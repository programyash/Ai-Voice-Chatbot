import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.database_path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def init_db():
    with connection() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS chunks (
          id TEXT PRIMARY KEY, source TEXT NOT NULL, page INTEGER,
          section TEXT NOT NULL, project TEXT, body TEXT NOT NULL,
          embedding TEXT, embedding_model TEXT, created_at TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
          body, section, project, content='chunks', content_rowid='rowid'
        );
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
          INSERT INTO chunks_fts(rowid, body, section, project)
          VALUES (new.rowid, new.body, new.section, new.project);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
          INSERT INTO chunks_fts(chunks_fts, rowid, body, section, project)
          VALUES ('delete', old.rowid, old.body, old.section, old.project);
        END;
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY, language TEXT NOT NULL DEFAULT 'en',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
          role TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        );
        CREATE TABLE IF NOT EXISTS leads (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, mobile TEXT, email TEXT,
          project TEXT, interest TEXT, budget TEXT, contact_time TEXT,
          requirements TEXT, consent_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visits (
          id TEXT PRIMARY KEY, project TEXT, preferred_date TEXT NOT NULL,
          preferred_time TEXT, name TEXT NOT NULL, mobile TEXT, email TEXT,
          status TEXT NOT NULL DEFAULT 'pending confirmation', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS callbacks (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, mobile TEXT, email TEXT,
          note TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        """)
