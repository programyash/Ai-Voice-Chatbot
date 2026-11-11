# Township Advisor

A real estate voice and text assistant built from the three-page AI Voice Bot assignment. It presents verified township and Project A/B information, retrieves source passages, supports customer inquiries, and bridges browser microphone audio to Gemini Live through a Python backend. The browser never receives the permanent Gemini key.

## Current verification status

- The local knowledge base contains a page-verified transcription of the scanned assignment PDF. An unrelated sentence embedded in the source page was excluded from the knowledge facts.
- The React interface, backend, SQLite persistence, ten agent tools, and audio bridge are implemented. Backend tests and the frontend build pass.
- The user approved sending the reviewed assignment facts to Gemini. This workspace's ignored `.env` enables the cloud knowledge switch; all seven source chunks have Gemini embeddings in SQLite. Grounded English and Hindi text answers, function calling, and multi-turn memory were verified.
- A content-free Live probe initially returned HTTP 404 because the installed SDK used the wrong WebSocket API version. Setting `GEMINI_LIVE_API_VERSION=v1alpha` resolved it. The local WebSocket received generated 24 kHz audio, and a browser test streamed synthetic microphone audio, received transcription, and played the model response.
- The complete evaluation ran: 44/44 known-fact retrieval targets in the top three, 38/46 exact answer-fragment matches, seven correct paraphrases flagged for review, and one transient transport error that succeeded on retry. Four multi-turn scenarios completed.

## Stack and architecture

- **Frontend:** React 19, TypeScript, Vite, Lucide, Web Audio API and AudioWorklet.
- **Backend:** FastAPI, Pydantic, official `google-genai` Python SDK, WebSockets.
- **Storage:** SQLite for conversations, messages, leads, visit/callback requests, FTS5 search and persistent embedding vectors.
- **Knowledge:** Reviewed Markdown transcription of the scanned source PDF. PDF/TXT/Markdown upload is supported; scanned PDFs require approved Gemini OCR or a reviewed text transcript.

See [architecture](docs/ARCHITECTURE.md), [tool reference](docs/TOOLS.md), and [testing guide](docs/TESTING.md).

## Prerequisites

Python 3.11+, Node.js 20+, npm, and a Gemini API key. Microphone capture requires a secure browser context (`localhost` qualifies) and Web Audio/AudioWorklet support. Gemini Live access is account and network dependent.

## Run locally (PowerShell)

From the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` and a long random `ADMIN_TOKEN`. The supplied key has been placed in the ignored local `.env` for this workspace. Do not put it into frontend files or commit it. The user approved assignment-content transfer for this workspace, so its local `.env` sets `ALLOW_KNOWLEDGE_EXPORT=true`. The distributed `.env.example` defaults to `false` for new installations.

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies `/api` and `/ws` to the backend. For a single-server build, run `npm run build` in `frontend`, then open [http://127.0.0.1:8000](http://127.0.0.1:8000); FastAPI serves `frontend/dist` when present.

On systems where `py -3.11` is unavailable, use an installed Python 3.11+ executable to create `.venv`. This workspace used the Codex bundled Python 3.12 runtime.

## Gemini setup and cloud knowledge switch

The backend reads model names from `.env`: `GEMINI_CHAT_MODEL`, `GEMINI_LIVE_MODEL`, and `GEMINI_EMBEDDING_MODEL`. Default chat is `gemini-3.5-flash-lite` because a content-free call to `gemini-3.8-flash` returned a temporary high-demand 503. The embedding default is `gemini-embedding-001`; Live defaults to `gemini-3.8-live` with `GEMINI_LIVE_API_VERSION=v1alpha`. Model names should be checked against [Google's model list](https://ai.google.dev/gemini-api/docs/models) for the account before changing them.

Once the source transfer is approved, set `ALLOW_KNOWLEDGE_EXPORT=true` and restart the backend. Startup embeds the existing knowledge chunks. The chat route sends retrieved assignment excerpts and recent conversation turns to Gemini. The Live route supplies a generic advisor instruction and retrieval tools; retrieved facts are sent to Gemini only when requested by the model. Scanned PDF OCR also sends rendered page images to Gemini. **This switch controls all of those transfers.** With the switch off, text chat returns verbatim local source excerpts instead of pretending to be an LLM answer.

Use `/api/health` to inspect `text_mode`, `embedded_chunks` and `voice_available`. `voice_available` means configured; the UI changes to connected only after the Live WebSocket opens. Run `python -m backend.live_probe` for a content-free Live connectivity check.

## Knowledge management

The initial knowledge lives at `backend/knowledge/assignment_transcript.md`, with source page metadata. The original PDF is scanned, so ordinary text extraction returns empty pages. The transcript was manually checked against page images. Startup creates `data/assistant.db` and indexes the transcript. Additional `.pdf`, `.txt`, and `.md` files can be uploaded to `POST /api/admin/ingest` with the `X-Admin-Token` header. Uploads are limited by `MAX_UPLOAD_MB` (10 MB default), validated and deleted after indexing. Text PDFs are extracted page by page; image-only PDFs use Gemini OCR only after the cloud knowledge switch is enabled. Review OCR output before relying on it for customer-facing answers.

The admin route `POST /api/admin/reindex` rebuilds missing/stale embeddings after changing the embedding model. Embedding models have incompatible vector spaces, so reindex after a model switch. The knowledge search route is `GET /api/knowledge/search?q=...`.

## Customer workflow

Customers can ask questions by text, choose English, Hindi, or Hinglish, or press the microphone for a live session. The browser streams 16-bit mono PCM at 16 kHz over the local WebSocket. The backend forwards audio to Gemini Live; generated 24 kHz PCM is played in the browser. Audio and text transcriptions are shown in the conversation. Speaking over playback stops local playback; Gemini interruption events also clear it. A failed connection is shown as an error, with retry on reconnect.

The inquiry dialog stores leads, site visit requests and callbacks only after the consent box is checked. A visit is saved as **pending confirmation**, not booked. Admin access to stored contacts uses `X-Admin-Token`; see [tools](docs/TOOLS.md).

## Security and retention

`.env` and the local SQLite database are ignored by Git. API keys remain server-side. CORS is restricted by `ALLOWED_ORIGINS`; HTTP routes have a per-IP rate limit. Requests and uploaded files are validated. Admin routes require `ADMIN_TOKEN`. The application does not log contact details or credentials. Protect access to the host machine and `data/assistant.db` in deployment.

Choose and communicate an organizational retention period. To remove conversations and contact requests older than 90 days, run:

```powershell
.\.venv\Scripts\python.exe -m backend.cleanup --days 90
```

This cleanup is manual; schedule it externally if required by your retention policy. No external CRM or scheduling service is connected.

## Tests and troubleshooting

See [testing guide](docs/TESTING.md) for commands and current results. If Gemini chat fails, check the key, cloud knowledge switch and model access; disabling the switch returns attributed local source excerpts. If Live returns a connection error, run the content-free probe and check the Live API version, WebSocket access and model availability. If the microphone is denied, allow it in the browser and reload. If the PDF upload says no extractable text, provide a reviewed Markdown/TXT transcript or enable approved OCR. Missing vector embeddings still leave keyword search operational.

