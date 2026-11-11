"""Connectivity probe only: opens and closes Live without transmitting content."""
import asyncio
from google import genai
from google.genai import types
from backend.app.config import settings


async def main():
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is missing")
    client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(api_version=settings.live_api_version))
    async with client.aio.live.connect(model=settings.live_model, config={"response_modalities": ["AUDIO"]}):
        print("LIVE_CONNECTED")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=20))
