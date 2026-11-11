"""Section-aware ingestion with SQLite FTS5 and persistent Gemini vectors."""
import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any

import pdfplumber
from google import genai
from google.genai import types

from .config import ROOT, settings
from .db import connection, now

SEED = ROOT / "backend" / "knowledge" / "assignment_transcript.md"
SOURCE = "Assignment - AI Voice Bot Development.pdf"
MARKER = re.compile(r"<!-- page: (\d+) \| section: ([^|]+) \| project: ([^ ]+) -->")
STOPWORDS = {"what", "is", "the", "in", "how", "does", "are", "there", "much", "many", "of", "to", "for", "and", "was", "were", "do", "this", "that", "it", "can", "i", "me", "about", "a", "an", "on", "with", "have"}
ALIASES = {"विला": "villa", "प्लॉट": "plot", "फ्रीहोल्ड": "freehold", "हैं": "", "क्या": ""}


def _terms(text: str) -> set[str]:
    for original, replacement in ALIASES.items():
        text = text.replace(original, replacement)
    words = re.findall(r"[\w]+", text.lower(), flags=re.UNICODE)
    normalized = []
    for word in words:
        if not word or word in STOPWORDS:
            continue
        normalized.append(word[:-1] if word.endswith("s") and len(word) > 4 else word)
    return set(normalized)


def _client():
    return genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key and settings.allow_knowledge_export else None


def _embedding(contents: list[str], task: str) -> list[list[float]] | None:
    client = _client()
    if not client or not contents:
        return None
    config = types.EmbedContentConfig(task_type=task) if settings.embedding_model == "gemini-embedding-001" else None
    result = client.models.embed_content(model=settings.embedding_model, contents=contents, config=config)
    return [item.values for item in result.embeddings]


def _segments(text: str, source: str, page: int | None = None):
    if source == SOURCE and MARKER.search(text):
        for match in MARKER.finditer(text):
            end = MARKER.search(text, match.end())
            body = text[match.end():end.start() if end else len(text)].strip()
            if body:
                yield {"source": source, "page": int(match.group(1)), "section": match.group(2).strip(), "project": match.group(3).strip(), "body": body}
        return
    # New documents: split on headings/paragraphs and overlap long sections.
    sections = re.split(r"(?=^#{1,3}\s+)", text, flags=re.M)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        title = section.splitlines()[0].lstrip("# ")[:100]
        words = section.split()
        if len(words) <= 180:
            yield {"source": source, "page": page, "section": title, "project": None, "body": section}
        else:
            for start in range(0, len(words), 150):
                body = " ".join(words[start:start + 180])
                if body:
                    yield {"source": source, "page": page, "section": title, "project": None, "body": body}
                if start + 180 >= len(words):
                    break


def _pdf_text(path: Path) -> list[tuple[int, str]]:
    with pdfplumber.open(path) as pdf:
        pages = []
        for i, page in enumerate(pdf.pages):
            body = page.extract_text() or ""
            if not body.strip() and _client():
                rendered = page.to_image(resolution=140).original
                output = io.BytesIO()
                rendered.save(output, format="PNG")
                result = _client().models.generate_content(
                    model=settings.chat_model,
                    contents=[types.Part.from_bytes(data=output.getvalue(), mime_type="image/png"), "Transcribe all visible page text faithfully. Preserve headings, numbers, and units. Return only transcription."],
                    config=types.GenerateContentConfig(temperature=0),
                )
                body = result.text or ""
            pages.append((i + 1, body))
    if not any(body.strip() for _, body in pages):
        raise ValueError("This PDF contains no extractable text. Supply a reviewed OCR transcript as Markdown, or enable approved Gemini OCR. The bundled assignment transcript is already included.")
    return pages


