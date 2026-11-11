"""End-to-end local WebSocket bridge probe using a text turn and audio response."""
import asyncio
import base64
import json
from pathlib import Path
import wave

import websockets


async def main():
    counts = {"audio": 0, "transcript": 0, "status": 0, "error": 0}
    audio_chunks = []
    async with websockets.connect("ws://127.0.0.1:8000/ws/live", origin="http://127.0.0.1:5173", max_size=8_000_000) as ws:
        await ws.send(json.dumps({"type": "start", "language": "en", "consent_to_store": False}))
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            if event["type"] == "error":
                raise RuntimeError(event["message"])
            if event["type"] == "status" and event["value"] == "listening":
                break
        await ws.send(json.dumps({"type": "text", "text": "What is the minimum villa plot size? Answer briefly."}))
        for _ in range(100):
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=45))
            kind = event["type"]
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "error":
                raise RuntimeError(event["message"])
            if kind == "audio":
                audio_chunks.append(base64.b64decode(event["data"]))
            if kind == "transcript":
                print(event["role"], event["text"][:200])
            if kind == "status" and event["value"] == "listening" and counts["audio"] > 0:
                break
        await ws.send(json.dumps({"type": "stop"}))
    print(counts)
    if counts["audio"] == 0:
        raise SystemExit("No generated audio received")
    path = Path("tmp/live-answer.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"".join(audio_chunks))
    print(f"Saved {path} for microphone input testing")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=90))
