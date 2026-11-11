import asyncio
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent.service import chat, create_conversation, history
from .config import ROOT, settings
from .db import connection, init_db
from .knowledge import ingest, retrieve, seed, reindex_embeddings
from .live import live_socket
from . import tools as domain


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await asyncio.to_thread(seed)
    yield


app = FastAPI(title="Township Voice Advisor", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Admin-Token"])
requests_by_ip: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        times = requests_by_ip[ip]
        cutoff = time.monotonic() - 60
        while times and times[0] < cutoff:
            times.popleft()
        if len(times) >= 80:
            return JSONResponse({"detail": "Too many requests. Try again shortly."}, status_code=429)
        times.append(time.monotonic())
    return await call_next(request)


def admin(x_admin_token: str | None = Header(default=None)):
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(403, "Admin access denied")


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="en", pattern="^(en|hi|hinglish)$")
    consent_to_store: bool = False


@app.get("/api/health")
def health():
    with connection() as db:
        chunks = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        vectors = db.execute("SELECT count(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
    return {"status": "ok", "gemini_configured": bool(settings.gemini_api_key), "voice_available": bool(settings.gemini_api_key and settings.allow_knowledge_export), "text_mode": "gemini" if settings.gemini_api_key and settings.allow_knowledge_export else "local_reference", "knowledge_export_enabled": settings.allow_knowledge_export, "knowledge_chunks": chunks, "embedded_chunks": vectors, "chat_model": settings.chat_model, "live_model": settings.live_model}


@app.post("/api/chat")
async def chat_route(data: ChatRequest):
    if not data.message.strip():
        raise HTTPException(422, "Message cannot be empty")
    conversation_id = data.conversation_id or create_conversation(data.language)
    try:
        return await asyncio.to_thread(chat, conversation_id, data.message.strip(), data.language, data.consent_to_store)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gemini request failed. Check the API key, model access and quota, then retry.") from error


@app.get("/api/conversations/{conversation_id}")
def conversation_route(conversation_id: str):
    try:
        return {"messages": history(conversation_id)}
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.get("/api/projects")
def projects():
    return {"township": domain.get_township_overview(), "projects": domain.PROJECTS, "distances_km": domain.DISTANCES}


@app.get("/api/knowledge/search")
def search(q: str = "", project: str | None = None):
    return {"results": retrieve(q[:400], project, limit=8)}


@app.post("/api/leads")
def lead(data: domain.Lead):
    return domain.capture_customer_lead(data)


@app.post("/api/visits")
def visit(data: domain.Visit):
    return domain.create_site_visit_request(data)


@app.post("/api/callbacks")
def callback(data: domain.Callback):
    return domain.request_human_callback(data)


@app.get("/api/admin/leads", dependencies=[Depends(admin)])
def admin_leads():
    with connection() as db:
        return {"leads": [dict(row) for row in db.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT 100")]}


@app.get("/api/admin/requests", dependencies=[Depends(admin)])
def admin_requests():
    with connection() as db:
        return {"visits": [dict(row) for row in db.execute("SELECT * FROM visits ORDER BY created_at DESC LIMIT 100")],
                "callbacks": [dict(row) for row in db.execute("SELECT * FROM callbacks ORDER BY created_at DESC LIMIT 100")]}


@app.post("/api/admin/ingest", dependencies=[Depends(admin)])
async def upload_knowledge(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise HTTPException(415, "Only PDF, TXT and Markdown files are supported")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File exceeds configured upload limit")
    if suffix == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(415, "Invalid PDF")
    folder = ROOT / "data" / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4()}{suffix}"
    try:
        path.write_bytes(data)
        return await asyncio.to_thread(ingest, path, Path(file.filename or "document").name)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/admin/reindex", dependencies=[Depends(admin)])
async def reindex():
    return await asyncio.to_thread(reindex_embeddings)


@app.websocket("/ws/live")
async def live(ws: WebSocket):
    await live_socket(ws)


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

