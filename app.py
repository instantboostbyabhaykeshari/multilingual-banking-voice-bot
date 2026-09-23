"""Live Gemini voice bot with in-call recommendations and grounded policy lookup."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from knowledge_base import ProductionKnowledgeBase
from llm_nudges import GeminiNudgeClassifier
from market_configs import MARKET_DATA
from nudge_engine import RealTimeNudgeEngine


INPUT_RATE = 16000
OUTPUT_RATE = 24000  # Gemini Live audio output is 24 kHz PCM.
FRAMES_PER_CHUNK = 1600  # 100 ms at 16 kHz.
OUTPUT_FRAMES_PER_BUFFER = 480  # 20 ms, bounding audible audio after a flush.
INTERRUPT_RMS = 500
INTERRUPT_VOICED_CHUNKS = 2
INTERRUPT_QUIET_CHUNKS = 4
MODEL_NAME = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")


@dataclass
class CallState:
    engine: RealTimeNudgeEngine
    kb: ProductionKnowledgeBase
    market: str
    classifier: GeminiNudgeClassifier | None = None
    audio_received_at: float | None = None
    transcript_seen: bool = False
    nudge_count: int = 0


class AudioPlayback:
    """Thread-safe PCM queue consumed by PortAudio's short output callback."""

    def __init__(self, pa_continue: int):
        self.pa_continue = pa_continue
        self.lock = threading.Lock()
        self.chunks: deque[bytes] = deque()
        self.pending = b""
        self.last_played_at = 0.0
        self.drop_until_turn_end = False
        self.user_speaking = False
        self.turn_finished = True

    def callback(self, _input, frame_count, _time_info, _status):
        needed = frame_count * 2  # Mono 16-bit PCM.
        with self.lock:
            while len(self.pending) < needed and self.chunks:
                self.pending += self.chunks.popleft()
            data, self.pending = self.pending[:needed], self.pending[needed:]
            if data:
                self.last_played_at = time.perf_counter()
        return (data.ljust(needed, b"\0"), self.pa_continue)

    def enqueue(self, data: bytes) -> None:
        with self.lock:
            if not self.drop_until_turn_end and not self.user_speaking:
                self.chunks.append(data)
                self.turn_finished = False

    def interrupt(self) -> bool:
        with self.lock:
            audible = bool(self.pending or self.chunks) or time.perf_counter() - self.last_played_at < 0.15
            if audible:
                self.pending = b""
                self.chunks.clear()
                # A fully generated turn has no later interruption event;
                # its queued audio has now been discarded completely.
                self.drop_until_turn_end = not self.turn_finished
            return audible

    def server_interrupted(self) -> None:
        with self.lock:
            self.pending = b""
            self.chunks.clear()
            # The server has ended the old turn. Its next audio belongs to a new one.
            self.drop_until_turn_end = False
            self.turn_finished = True

    def turn_complete(self) -> None:
        with self.lock:
            self.drop_until_turn_end = False
            self.turn_finished = True

    def set_user_speaking(self, speaking: bool) -> None:
        with self.lock:
            self.user_speaking = speaking


class SpeechDetector:
    """Confirm local microphone speech before cutting off playback."""

    def __init__(self):
        self.voiced = 0
        self.quiet = 0
        self.speaking = False

    def update(self, rms: int) -> tuple[bool, bool]:
        if rms >= INTERRUPT_RMS:
            self.voiced += 1
            self.quiet = 0
            if not self.speaking and self.voiced >= INTERRUPT_VOICED_CHUNKS:
                self.speaking = True
                return True, False
        else:
            self.voiced = 0
            self.quiet += 1
            if self.speaking and self.quiet >= INTERRUPT_QUIET_CHUNKS:
                self.speaking = False
                return False, True
        return False, False


def pcm_rms(data: bytes) -> float:
    """RMS of signed 16-bit microphone PCM (audioop is absent in Python 3.13)."""
    samples = np.frombuffer(data, dtype="<i2").astype(np.float64)
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


