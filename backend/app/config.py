from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    chat_model: str = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
    live_model: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
    max_output_tokens: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024"))
    allow_knowledge_export: bool = os.getenv("ALLOW_KNOWLEDGE_EXPORT", "false").lower() == "true"
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    allowed_origins: tuple[str, ...] = tuple(x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if x.strip())
    database_path: Path = ROOT / os.getenv("DATABASE_PATH", "data/assistant.db")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024


settings = Settings()
