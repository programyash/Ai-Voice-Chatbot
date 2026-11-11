"""Browser PCM/WebSocket bridge to Gemini Live; credentials never reach the browser."""
import asyncio
import base64
import binascii
from contextlib import suppress

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from .config import settings
from .agent.service import PROMPT, agent_functions, create_conversation, save_message


async def live_socket(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin not in settings.allowed_origins:
        await ws.close(code=1008)
        return
    await ws.accept()
    if not settings.gemini_api_key or not settings.allow_knowledge_export:
        await ws.send_json({"type": "error", "message": "Gemini Live is unavailable until cloud knowledge access is approved and configured."})
        await ws.close(code=1011)
        return
    try:
        start = await asyncio.wait_for(ws.receive_json(), timeout=15)
        if start.get("type") != "start":
            await ws.close(code=1008)
            return
        language = start.get("language", "en")
        if language not in {"en", "hi", "hinglish"}:
            language = "en"
        conversation_id = create_conversation(language)
        allow_write = start.get("consent_to_store") is True
        await ws.send_json({"type": "session", "conversation_id": conversation_id})
        await ws.send_json({"type": "status", "value": "connecting"})
        client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(api_version=settings.live_api_version))
        functions = agent_functions(allow_write)
        declarations = [types.FunctionDeclaration.from_callable(callable=fn, client=client, use_json_schema=True) for fn in functions]
        function_map = {fn.__name__: fn for fn in functions}
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=PROMPT + f"\nPreferred language: {language}. Use retrieve_project_knowledge before making factual township claims.",
            tools=[types.Tool(function_declarations=declarations)],
        )
        async with client.aio.live.connect(model=settings.live_model, config=config) as session:
            await ws.send_json({"type": "status", "value": "listening"})

            async def browser_to_gemini():
                while True:
                    packet = await ws.receive_json()
                    kind = packet.get("type")
                    if kind == "stop":
                        return
                    if kind == "audio":
                        encoded = packet.get("data", "")
                        if not isinstance(encoded, str) or len(encoded) > 90000:
                            continue
                        try:
                            pcm = base64.b64decode(encoded, validate=True)
                        except (binascii.Error, ValueError):
                            continue
                        if pcm:
                            await session.send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
                    elif kind == "audio_end":
                        await session.send_realtime_input(audio_stream_end=True)
                    elif kind == "text" and isinstance(packet.get("text"), str):
                        text = packet["text"].strip()[:2000]
                        if text:
                            save_message(conversation_id, "user", text)
                            await session.send_client_content(turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)

            async def gemini_to_browser():
                while True:
                    async for msg in session.receive():
                        if msg.tool_call:
                            replies = []
                            for call in msg.tool_call.function_calls:
                                fn = function_map.get(call.name)
                                try:
                                    result = fn(**dict(call.args or {})) if fn else {"error": "Unknown tool"}
                                except Exception:
                                    result = {"error": "Tool validation or execution failed"}
                                replies.append(types.FunctionResponse(name=call.name, response=result, id=call.id))
                            if replies:
                                await session.send_tool_response(function_responses=replies)
                        content = msg.server_content
                        if not content:
                            continue
                        if content.interrupted:
                            await ws.send_json({"type": "interrupted"})
                        if content.input_transcription and content.input_transcription.text:
                            text = content.input_transcription.text.strip()
                            await ws.send_json({"type": "transcript", "role": "user", "text": text})
                            await ws.send_json({"type": "status", "value": "processing"})
                            save_message(conversation_id, "user", text)
                        if content.output_transcription and content.output_transcription.text:
                            text = content.output_transcription.text.strip()
                            await ws.send_json({"type": "transcript", "role": "assistant", "text": text})
                            save_message(conversation_id, "assistant", text)
                        if content.model_turn:
                            for part in content.model_turn.parts or []:
                                if part.inline_data and part.inline_data.data:
                                    await ws.send_json({"type": "audio", "data": base64.b64encode(part.inline_data.data).decode("ascii")})
                                    await ws.send_json({"type": "status", "value": "speaking"})
                        if content.turn_complete:
                            await ws.send_json({"type": "status", "value": "listening"})

            sender = asyncio.create_task(browser_to_gemini())
            receiver = asyncio.create_task(gemini_to_browser())
            done, pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in pending:
                with suppress(asyncio.CancelledError):
                    await task
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        with suppress(Exception):
            await ws.send_json({"type": "error", "message": "Live voice could not connect or was interrupted. Check the Gemini key, model access and network, then retry."})
    finally:
        with suppress(Exception):
            await ws.close()