def live_config(market: str) -> types.LiveConnectConfig:
    market_instruction = MARKET_DATA[market]["system_instruction"]
    grounding = (
        "Keep replies brief: one or two short sentences, then let the caller respond. "
        "Detect the caller's language and reply in that same language; for mixed speech, use the dominant language. "
        "If the caller starts speaking, stop and listen; do not repeat an interrupted answer. "
        "For any specific policy fact (rates, eligibility, amounts, documents, tenure, "
        "fees or offers), call query_knowledge_base before answering. Quote only facts "
        "returned with found=true and cite the source/page in speech. If no verified "
        "passage is found, say the policy is unavailable and offer a human callback. "
        "If the caller asks to speak to a human agent, treat this as a demo transfer and say exactly: "
        "'Sure, I am connecting you to a human agent now.' Do not claim that a real transfer occurred; "
        "this prototype only simulates the transfer response. "
        "Never present a nudge as a policy fact. Do not promise an offer, approval, "
        "or any other real workflow action. "
        "If the source contains a data-quality warning, do not quote the disputed value."
    )
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        # Auto detection supports natural code switching. Live streaming does
        # not support speaker diarization; input and output are separate here.
        input_audio_transcription=types.AudioTranscriptionConfig(language_codes=[]),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(parts=[types.Part(text=market_instruction + "\n" + grounding)]),
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
            name="query_knowledge_base",
            description="Retrieve a verified banking policy passage with source and page; use before policy claims.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={"user_query": types.Schema(type=types.Type.STRING)},
                required=["user_query"],
            ),
        )])],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede"))),
    )


def display_nudges(state: CallState, alerts: list[dict], audio_at: float | None) -> None:
    started = time.perf_counter()
    for alert in alerts:
        print(f"\n[LIVE NUDGE][{alert['priority'].upper()}] {alert['signal']}")
        print(f"  {alert['nudge']}  (model confidence={alert['confidence']:.2f})", flush=True)
        state.nudge_count += 1
    if alerts:
        state.engine.record_latency("delivery", (time.perf_counter() - started) * 1000)
        if audio_at is not None:
            state.engine.record_latency("audio_to_nudge", (time.perf_counter() - audio_at) * 1000)


def process_transcript(state: CallState, text: str, source: str,
                       queue: asyncio.Queue, audio_at: float | None = None) -> None:
    if not text or not text.strip():
        return
    if source == "customer":
        state.transcript_seen = True
        elapsed = (time.perf_counter() - audio_at) * 1000 if audio_at is not None else None
        print(f"\n[Customer transcript] {text}"
              + (f"  (audio-to-ASR estimate {elapsed:.0f} ms)" if elapsed is not None else ""), flush=True)
        if elapsed is not None:
            state.engine.record_latency("asr_estimate", elapsed)
    else:
        print(f"\n[Bot transcript] {text}", flush=True)
    if queue.full():
        queue.get_nowait()  # Discard stale interim text; use the newest update.
        queue.task_done()
    queue.put_nowait((text, source, audio_at))


async def nudge_worker(state: CallState, queue: asyncio.Queue):
    while True:
        text, source, audio_at = await queue.get()
        try:
            decision, llm_ms = await state.classifier.classify(
                text, source, state.engine.disclosure_seen)
            state.engine.record_latency("llm", llm_ms)
            alerts = state.engine.accept_decision(text, source, decision)
            display_nudges(state, alerts, audio_at)
        except Exception as exc:
            print(f"[Nudge classifier error] {exc}", flush=True)
        finally:
            queue.task_done()


async def stream_microphone(session, stream, state: CallState, playback: AudioPlayback):
    detector = SpeechDetector()
    try:
        while True:
            data = await asyncio.to_thread(stream.read, FRAMES_PER_CHUNK, False)
            if not data:
                continue
            # The first chunk after a finalized transcript is the approximate
            # start of the next utterance. The API does not align transcript
            # events to exact input chunks, so this is an estimate.
            rms = pcm_rms(data)
            if state.audio_received_at is None and rms >= 180:
                state.audio_received_at = time.perf_counter()
            speech_started, speech_ended = detector.update(rms)
            if speech_started:
                playback.set_user_speaking(True)
                if playback.interrupt():
                    print("\n[Interrupted: listening]", flush=True)
            elif speech_ended:
                playback.set_user_speaking(False)
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=f"audio/pcm;rate={INPUT_RATE}"))
    except asyncio.CancelledError:
        raise


