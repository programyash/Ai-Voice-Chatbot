# Testing and evaluation

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m backend.evaluate
```

From `frontend`:

```powershell
npm run build
node scripts/visual-check.mjs
```

The visual check uses an isolated headless Chrome profile and assumes the backend is at port 8000 and Vite is at port 5173. It checks desktop/mobile overflow, project switching, inquiry dialog opening, and browser page errors, then writes temporary screenshots under `tmp/`.

The evaluation dataset at `backend/evaluation_cases.json` contains 46 single-turn questions and four multi-turn scenarios, covering township, connectivity, projects, investment caveats, Hindi/Hinglish, unknowns and prompt injection. Offline evaluation checks whether the expected source section appears in the top three retrieved chunks. Current result: **44/44 known-fact cases (100%)** with keyword retrieval. This is a source-location metric; it does not prove generated answer quality.

After explicit approval of assignment-content transfer and a working Live-capable account, set `ALLOW_KNOWLEDGE_EXPORT=true`, restart, and run `python -m backend.evaluate --live`. The live mode checks expected answer fragments and prints multi-turn answers for manual review. Review factual accuracy, unsupported claims, tool use, unknown-answer handling and conversational tone; paraphrases may be marked `REVIEW` despite being correct. Also test microphone permission denial, reconnect, interruption and Hindi/Hinglish speech manually.

Current test evidence: six backend tests passed; Vite production build passed; desktop/mobile Playwright checks passed with no horizontal overflow or page errors. A generic Gemini text request, embedding request and area-conversion function call succeeded. Gemini Live content-free connection attempts returned HTTP 404 for the default stable model and a documented preview model. No assignment content has been sent to Gemini.

