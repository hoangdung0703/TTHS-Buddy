"""HyDE on/off retrieval experiment over backend/evaluation/hyde_diagnostic_set.json (requirements.md
Muc 4). Read-only with respect to behaviour: the default is untouched, the "off" arm uses the
experiment-only RAG_EXPERIMENT_DISABLE_HYDE switch in rag_service.retrieve_context.

Design - PAIRED: each run calls query understanding ONCE (with the case's prior turns, as the chat
route would), then retrieves for that same rewritten question with HyDE on and with HyDE off, in
alternating order across runs. The two arms therefore differ only by HyDE, not by query-rewrite
variance. Multi-part questions follow the chat route's own rule (>= 2 sub-questions and no
anonymisation -> one retrieval per sub-question).

Measures, per case and arm: whether each expected Dieu reaches legal_primary, its rank there
(1-based, among DISTINCT Dieu in legal_primary order), and retrieval latency (retrieval only - query
understanding excluded). Prints numbers and ids only - never question, rewrite or answer text.

Usage: ENVIRONMENT=test .venv/bin/python evaluation/run_hyde_experiment.py [runs=5]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
logging.disable(logging.CRITICAL)

from app.core.config import create_qdrant_client, get_settings  # noqa: E402
from app.services import rag_service as R  # noqa: E402
from app.services.query_understanding_service import rewrite_question  # noqa: E402

SET_PATH = Path(__file__).resolve().parent / "hyde_diagnostic_set.json"
RESULTS_PATH = Path(__file__).resolve().parent / "hyde_experiment_results.json"


def distinct_dieu(chunks: list) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for c in chunks:
        key = (c.payload["dieu_number"], c.payload["source_document"])
        if key not in seen:
            seen.append(key)
    return seen


async def retrieve(rewritten: str, sub_questions: list[str] | None, needs_anon: bool, hyde_on: bool,
                   settings, qdrant):
    if hyde_on:
        os.environ.pop(R.HYDE_EXPERIMENT_DISABLE_ENV, None)
    else:
        os.environ[R.HYDE_EXPERIMENT_DISABLE_ENV] = "1"
    try:
        started = time.monotonic()
        if sub_questions and len(sub_questions) >= 2 and not needs_anon:
            results = await R.retrieve_context_for_subquestions(sub_questions, settings, qdrant)
        else:
            results = [await R.retrieve_context(rewritten, settings, qdrant)]
        return results, time.monotonic() - started
    finally:
        os.environ.pop(R.HYDE_EXPERIMENT_DISABLE_ENV, None)


def score(results, expected: list[dict]) -> list[dict]:
    out = []
    for exp in expected:
        key = (exp["dieu_number"], exp["source_document"])
        ranks = [distinct_dieu(r.legal_primary).index(key) + 1 for r in results if key in distinct_dieu(r.legal_primary)]
        out.append({"dieu": exp["dieu_number"], "in_primary": bool(ranks), "rank": min(ranks) if ranks else None})
    return out


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    cases = json.loads(SET_PATH.read_text(encoding="utf-8"))["cases"]
    records = []
    for i in range(runs):
        for case in cases:
            turns = [{"question": t["question"], "answer": t["answer"]} for t in case.get("prior_turns", [])]
            qu = rewrite_question(case["question"], turns, settings, False)
            subs = getattr(qu, "sub_questions", None) or None
            arms = (True, False) if i % 2 == 0 else (False, True)
            for hyde_on in arms:
                results, seconds = asyncio.run(retrieve(qu.rewritten_question, subs, qu.needs_anonymization,
                                                        hyde_on, settings, qdrant))
                records.append({"case": case["id"], "property": case["property"], "run": i + 1,
                                "hyde": "on" if hyde_on else "off", "intent": qu.intent,
                                "multipart_subquestions": len(subs) if subs and len(subs) >= 2 else 0,
                                "retrieval_seconds": round(seconds, 3), "expected": score(results, case["expected"])})
            print(f"  run {i + 1}/{runs}  {case['id']}", flush=True)

    summary = {}
    for case in cases:
        summary[case["id"]] = {}
        for arm in ("on", "off"):
            rs = [r for r in records if r["case"] == case["id"] and r["hyde"] == arm]
            summary[case["id"]][arm] = {
                "n": len(rs),
                "retrieval_seconds_median": round(statistics.median(r["retrieval_seconds"] for r in rs), 2),
                "intents": sorted({r["intent"] for r in rs}),
                "per_expected": {
                    e["dieu_number"]: {
                        "in_primary": sum(1 for r in rs for x in r["expected"] if x["dieu"] == e["dieu_number"] and x["in_primary"]),
                        "ranks": [x["rank"] for r in rs for x in r["expected"] if x["dieu"] == e["dieu_number"]],
                    } for e in case["expected"]
                },
            }
    RESULTS_PATH.write_text(json.dumps({"runs": runs, "summary": summary, "records": records},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'case':30s} {'arm':4s} {'n':>2s}  {'Dieu: in primary (ranks)':48s} retrieval median")
    for case in cases:
        for arm in ("on", "off"):
            s = summary[case["id"]][arm]
            hits = "  ".join(f"{d}: {v['in_primary']}/{s['n']} {v['ranks']}" for d, v in s["per_expected"].items())
            print(f"{case['id']:30s} {arm:4s} {s['n']:>2d}  {hits:48s} {s['retrieval_seconds_median']:.2f}s")
    for arm in ("on", "off"):
        lat = [r["retrieval_seconds"] for r in records if r["hyde"] == arm]
        print(f"\nall cases, HyDE {arm}: retrieval median {statistics.median(lat):.2f}s  "
              f"p90 {sorted(lat)[int(0.9 * len(lat))]:.2f}s  (n={len(lat)})")
    print(f"\nresults written to {RESULTS_PATH.name}")


if __name__ == "__main__":
    main()