def ingest(path: Path, source_name: str | None = None) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise ValueError("Only PDF, TXT, and Markdown files are supported")
    source = source_name or path.name
    if suffix == ".pdf":
        segments = [item for page, text in _pdf_text(path) for item in _segments(text, source, page)]
    else:
        text = path.read_text(encoding="utf-8")
        segments = list(_segments(text, source))
    if not segments:
        raise ValueError("No usable content found")
    unique = {hashlib.sha256(s["body"].encode()).hexdigest(): s for s in segments}
    records = [{"id": key, **value} for key, value in unique.items()]
    try:
        vectors = _embedding([s["body"] for s in records], "RETRIEVAL_DOCUMENT")
    except Exception:
        vectors = None  # FTS remains usable during an embedding outage.
    with connection() as db:
        for i, record in enumerate(records):
            db.execute("DELETE FROM chunks WHERE id=?", (record["id"],))
            db.execute("""INSERT INTO chunks
              (id, source, page, section, project, body, embedding, embedding_model, created_at)
              VALUES (?,?,?,?,?,?,?,?,?)""",
              (record["id"], record["source"], record["page"], record["section"], record["project"], record["body"],
               json.dumps(vectors[i]) if vectors else None, settings.embedding_model if vectors else None, now()))
    return {"source": source, "chunks": len(records), "embedded": bool(vectors)}


def seed():
    with connection() as db:
        count = db.execute("SELECT count(*) FROM chunks WHERE source=?", (SOURCE,)).fetchone()[0]
    if not count:
        ingest(SEED, SOURCE)
    elif settings.allow_knowledge_export:
        reindex_embeddings()


def reindex_embeddings() -> dict:
    """Generate missing or stale vectors after cloud knowledge transfer is enabled."""
    if not _client():
        return {"embedded": 0, "reason": "cloud knowledge access disabled"}
    with connection() as db:
        rows = [dict(x) for x in db.execute("SELECT id, body FROM chunks WHERE embedding IS NULL OR embedding_model IS NOT ?", (settings.embedding_model,))]
    count = 0
    for start in range(0, len(rows), 16):
        batch = rows[start:start + 16]
        vectors = _embedding([row["body"] for row in batch], "RETRIEVAL_DOCUMENT")
        if not vectors:
            continue
        with connection() as db:
            for row, vector in zip(batch, vectors):
                db.execute("UPDATE chunks SET embedding=?, embedding_model=? WHERE id=?", (json.dumps(vector), settings.embedding_model, row["id"]))
                count += 1
    return {"embedded": count}


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def retrieve(query: str, project: str | None = None, limit: int = 5) -> list[dict]:
    if not query.strip():
        return []
    tokens = list(_terms(query))
    fts_query = " OR ".join(f'"{x}"' for x in tokens[:12])
    with connection() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM chunks WHERE (? IS NULL OR project=? OR project='township')", (project, project))]
        lexical = {}
        if fts_query:
            try:
                for row in db.execute("SELECT c.id, bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid WHERE chunks_fts MATCH ?", (fts_query,)):
                    lexical[row["id"]] = 1 / (1 + max(0, row["rank"] + 10))
            except Exception:
                pass
    try:
        query_vec = (_embedding([query], "RETRIEVAL_QUERY") or [None])[0]
    except Exception:
        query_vec = None
    ranked = []
    for row in rows:
        semantic = _cosine(query_vec, json.loads(row["embedding"])) if query_vec and row["embedding"] and row["embedding_model"] == settings.embedding_model else 0
        words = set(tokens)
        keyword = len(words & _terms(row["body"] + " " + row["section"])) / max(1, len(words))
        project_hint = re.search(r"\bproject\s*([ab])\b", query.lower())
        project_bonus = 0.12 if project_hint and row["project"] == project_hint.group(1).upper() else 0
        score = 0.55 * max(0, semantic) + 0.35 * keyword + 0.10 * lexical.get(row["id"], 0) + project_bonus
        if score >= 0.08:
            ranked.append({"id": row["id"], "source": row["source"], "page": row["page"], "section": row["section"], "project": row["project"], "text": row["body"], "score": round(score, 3)})
    return sorted(ranked, key=lambda x: x["score"], reverse=True)[:limit]

