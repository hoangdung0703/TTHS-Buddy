"""Phase 3 Extension - end-to-end SSE stream test for the exact reported aggregate question,
against the real rag_service.stream_answer_question and real Qdrant (no mocks, no running HTTP
server needed - calls the generator directly).

Usage:
    python backend/evaluation/test_aggregate_e2e_stream.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.rag_service import RagAnswer, stream_answer_question  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402


async def main() -> int:
    settings = get_settings()
    client = QdrantClient(url=str(settings.qdrant_url), api_key=settings.qdrant_api_key, check_compatibility=False)

    question = "Bộ luật TTHS gồm bao nhiêu chương, bao nhiêu điều?"
    result = RagAnswer(
        answer="", citations=[], related_articles=[], suggested_followups=[],
        is_fallback=False, retrieved_chunks=[], used_academic_reference=False
    )

    events = []
    async for event_name, payload in stream_answer_question(question, uuid.uuid4(), settings, client, result, None):
        events.append((event_name, payload))

    print("Event sequence:", [e[0] for e in events])
    for name, payload in events:
        print(f"  {name}: {payload}")

    failures = []
    if [e[0] for e in events] != ["citations", "answer_delta", "suggested_followups", "done"]:
        failures.append(f"unexpected event sequence: {[e[0] for e in events]}")
    if result.is_fallback is not False:
        failures.append("should NOT be a fallback answer")
    if result.citations != []:
        failures.append("aggregate answer should have no citations (not a single-Dieu lookup)")
    if "35 chương" not in result.answer:
        failures.append(f"expected '35 chương' in answer, got: {result.answer!r}")
    if "điều" not in result.answer:
        failures.append(f"expected dieu count mentioned in answer: {result.answer!r}")

    print("\nFinal result.answer:")
    print(result.answer)

    if failures:
        print(f"\nFAIL - {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nE2E AGGREGATE STREAM TEST PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
