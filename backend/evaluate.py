"""Offline retrieval check; optional live answer smoke evaluation after approval."""
import argparse
import json
import sys
import time
from pathlib import Path

from backend.app.config import settings
from backend.app.db import init_db
from backend.app.knowledge import retrieve, seed


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Call Gemini on the evaluation questions (requires approved cloud knowledge access)")
    parser.add_argument("--limit", type=int, default=0, help="Limit the number of live single-turn cases; 0 runs all")
    args = parser.parse_args()
    init_db()
    seed()
    cases = json.loads((Path(__file__).parent / "evaluation_cases.json").read_text(encoding="utf-8"))
    known = [item for item in cases["single_turn"] if item["section"] != "unknown"]
    found = []
    for item in known:
        sections = [result["section"] for result in retrieve(item["q"], limit=3)]
        found.append((item["q"], item["section"] in sections))
    hits = sum(success for _, success in found)
    print(f"Retrieval recall@3: {hits}/{len(known)} ({hits / len(known):.1%})")
    for question, success in found:
        if not success:
            print(f"  MISS: {question}")
    if not args.live:
        print("Live answer checks skipped; run with --live only after approving cloud transfer of assignment facts.")
        return
    if not settings.allow_knowledge_export or not settings.gemini_api_key:
        raise SystemExit("Live evaluation requires GEMINI_API_KEY and ALLOW_KNOWLEDGE_EXPORT=true.")
    from backend.app.agent.service import chat, create_conversation
    correct = 0
    errors = 0
    selected = cases["single_turn"][:args.limit] if args.limit else cases["single_turn"]
    for item in selected:
        conversation_id = create_conversation()
        try:
            answer = chat(conversation_id, item["q"])["answer"]
        except Exception as error:
            errors += 1
            print(f"ERROR: {item['q']} -> {type(error).__name__}", flush=True)
            time.sleep(3)
            continue
        matched = item["expected"].lower() in answer.lower()
        correct += matched
        print(f"{'PASS' if matched else 'REVIEW'}: {item['q']}" + (f" -> {answer[:200]}" if not matched else ""), flush=True)
        time.sleep(1)
    print(f"Exact expected-fragment matches: {correct}/{len(selected)}; errors: {errors}. Manually review paraphrases and unsupported claims.", flush=True)
    if args.limit:
        return
    for item in cases["multi_turn"]:
        conversation_id = create_conversation()
        for turn in item["turns"]:
            answer = chat(conversation_id, turn)["answer"]
        print(f"MULTI-TURN: {item['turns']} -> {answer[:200]}")


if __name__ == "__main__":
    main()
