import asyncio
import time
import unittest
from types import SimpleNamespace

from app import CallState, nudge_worker, receive_live
from nudge_engine import RealTimeNudgeEngine


class NudgeControllerTests(unittest.TestCase):
    def test_required_signals_and_suppression(self):
        engine = RealTimeNudgeEngine(cooldown_seconds=30)
        examples = [
            ("MISSED_CROSS_SELL", "Customer wants a second car"),
            ("RISING_FRUSTRATION", "I am frustrated and want a human"),
            ("PAYMENT_DIFFICULTY", "I cannot afford this installment"),
            ("COMPLIANCE_GAP", "What fees do I have to pay?"),
            ("CALLBACK_REQUEST", "Please call me back later"),
        ]
        for signal, text in examples:
            self.assertEqual(engine.accept_decision(text, "customer", {
                "signal": signal, "confidence": 0.93})[0]["signal"], signal)
        self.assertEqual(engine.accept_decision(examples[0][1], "customer", {
            "signal": examples[0][0], "confidence": 0.93}), [])
        self.assertEqual(engine.accept_decision("Car", "customer", {
            "signal": "MISSED_CROSS_SELL", "confidence": 0.99}), [])
        self.assertEqual(engine.accept_decision("Customer wants a second car", "agent", {
            "signal": "MISSED_CROSS_SELL", "confidence": 0.99}), [])
        self.assertEqual(engine.accept_decision("Customer wants a second car", "customer", {
            "signal": "MISSED_CROSS_SELL", "confidence": 0.60}), [])

    def test_risky_agent_claim_and_disclosure_state(self):
        engine = RealTimeNudgeEngine(cooldown_seconds=0)
        alerts = engine.accept_decision("Approval is guaranteed with no documents", "agent", {
            "signal": "COMPLIANCE_RISK", "confidence": 0.94})
        self.assertEqual(alerts[0]["priority"], "high")
        engine.accept_decision("The processing fee and rate are in the policy", "agent", {
            "signal": "DISCLOSURE_GIVEN", "confidence": 0.91})
        self.assertEqual(engine.accept_decision("What are the fees and rates?", "customer", {
            "signal": "COMPLIANCE_GAP", "confidence": 0.96}), [])

    def test_interim_transcript_reaches_worker_before_final(self):
        class EndOfStream(Exception):
            pass

        class FakeSession:
            async def receive(self):
                content = SimpleNamespace(
                    interim_input_transcription=SimpleNamespace(text="Customer wants a second car"),
                    input_transcription=None, output_transcription=None, model_turn=None,
                )
                yield SimpleNamespace(server_content=content, tool_call=None)
                raise EndOfStream()

        class FakeClassifier:
            async def classify(self, text, source, disclosure_seen):
                return {"signal": "MISSED_CROSS_SELL", "confidence": 0.95}, 15.0

        async def check():
            state = CallState(RealTimeNudgeEngine(), kb=None, market="india",
                              classifier=FakeClassifier(), audio_received_at=time.perf_counter())
            queue = asyncio.Queue(maxsize=3)
            worker = asyncio.create_task(nudge_worker(state, queue))
            try:
                with self.assertRaises(EndOfStream):
                    await receive_live(FakeSession(), None, state, queue)
                await queue.join()
                self.assertTrue(state.transcript_seen)
                self.assertEqual(state.nudge_count, 1)
                self.assertIn("llm", state.engine.latency_report())
            finally:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
