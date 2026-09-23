"""Check Gemini Live setup with the current key, without starting the mic."""
import asyncio
import os

from dotenv import load_dotenv
from google import genai

from app import MODEL_NAME, live_config


async def main():
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY missing")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    async with client.aio.live.connect(model=MODEL_NAME, config=live_config("india")):
        print(f"Connected to {MODEL_NAME} with the production call config")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=25))
