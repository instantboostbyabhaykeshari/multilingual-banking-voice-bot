"""Small live API classification check; consumes Gemini API calls."""
import asyncio
import os
from statistics import median, quantiles

from dotenv import load_dotenv
from google import genai

from llm_nudges import GeminiNudgeClassifier
from nudge_engine import RealTimeNudgeEngine


CASES = [
    ("Customer needs a second car for family", "customer", "MISSED_CROSS_SELL"),
    ("I am very frustrated, please connect me to a person", "customer", "RISING_FRUSTRATION"),
    ("My budget is tight and I cannot afford the EMI", "customer", "PAYMENT_DIFFICULTY"),
    ("What are the fees and charges?", "customer", "COMPLIANCE_GAP"),
    ("This is guaranteed approval with no documents", "agent", "COMPLIANCE_RISK"),
    ("Mujhe family ke liye ek aur gaadi leni hai", "customer", "MISSED_CROSS_SELL"),
    ("Mahal ang hulog ko, hindi ko kaya", "customer", "PAYMENT_DIFFICULTY"),
    ("Saya ingin kendaraan kedua untuk keluarga", "customer", "MISSED_CROSS_SELL"),
    ("I need a normal car loan", "customer", "NONE"),
    ("Mobil saya rusak, jadi mau perbaikan", "customer", "NONE"),
    ("Hello, can you hear me?", "customer", "NONE"),
    ("I will call you later", "customer", "NONE"),
]


async def main():
    load_dotenv()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    classifier = GeminiNudgeClassifier(client)
    limiter = asyncio.Semaphore(2)

    async def check(text, source, expected):
        async with limiter:
            decision, latency_ms = await classifier.classify(text, source, False)
        engine = RealTimeNudgeEngine(cooldown_seconds=0)
        alerts = engine.accept_decision(text, source, decision)
        actual = alerts[0]["signal"] if alerts else "NONE"
        print(f"{expected:22} -> {actual:22}  {latency_ms:7.0f} ms  {text}")
        return expected, actual, latency_ms

    results = await asyncio.gather(*(check(*case) for case in CASES))
    false_positives = sum(expected == "NONE" and actual != "NONE" for expected, actual, _ in results)
    misses = sum(expected != "NONE" and actual != expected for expected, actual, _ in results)
    latencies = [elapsed for _, _, elapsed in results]
    print(f"LLM latency P50={median(latencies):.0f} ms P95={quantiles(latencies, n=20, method='inclusive')[18]:.0f} ms")
    print(f"False positives: {false_positives}/4 negatives; misses: {misses}/8 positives")
    if false_positives or misses:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
