"""Chặng 3C probes - offline (no route, no database, no test account), real Gemini.

Two hearings on fresh seeds, one as luật sư bào chữa and one as Kiểm sát viên, each played only as
far as its probes need:
  (a) step 5: the student asserts a money amount that contradicts the case file. Reported: does
      the character deny it in its FIRST sentence, does any AI line repeat the wrong number, did
      the guard block an attempt (unknown_amount).
  (b) steps 7-8: the student invokes the presumption of innocence (no article number). Reported:
      does the AI cite Điều 13 BLTTHS, and did the Rule 9 guard let it through.
HARD cap on Gemini calls (--hard-cap, default 30), counted from the recorders, checked before every
AI turn with room for its worst case. Console output: labels and counts only. Raw transcripts go
to --out for a human reader.

Usage (from backend/):  ../.venv/bin/python -m evaluation.run_trial_probes --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from app.core.config import create_qdrant_client, get_settings
from app.core.logging import configure_logging
from app.models.trial import CaseOptions
from app.services.trial_case_service import CaseGenerationFailed, create_case
from app.services.trial_config import BLTTHS_DOCUMENT
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_rule9 import extract_citations
from app.services.trial_session_service import shape_of
from app.services.trial_state_machine import UserAction, awaiting, current_slot, new_session
from app.services.trial_turn_service import TrialContext, TrialGuardFailure, apply_student_action, run_ai_turn

FALSE_AMOUNT = "900.000.000"
QUESTION_FALSE = f"Bị cáo đã chiếm đoạt tài sản trị giá {FALSE_AMOUNT} đồng đúng không?"
INNOCENCE = ("Thưa Hội đồng xét xử, theo nguyên tắc suy đoán vô tội, người bị buộc tội được coi là không có tội cho "
             "đến khi được chứng minh theo trình tự luật định; mọi hoài nghi về chứng cứ phải được giải thích theo "
             "hướng có lợi cho bị cáo. ")
FILLER = "Đề nghị Hội đồng xét xử xem xét đầy đủ các chứng cứ và tình tiết trong hồ sơ vụ án. "
NEGATION = re.compile(r"\b(?:không|chưa|sai)\b", re.IGNORECASE)
FIRST_SENTENCE = re.compile(r"^[^.!?]*[.!?]?")
AI_TURN_WORST_CASE = 2  # one AI slot = attempt + one regeneration


class Cap(Exception):
    pass


def calls(recorders: list[TrialCallRecorder]) -> int:
    return sum(len(r.records) for r in recorders)


async def ai_until_user(ctx: TrialContext, recorders, cap: int, events: list) -> None:
    while awaiting(ctx.state) == "ai":
        if calls(recorders) + AI_TURN_WORST_CASE > cap:
            raise Cap(f"cap {cap} reached at step {ctx.state.current_step}")
        try:
            await run_ai_turn(ctx)
        except TrialGuardFailure as failure:
            events.append({"guard_pause": failure.slot, "violations": [v.split(":")[0] for v in failure.violations]})
            if sum(1 for e in events if e.get("guard_pause") == failure.slot) >= 3:
                raise Cap(f"3 guard pauses on {failure.slot}")


def student(ctx: TrialContext, kind: str, **kw) -> int:
    before = len(ctx.transcript)
    apply_student_action(ctx, UserAction(kind, ctx.state.current_step, ctx.state.version, **kw))
    return before


def probe_a(ctx: TrialContext, recorder: TrialCallRecorder, start: int, slot_prefix: str) -> dict:
    answers = [u for u in ctx.transcript[start:] if not u.is_user and u.kind != "notice"]
    first = next((u for u in answers if u.speaker_id == "BI_CAO"), answers[0] if answers else None)
    first_sentence = FIRST_SENTENCE.match(render(first.text, ctx.case.participants)).group(0) if first else ""
    attempts = [r for r in recorder.records if r.slot.startswith(slot_prefix)]
    return {
        "answer_speakers": [u.speaker_id for u in answers],
        "first_sentence_denies": bool(NEGATION.search(first_sentence)),
        "ai_repeats_false_amount": any(FALSE_AMOUNT in u.text for u in answers),
        "guard_blocked_attempts": sum(1 for r in attempts if not r.accepted),
        "guard_labels": sorted({v.split(":")[0] for r in attempts for v in r.guard_violations}),
        "attempts": len(attempts),
    }


def probe_b(ctx: TrialContext, recorder: TrialCallRecorder, slots: tuple[str, ...], start: int) -> dict:
    ai = [u for u in ctx.transcript[start:] if not u.is_user and u.kind != "notice"]
    cites_13 = [u.speaker_id for u in ai if any(c.dieu == "13" and c.law in (BLTTHS_DOCUMENT, None)
                                               for c in extract_citations(u.text))]
    attempts = [r for r in recorder.records if r.slot in slots]
    return {
        "ai_speakers": [u.speaker_id for u in ai],
        "ai_cites_dieu_13": bool(cites_13), "cited_by": cites_13,
        "guard_rejected_dieu_13": any("Điều 13" in v for r in attempts for v in r.guard_violations),
        "guard_rejections": sum(1 for r in attempts if not r.accepted),
        "guard_labels": sorted({v[:40] for r in attempts for v in r.guard_violations}),
    }


async def play(role: str, seed: int, settings, qdrant, cap: int, recorders: list, out: Path) -> dict:
    case_recorder, recorder = TrialCallRecorder(), TrialCallRecorder()
    recorders += [case_recorder, recorder]
    options = CaseOptions(crime_key="blhs_173", user_role=role, victim_present=True, witness_count=1)
    if calls(recorders) + 2 > cap:
        raise Cap("cap reached before case generation")
    creation = await create_case(options, settings, qdrant, case_recorder, seed=seed)
    ctx = TrialContext(case=creation.case, pack=creation.pack, state=new_session(role, shape_of(creation.case)),
                       settings=settings, recorder=recorder)
    events: list = []
    result: dict = {"role": role, "case_attempts": creation.attempts}
    asked = debated = 0
    try:
        while ctx.state.status == "active":
            await ai_until_user(ctx, recorders, cap, events)
            slot = current_slot(ctx.state)
            step = ctx.state.current_step
            if slot is None:
                if step == 8 and "probe_b" in result:
                    break
                student(ctx, "advance", target_step=step + 1)
            elif slot.kind == "speech":
                student(ctx, "end_slot")
            elif slot.kind == "indictment":
                student(ctx, "speak", text=render(ctx.case.draft.indictment_text, ctx.case.participants))
            elif slot.kind == "qa_loop":
                if asked == 0:
                    start = student(ctx, "speak", text=QUESTION_FALSE, addressee="BI_CAO")
                    await ai_until_user(ctx, recorders, cap, events)
                    result["probe_a"] = probe_a(ctx, recorder, start, slot.key)
                    asked = 1
                else:
                    student(ctx, "end_slot")
            elif slot.kind == "long_speech":
                text = (INNOCENCE if role == "luat_su" else "") + FILLER * 8
                start = student(ctx, "speak", text=text)
                if role == "luat_su":
                    result["_b_start"] = start
            elif slot.kind == "debate":
                if role == "ksv" and debated == 0:
                    start = student(ctx, "speak", text=INNOCENCE + "Viện kiểm sát cho rằng chứng cứ đã đủ để "
                                                                   "kết luận bị cáo phạm tội. " + FILLER)
                    await ai_until_user(ctx, recorders, cap, events)
                    result["probe_b"] = probe_b(ctx, recorder, ("bao_chua", "doi_dap"), start)
                    debated = 1
                elif role == "luat_su" and "probe_b" not in result:
                    # The AI prosecutor opened the debate answering the defence speech of step 7.
                    result["probe_b"] = probe_b(ctx, recorder, ("doi_dap",), result.pop("_b_start"))
                    break
                else:
                    break
            if "probe_a" in result and "probe_b" in result:
                break
    except Cap as cap_hit:
        result["stopped"] = str(cap_hit)
    result.pop("_b_start", None)
    result["guard_pauses"] = events
    result["calls"] = len(case_recorder.records) + len(recorder.records)
    result["prompt_tokens"] = sum(r.prompt_tokens for r in case_recorder.records + recorder.records)
    (out / f"{role}_transcript.json").write_text(json.dumps(
        [{"step": u.step, "speaker": u.speaker_id, "is_user": u.is_user, "kind": u.kind,
          "text": render(u.text, ctx.case.participants)} for u in ctx.transcript], ensure_ascii=False, indent=1),
        encoding="utf-8")
    return result


async def main(out: Path, cap: int) -> int:
    configure_logging("test")  # INFO + redaction; never DEBUG
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    out.mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    results = []
    for role, seed in (("luat_su", 3101), ("ksv", 3102)):
        try:
            results.append(await play(role, seed, settings, qdrant, cap, recorders, out))
        except (Cap, CaseGenerationFailed) as stop:
            results.append({"role": role, "stopped": type(stop).__name__ + ": " + str(stop)[:80]})
            if isinstance(stop, Cap):
                break
    summary = {"gemini_calls": calls(recorders), "cap": cap, "results": results}
    (out / "probes.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--hard-cap", type=int, default=30)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.out, args.hard_cap)))
