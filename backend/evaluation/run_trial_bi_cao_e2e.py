"""Chặng R3 - end-to-end Bị cáo hearings, offline (no route, no database, no test account), real Gemini.

A scripted student plays Bị cáo on fresh seeds and goes through all 11 steps the way the frontend
would: it reads `pending_question` and `allowed_actions` from state_out, answers each question put to
it (the identity question with the prefill, the others with canned answers), declines at least one
question in the first session, adds to the defence and argues in step 8 in the first session and
skips both in the second, and says its last words.

Reported (console: labels and counts only, never any text of the hearing): Gemini calls by type and
slot, latency median/p90, guard pauses and rejected attempts with their labels, questions put to the
student per slot (and how many code had to ask itself), declines, measure-only flags
(speaks_for_student, question_trimmed, user_amount_off_file), record completeness. Records go to
--out for a human reader, and so does flags_<seed>.json: every AI line flagged speaks_for_student,
verbatim, with the two utterances before it, for a person to classify (true or false positive).
--out must lie OUTSIDE the repository: these files hold hearing text and are never committed or
printed.

HARD cap on Gemini calls (--hard-cap, default 50, never above 80), checked before every AI turn with
room for its worst case; stops at once on a Gemini 402/429 and after 3 guard pauses on one slot.

Usage (from backend/):  ../.venv/bin/python -m evaluation.run_trial_bi_cao_e2e --out <dir>
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
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_record import build_record, render_record_text
from app.services.trial_record_summary import summarise_record
from app.services.trial_session_service import shape_of, state_out
from app.services.trial_state_machine import ROLE_LABELS, current_slot, new_session
from app.services.trial_turn_service import STUDENT_QUESTION_FLAG, TrialContext, role_of
from evaluation.run_trial_probes import Cap, _p90, _record_complete, ai_until_user, calls, student

CONFIGS = (
    # (seed, options, play_optional_turns)
    (9401, CaseOptions(crime_key="blhs_173", user_role="bi_cao", victim_present=True, witness_count=1), True),
    (9402, CaseOptions(crime_key="blhs_134", user_role="bi_cao", victim_present=False, witness_count=1), False),
)
MAX_CAP = 80
CASE_WORST_CASE = 3
SUMMARY_WORST_CASE = 2
SESSION_ID = "00000000-0000-0000-0000-000000000000"
ANSWERS = (
    "Dạ, tôi xin trình bày đúng như lời khai của tôi tại cơ quan điều tra.",
    "Dạ, lúc đó tôi đang túng quẫn nên mới làm như vậy, tôi rất hối hận.",
    "Dạ, tôi không nhớ rõ chi tiết đó, chỉ nhớ đại khái như trong hồ sơ.",
    "Dạ, sau đó tôi đã xin lỗi và mong được bồi thường cho bị hại.",
)
ADD_DEFENCE = ("Tôi xin bổ sung: tôi là lao động chính trong gia đình, lần đầu vi phạm và đã thật sự ăn năn. Kính "
               "mong Hội đồng xét xử xem xét giảm nhẹ hình phạt cho tôi.")
ARGUE = ("Tôi không đồng ý với mức hình phạt Kiểm sát viên đề nghị vì tôi đã khắc phục một phần hậu quả và thành "
         "khẩn khai báo. Đề nghị Hội đồng xét xử cho tôi được hưởng mức án nhẹ hơn.")
LAST_WORDS = "Tôi biết mình đã sai. Kính mong Hội đồng xét xử khoan hồng để tôi sớm trở về lo cho gia đình."


FLAG_CONTEXT = 2


def save_flagged(ctx: TrialContext, path: Path) -> int:
    """Writes each AI line flagged speaks_for_student, verbatim with the FLAG_CONTEXT utterances before
    it, for manual classification. Hearing text: the file stays outside the repository, unprinted."""
    def shown(u) -> dict:
        return {"seq": u.seq, "step": u.step, "speaker": ROLE_LABELS.get(role_of(u.speaker_id), u.speaker_id),
                "is_user": u.is_user, "kind": u.kind, "flags": u.guard_flags,
                "text": u.text if u.is_user else render(u.text, ctx.case.participants)}
    items = []
    for i, u in enumerate(ctx.transcript):
        if not u.is_user and "speaks_for_student" in u.guard_flags:
            items.append({"flagged": shown(u),
                          "before": [shown(b) for b in ctx.transcript[max(0, i - FLAG_CONTEXT):i]]})
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(items)


async def play(seed: int, options: CaseOptions, optional: bool, settings, qdrant, cap: int, recorders: list,
               out: Path) -> dict:
    case_recorder, recorder = TrialCallRecorder(), TrialCallRecorder()
    recorders += [case_recorder, recorder]
    if calls(recorders) + CASE_WORST_CASE > cap:
        raise Cap("cap reached before case generation")
    creation = await create_case(options, settings, qdrant, case_recorder, seed=seed)
    ctx = TrialContext(case=creation.case, pack=creation.pack, state=new_session("bi_cao", shape_of(creation.case)),
                       settings=settings, recorder=recorder)
    events: list = []
    answered: dict[str, int] = {}
    declines = 0
    started = time.monotonic()
    cap_stop = None
    try:   # a cap hit mid-hearing still reports and saves what was played
        while ctx.state.status == "active":
            await ai_until_user(ctx, recorders, cap, events)
            if ctx.state.status != "active":
                break
            view = state_out(SESSION_ID, ctx.state, case=ctx.case, transcript=ctx.transcript)
            actions, question = view.allowed_actions, view.pending_question
            if question is not None:
                key = current_slot(ctx.state).key
                answered[key] = answered.get(key, 0) + 1
                if key == "loi_sau_cung":
                    student(ctx, "speak", text=LAST_WORDS)
                elif "decline" in actions and optional and declines == 0:
                    student(ctx, "decline")
                    declines += 1
                else:
                    student(ctx, "speak", text=question.prefill or ANSWERS[sum(answered.values()) % len(ANSWERS)])
            elif actions and actions[0].startswith("advance:"):
                student(ctx, "advance", target_step=ctx.state.current_step + 1)
            elif "end_slot" in actions and not optional:
                student(ctx, "end_slot")
            else:   # the optional turns of steps 7 and 8
                student(ctx, "speak", text=ADD_DEFENCE if ctx.state.current_step == 7 else ARGUE)
    except Cap as stop:
        cap_stop = str(stop)
    hearing_seconds = round(time.monotonic() - started, 1)
    if ctx.state.status == "completed":
        if calls(recorders) + SUMMARY_WORST_CASE > cap:
            cap_stop = "cap reached before the record summary"
        else:
            ctx.record_summary = await summarise_record(ctx)
    record = build_record(ctx.case, ctx.transcript, None, None, summary=ctx.record_summary)
    (out / f"record_{seed}.txt").write_text(render_record_text(record), encoding="utf-8")
    flagged = save_flagged(ctx, out / f"flags_{seed}.json")

    flags: dict[str, int] = {}
    for u in ctx.transcript:
        for f in u.guard_flags:
            flags[f.split(":")[0]] = flags.get(f.split(":")[0], 0) + 1
    rejected: dict[str, int] = {}
    for r in recorder.records:
        if not r.accepted:
            for label in {v.split(":")[0] for v in r.guard_violations}:
                rejected[label] = rejected.get(label, 0) + 1
    return {
        "seed": seed, "crime": options.crime_key, "case_attempts": creation.attempts, "stopped": cap_stop,
        "last_step": ctx.state.current_step,
        "completed": ctx.state.status == "completed", "hearing_seconds": hearing_seconds,
        "case_calls": len(case_recorder.records), "hearing_calls": len(recorder.records),
        "calls_by_type": {t: sum(1 for r in recorder.records if r.call_type == t)
                          for t in sorted({r.call_type for r in recorder.records})},
        "calls_by_slot": {s: sum(1 for r in recorder.records if r.slot == s)
                          for s in sorted({r.slot for r in recorder.records})},
        "rejected_attempts": sum(not r.accepted for r in recorder.records), "rejected_labels": rejected,
        "guard_pauses": len([e for e in events if "guard_pause" in e]),
        "questions_to_student": answered,
        "questions_by_code": sum("question_fallback" in u.guard_flags for u in ctx.transcript),
        "student_utterances": sum(u.is_user for u in ctx.transcript), "declines": declines,
        "ai_utterances_as_student": sum(u.speaker_id == "BI_CAO" and not u.is_user for u in ctx.transcript),
        "flags": flags, "speaks_for_student_saved": flagged,
        "student_question_flags": sum(STUDENT_QUESTION_FLAG in u.guard_flags for u in ctx.transcript),
        "verdict_guilty": ctx.verdict.guilty if ctx.verdict else None,
        "record": _record_complete(record),
        "record_iv_content": [s.content for s in record.sections[-1].subsections],
    }


async def main(out: Path, cap: int) -> int:
    configure_logging("test")  # INFO + redaction; never DEBUG
    cap = min(cap, MAX_CAP)
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    out.mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    rows, stopped = [], None
    for seed, options, optional in CONFIGS:
        try:
            rows.append(await play(seed, options, optional, settings, qdrant, cap, recorders, out))
            if rows[-1]["stopped"]:
                stopped = rows[-1]["stopped"]
                break
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
    dialogue = [r.latency_seconds for r in hearing if r.call_type == "dialogue"]
    report = {
        "gemini_calls": len(records), "cap": cap, "stopped": stopped,
        "tokens": {"prompt": sum(r.prompt_tokens for r in records), "output": sum(r.output_tokens for r in records),
                   "thinking": sum(r.thinking_tokens for r in records)},
        "hearing_call_latency": {"median": statistics.median(latencies) if latencies else None, "p90": _p90(latencies)},
        "dialogue_call_latency": {"median": statistics.median(dialogue) if dialogue else None, "p90": _p90(dialogue)},
        "sessions": rows,
    }
    (out / "bi_cao_e2e.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hard-cap", type=int, default=50)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.out, args.hard_cap)))