async def receive_live(session, playback: AudioPlayback, state: CallState, queue: asyncio.Queue):
    while True:
        async for response in session.receive():
            content = response.server_content
            if content:
                interrupted = getattr(content, "interrupted", False)
                if interrupted:
                    playback.server_interrupted()
                # Interim text arrives while the customer is speaking. Final
                # text may repeat it; the engine's cooldown suppresses repeats.
                for transcript in (content.interim_input_transcription, content.input_transcription):
                    if transcript and transcript.text:
                        process_transcript(state, transcript.text, "customer", queue, state.audio_received_at)
                if content.input_transcription and content.input_transcription.text:
                    state.audio_received_at = None
                if content.output_transcription and content.output_transcription.text:
                    process_transcript(state, content.output_transcription.text, "agent", queue)
                if not interrupted and content.model_turn and content.model_turn.parts:
                    for part in content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            playback.enqueue(part.inline_data.data)
                if getattr(content, "turn_complete", False):
                    playback.turn_complete()

            if response.tool_call and response.tool_call.function_calls:
                replies = []
                for call in response.tool_call.function_calls:
                    if call.name == "query_knowledge_base":
                        query = (call.args or {}).get("user_query", "")
                        result = await asyncio.to_thread(state.kb.query, query, state.market)
                        print("\n[Policy lookup] " + json.dumps(result, ensure_ascii=False), flush=True)
                    else:
                        result = {"found": False, "reason": "Unknown tool"}
                    replies.append(types.FunctionResponse(name=call.name, id=call.id, response=result))
                await session.send_tool_response(function_responses=replies)


async def run_call(market: str) -> None:
    import pyaudio

    audio = pyaudio.PyAudio()
    input_stream = output_stream = None
    state = None
    try:
        kb = ProductionKnowledgeBase()
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        state = CallState(RealTimeNudgeEngine(), kb, market, GeminiNudgeClassifier(client))
        input_stream = audio.open(format=pyaudio.paInt16, channels=1, rate=INPUT_RATE,
                                  input=True, frames_per_buffer=FRAMES_PER_CHUNK)
        playback = AudioPlayback(pyaudio.paContinue)
        output_stream = audio.open(format=pyaudio.paInt16, channels=1, rate=OUTPUT_RATE,
                                   output=True, frames_per_buffer=OUTPUT_FRAMES_PER_BUFFER,
                                   stream_callback=playback.callback)
        async with client.aio.live.connect(model=MODEL_NAME, config=live_config(market)) as session:
            print(f"Live call connected ({market}, {MODEL_NAME}). Speak into the microphone. Ctrl+C ends.")
            transcript_queue = asyncio.Queue(maxsize=3)
            await asyncio.gather(stream_microphone(session, input_stream, state, playback),
                                 receive_live(session, playback, state, transcript_queue),
                                 nudge_worker(state, transcript_queue))
    finally:
        if state:
            report = state.engine.latency_report()
            report["nudge_count"] = state.nudge_count
            report["notes"] = "Audio-to-ASR and audio-to-nudge start times are utterance estimates; the API does not align each transcript to an input chunk."
            print("\n[Q4 LATENCY REPORT] " + json.dumps(report), flush=True)
            if not state.transcript_seen:
                print("No input transcription received; check microphone/API transcription support.")
        for stream in (input_stream, output_stream):
            if stream is not None:
                stream.stop_stream()
                stream.close()
        audio.terminate()


def main() -> int:
    load_dotenv()
    market = sys.argv[1].lower() if len(sys.argv) > 1 else "india"
    if market not in MARKET_DATA:
        print(f"Unknown market: {market}. Options: {', '.join(MARKET_DATA)}")
        return 2
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is missing. Add it to .env before starting a live call.")
        return 2
    try:
        asyncio.run(run_call(market))
    except KeyboardInterrupt:
        print("\nCall ended by user.")
    except Exception as exc:
        print(f"Live call failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
