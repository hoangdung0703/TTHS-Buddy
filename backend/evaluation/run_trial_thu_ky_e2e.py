"""Chặng R2 - end-to-end Thư ký hearings, offline (no route, no database, no test account), real Gemini.

A scripted student plays Thư ký on fresh seeds: submits the prefilled step-1 report, advances through
steps 2-11, then writes parts IV.2 and IV.3 of the biên bản from the transcript (the first sentence of
each line of the section, as a hurried clerk would), runs the review, finalises and builds the record.

Reported (console: labels and counts only, never any text of the hearing): Gemini calls by type
(there must be no record_summary call), latency median/p90, guard pauses and rejected attempts,
measure-only flags (speaks_for_student), lengths of the clerk-written sections, notice codes, record
completeness. Records go to --out for a human reader.

HARD cap on Gemini calls (--hard-cap, default 50, never above 80), checked before every AI turn with
room for its worst case; stops at once on a Gemini 402/429 and after 3 guard pauses on one slot.

Usage (from backend/):  ../.venv/bin/python -m evaluation.run_trial_thu_ky_e2e --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

from app.core.config import create_qdrant_client, get_settings
from app.core.logging import configure_logging
from app.models.trial import CaseOptions
from app.services.trial_case_service import CaseGenerationFailed, create_case
from app.services.trial_clerk import (
    CLERK_SECTIONS,
    draft_of,
    report_prefill,
    review_draft,
    with_draft,
    with_finalized,
)
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_record import build_record, render_record_text
from app.services.trial_record_summary import SECTION_STEPS
from app.services.trial_repository import utc_now
from app.services.trial_session_service import shape_of
from app.services.trial_state_machine import ROLE_LABELS, new_session
from app.services.trial_turn_service import TrialContext, role_of
from evaluation.run_trial_probes import FIRST_SENTENCE, Cap, _p90, _record_complete, ai_until_user, calls, student

CONFIGS = (
    (9301, CaseOptions(crime_key="blhs_173", user_role="thu_ky", victim_present=True, witness_count=1)),
    (9302, CaseOptions(crime_key="blhs_134", user_role="thu_ky", victim_present=False, witness_count=1)),
)
MAX_CAP = 80
CASE_WORST_CASE = 3
SECTION_TARGET_CHARS = 3800


def scripted_section(ctx: TrialContext, key: str) -> str:
    """What a hurried clerk writes: who spoke and the first sentence of what they said, in order."""
    lines = []
    for u in ctx.transcript:
        if u.kind == "notice" or u.step not in SECTION_STEPS[key]:
            continue
        name = ctx.case.participants[u.speaker_id].name if u.speaker_id in ctx.case.participants else ""
        sentence = FIRST_SENTENCE.match(render(u.text, ctx.case.participants).strip()).group(0).strip()
        lines.append(f"{ROLE_LABELS.get(role_of(u.speaker_id), '')} {name} trình bày: {sentence}")
    text = "\n".join(lines)
    return text[:SECTION_TARGET_CHARS].rsplit("\n", 1)[0] if len(text) > SECTION_TARGET_CHARS else text


async def play(seed: int, options: CaseOptions, settings, qdrant, cap: int, recorders: list, out: Path) -> dict:
    case_recorder, recorder = TrialCallRecorder(), TrialCallRecorder()
    recorders += [case_recorder, recorder]
    if calls(recorders) + CASE_WORST_CASE > cap:
        raise Cap("cap reached before case generation")
    creation = await create_case(options, settings, qdrant, case_recorder, seed=seed)
    ctx = TrialContext(case=creation.case, pack=creation.pack, state=new_session("thu_ky", shape_of(creation.case)),
                       settings=settings, recorder=recorder)
    report = report_prefill(ctx.case, ctx.state.shape)
    student(ctx, "speak", text=report)
    events: list = []
    started = time.monotonic()
    while ctx.state.status == "active":
        await ai_until_user(ctx, recorders, cap, events)
        if ctx.state.status != "active":
            break
        student(ctx, "advance", target_step=ctx.state.current_step + 1)
    hearing_seconds = round(time.monotonic() - started, 1)

    work = with_draft(None, {key: scripted_section(ctx, key) for key in CLERK_SECTIONS}, utc_now())
    draft = draft_of(work)
    notices = review_draft(ctx.case, ctx.transcript, draft)
    work = with_finalized(work, utc_now())
    record = build_record(ctx.case, ctx.transcript, None, None, clerk=draft_of(work).sections(),
                          draft=not draft_of(work).finalized)
    (out / f"record_{seed}.txt").write_text(render_record_text(record), encoding="utf-8")

    flags: dict[str, int] = {}
    for u in ctx.transcript:
        for f in u.guard_flags:
            flags[f.split(":")[0]] = flags.get(f.split(":")[0], 0) + 1
    rejected: dict[str, int] = {}
    for r in recorder.records:
        if not r.accepted:
            for label in {v.split(":")[0] for v in r.guard_violations}:
                rejected[label] = rejected.get(label, 0) + 1
    codes: dict[str, int] = {}
    for n in notices:
        codes[f"{n.section}:{n.code}"] = codes.get(f"{n.section}:{n.code}", 0) + 1
    return {
        "seed": seed, "crime": options.crime_key, "case_attempts": creation.attempts,
        "completed": ctx.state.status == "completed", "hearing_seconds": hearing_seconds,
        "case_calls": len(case_recorder.records), "hearing_calls": len(recorder.records),
        "calls_by_type": {t: sum(1 for r in recorder.records if r.call_type == t)
                          for t in sorted({r.call_type for r in recorder.records})},
        "rejected_attempts": sum(not r.accepted for r in recorder.records), "rejected_labels": rejected,
        "guard_pauses": len([e for e in events if "guard_pause" in e]),
        "utterance_flags": flags,
        "clerk_utterances": sum(u.is_user for u in ctx.transcript),
        "report_chars": len(report),
        "section_chars": {k: len(v) for k, v in draft.sections().items()},
        "notices": codes,
        "record": _record_complete(record),
        "record_iv_content": [s.content for s in record.sections[-1].subsections],
        "record_draft": record.draft,
    }


async def main(out: Path, cap: int) -> int:
    configure_logging("test")  # INFO + redaction; never DEBUG
    cap = min(cap, MAX_CAP)
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    out.mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    rows, stopped = [], None
    for seed, options in CONFIGS:
        try:
            rows.append(await play(seed, options, settings, qdrant, cap, recorders, out))
        except (Cap, CaseGenerationFailed) as stop:
            rows.append({"seed": seed, "crime": options.crime_key, "stopped": type(stop).__name__})
            if isinstance(stop, Cap):
                stopped = str(stop)
                break
        except httpx.HTTPStatusError as error:
            if error.response.status_code in (402, 429):
                stopped = f"Gemini {error.response.status_code} - stopped"
                break
            raise
    records = [r for rec in recorders for r in rec.records]
    hearing = [r for r in records if r.call_type != "case_generation"]
    latencies = [r.latency_seconds for r in hearing]
    report = {
        "gemini_calls": len(records), "cap": cap, "stopped": stopped,
        "record_summary_calls": sum(r.call_type == "record_summary" for r in records),
        "tokens": {"prompt": sum(r.prompt_tokens for r in records), "output": sum(r.output_tokens for r in records),
                   "thinking": sum(r.thinking_tokens for r in records)},
        "hearing_call_latency": {"median": statistics.median(latencies) if latencies else None, "p90": _p90(latencies)},
        "sessions": rows,
    }
    (out / "thu_ky_e2e.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hard-cap", type=int, default=50)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.out, args.hard_cap)))
