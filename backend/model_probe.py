"""List model names available to the configured API key without sending content."""
from google import genai
from backend.app.config import settings

client = genai.Client(api_key=settings.gemini_api_key)
for model in client.models.list():
    if any(token in model.name.lower() for token in ("live", "embedding", "flash-lite")):
        print(model.name)
