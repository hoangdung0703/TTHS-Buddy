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

--format (chặng 3D) measures layout instead:
  - cases on seeds 4001-4006 (the A5-bis option mix): schema pass, first-pass rate, indictments with
    all four section headings on their own lines (counted by code), median generation time;
  - the 4 long slots (luận tội, bào chữa, đối đáp, tuyên án) on the first 2 cases, each run once on
    an empty transcript: share of outputs with at least 3 paragraphs.

--summary (chặng 3E):
  - cases on seeds 5001-5006: schema pass, first pass, cases caught by the no-diacritics check,
    median generation time;
  - one full hearing as KSV on the first valid case (2 questions, 1 debate line), then the biên bản
    summary call: tokens, latency, guard labels, verbatim fallbacks. 2 calls are kept for the
    summary under the cap.

--observer (chặng R1): 3 full Người xem hearings (seeds 9201-9203, Điều 173/134/174) with the biên bản
summary: calls, tokens, latency, guard labels, paragraph layout of long speeches, overlap of the AI-AI
đối đáp with luận tội/bào chữa, completeness of the Mẫu 22-HS record. Records go to --out/observer.

Usage (from backend/):  ../.venv/bin/python -m evaluation.run_trial_probes --out <dir> [--format|--summary|--observer]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

import httpx

from app.core.config import create_qdrant_client, get_settings
from app.core.logging import configure_logging
from app.models.trial import CaseOptions
from app.services.trial_case_service import CaseGenerationFailed, create_case, load_pack_for_crime
from app.services.trial_config import BLTTHS_DOCUMENT, get_crime
from app.services.trial_knobs import choose_knobs
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_rule9 import extract_citations
from app.services.trial_session_service import shape_of
from app.services.trial_record import build_record, render_record_text
from app.services.trial_state_machine import STEPS, UserAction, awaiting, current_slot, new_session
from app.services.trial_text_format import INDICTMENT_SECTIONS, indictment_sections, paragraphs
from app.services.trial_record_summary import section_sources, summarise_record
from app.services.trial_turn_service import TrialContext, TrialGuardFailure, apply_student_action, run_ai_turn
from evaluation.run_trial_spike import BIS_CONFIGS, scripted_lines

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


DIACRITIC_ERROR = "tiếng Việt có dấu"
FORMAT_SEED_OFFSET = 2000   # BIS_CONFIGS seeds 2001-2006 -> 4001-4006, never tuned against
FORMAT_CASES = 6
FORMAT_SLOT_CASES = 2
# (slot key, student role): the role is chosen so that the AI is the speaker of the slot.
LONG_SLOTS = (("luan_toi", "luat_su"), ("bao_chua", "ksv"), ("doi_dap", "luat_su"), ("tuyen_an", "luat_su"))
SLOT_WORST_CASE = {"tuyen_an": 4}   # nghị án + tuyên án, each with one regeneration


def _slot_position(key: str) -> tuple[int, int]:
    return next((step.number, i) for step in STEPS for i, slot in enumerate(step.slots) if slot.key == key)


def _configs(seed_offset: int) -> list:
    return [(seed + seed_offset, options, forced) for seed, options, forced in BIS_CONFIGS[:FORMAT_CASES]]


async def _generate_cases(configs: list, settings, qdrant, cap: int, recorders: list, out: Path,
                          cases: list, case_rows: list) -> None:
    for seed, options, forced in configs:
        if calls(recorders) + 2 > cap:
            raise Cap("cap reached before case generation")
        recorder = TrialCallRecorder()
        recorders.append(recorder)
        started = time.monotonic()
        pack = await load_pack_for_crime(get_crime(options.crime_key), settings, qdrant)
        knobs = choose_knobs(get_crime(options.crime_key), pack, random.Random(seed), **forced) if forced else None
        try:
            creation = await create_case(options, settings, qdrant, recorder, pack=pack, seed=seed, knobs=knobs)
        except CaseGenerationFailed as failure:
            case_rows.append({"seed": seed, "crime": options.crime_key, "ok": False,
                              "errors_per_attempt": failure.error_counts, "calls": len(recorder.records),
                              "labels_per_attempt": [r.guard_violations for r in recorder.records],
                              **_tokens(recorder), "seconds": round(time.monotonic() - started, 1),
                              "no_diacritics_caught": any(DIACRITIC_ERROR in e for es in failure.errors for e in es),
                              "no_diacritics_last_attempt": any(DIACRITIC_ERROR in e for e in failure.errors[-1])})
            continue
        sections = indictment_sections(creation.case.draft.indictment_text)
        case_rows.append({"seed": seed, "crime": options.crime_key, "ok": True, "attempts": creation.attempts,
                          "labels_per_attempt": [r.guard_violations for r in recorder.records], **_tokens(recorder),
                          "errors_per_attempt": [len(e) for e in creation.errors_per_attempt],
                          "no_diacritics_caught": any(DIACRITIC_ERROR in e for es in creation.errors_per_attempt
                                                      for e in es),
                          "sections": len(sections), "all_sections": len(sections) == len(INDICTMENT_SECTIONS),
                          "indictment_paragraphs": len(paragraphs(creation.case.draft.indictment_text)),
                          "seconds": round(time.monotonic() - started, 1), "calls": len(recorder.records)})
        cases.append(creation)
        (out / "cases" / f"case_{seed}.json").write_text(creation.case.model_dump_json(indent=1), encoding="utf-8")


def _tokens(recorder: TrialCallRecorder) -> dict:
    return {"prompt_tokens": sum(r.prompt_tokens for r in recorder.records),
            "output_tokens": sum(r.output_tokens for r in recorder.records),
            "thinking_tokens": sum(r.thinking_tokens for r in recorder.records)}


def _p90(values: list[float]) -> float | None:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))] if ordered else None


def _case_summary(case_rows: list) -> dict:
    ok = [r for r in case_rows if r["ok"]]
    seconds = [r["seconds"] for r in case_rows if "seconds" in r]
    label_table: dict[str, dict[str, int]] = {}
    for r in case_rows:
        for attempt, labels in enumerate(r.get("labels_per_attempt", []), 1):
            for label in set(labels):
                label_table.setdefault(label, {}).setdefault(f"attempt_{attempt}", 0)
                label_table[label][f"attempt_{attempt}"] += 1
    return {"total": len(case_rows), "schema_ok": len(ok), "first_pass": sum(1 for r in ok if r["attempts"] == 1),
            "calls_per_case": round(sum(r["calls"] for r in case_rows) / len(case_rows), 2) if case_rows else None,
            "tokens_per_case_mean": {k: round(sum(r.get(k, 0) for r in case_rows) / len(case_rows))
                                     for k in ("prompt_tokens", "output_tokens", "thinking_tokens")} if case_rows else None,
            "seconds_all_median": statistics.median(seconds) if seconds else None, "seconds_all_p90": _p90(seconds),
            "failed_cases": [{"seed": r["seed"], "crime": r["crime"], "labels": r.get("labels_per_attempt")}
                             for r in case_rows if not r["ok"]],
            "label_table": dict(sorted(label_table.items(), key=lambda kv: -sum(kv[1].values()))),
            "no_diacritics_caught": sum(1 for r in case_rows if r["no_diacritics_caught"]),
            "all_four_sections": sum(1 for r in ok if r["all_sections"]),
            "median_seconds": statistics.median(r["seconds"] for r in ok) if ok else None, "rows": case_rows}


SUMMARY_SEED_OFFSET = 3000   # 5001-5006
SUMMARY_RESERVE = 2          # the biên bản summary: attempt + one regeneration


async def _play_short_ksv(ctx: TrialContext, recorders: list, cap: int, events: list) -> None:
    """Full hearing as KSV with the spike's scripted lines, trimmed to 2 questions and 1 debate line."""
    lines = scripted_lines(ctx)
    questions = [q for q in lines["questions"] if "tuyên án" not in q[1]][:2]
    debate = lines["debate"][1:2]          # without the spike's fabricated-citation probe
    while ctx.state.status == "active":
        await ai_until_user(ctx, recorders, cap, events)
        if ctx.state.status != "active":
            break
        slot = current_slot(ctx.state)
        if slot is None:
            student(ctx, "advance", target_step=ctx.state.current_step + 1)
        elif slot.key == "y_kien_ksv_thay_doi":
            student(ctx, "speak", text=lines["objection"])
        elif slot.key == "cong_bo_cao_trang":
            student(ctx, "speak", text=lines["indictment"])
        elif slot.key == "ksv_hoi":
            if questions:
                addressee, text = questions.pop(0)
                student(ctx, "speak", text=text, addressee=addressee)
            else:
                student(ctx, "end_slot")
        elif slot.key == "luan_toi":
            student(ctx, "speak", text=lines["luan_toi"])
        elif slot.key == "doi_dap" and debate:
            student(ctx, "speak", text=debate.pop(0))
        elif slot.key == "doi_dap":
            student(ctx, "end_slot")
        else:
            raise Cap(f"unscripted slot {slot.key}")


async def summary_main(out: Path, cap: int) -> int:
    configure_logging("test")
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    cases, case_rows, stopped, session = [], [], None, {}
    try:
        await _generate_cases(_configs(SUMMARY_SEED_OFFSET), settings, qdrant, cap - SUMMARY_RESERVE, recorders, out, cases,
                              case_rows)
        if cases:
            creation = cases[0]
            recorder = TrialCallRecorder()
            recorders.append(recorder)
            ctx = TrialContext(case=creation.case, pack=creation.pack,
                               state=new_session("ksv", shape_of(creation.case)), settings=settings, recorder=recorder)
            events: list = []
            try:
                await _play_short_ksv(ctx, recorders, cap - SUMMARY_RESERVE, events)
            except Cap as cap_hit:
                session["stopped"] = str(cap_hit)
            session.update({"crime": creation.case.crime_key, "status": ctx.state.status,
                            "hearing_calls": len(recorder.records), "guard_pauses": events})
            if ctx.state.status == "completed":
                result = await summarise_record(ctx)
                summary_calls = [r for r in recorder.records if r.call_type == "record_summary"]
                session["summary"] = {
                    "calls": len(summary_calls),
                    "prompt_tokens": [r.prompt_tokens for r in summary_calls],
                    "output_tokens": [r.output_tokens for r in summary_calls],
                    "latency_s": [round(r.latency_seconds, 2) for r in summary_calls],
                    "guard_labels": [r.guard_violations for r in summary_calls],
                    "sections_summarised": [k for k in ("iv2", "iv3") if result[k]],
                    "verbatim_fallback": [k for k in ("iv2", "iv3") if not result[k]],
                    "flags": result["flags"],
                    "source_chars": {k: len(v) for k, v in section_sources(ctx).items()},
                    "summary_chars": {k: len(result[k] or "") for k in ("iv2", "iv3")},
                }
                (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    except Cap as cap_hit:
        stopped = str(cap_hit)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (402, 429):
            stopped = f"Gemini {error.response.status_code} - stopped"
        else:
            raise
    report = {"gemini_calls": calls(recorders), "cap": cap, "stopped": stopped,
              "cases": _case_summary(case_rows), "session": session}
    (out / "summary_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


RELIABILITY_CASES = 12


def _reliability_configs(base: int) -> list:
    """12 seeds base+1..base+12, cycling the A5-bis option mix (every crime, forced knobs)."""
    return [(base + i, BIS_CONFIGS[(i - 1) % len(BIS_CONFIGS)][1], BIS_CONFIGS[(i - 1) % len(BIS_CONFIGS)][2])
            for i in range(1, RELIABILITY_CASES + 1)]


async def reliability_main(out: Path, cap: int, seed_base: int) -> int:
    configure_logging("test")
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    cases, case_rows, stopped = [], [], None
    try:
        await _generate_cases(_reliability_configs(seed_base), settings, qdrant, cap, recorders, out, cases,
                              case_rows)
    except Cap as cap_hit:
        stopped = str(cap_hit)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (402, 429):
            stopped = f"Gemini {error.response.status_code} - stopped"
        else:
            raise
    report = {"gemini_calls": calls(recorders), "cap": cap, "stopped": stopped, "cases": _case_summary(case_rows)}
    (out / f"reliability_{seed_base}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    print(json.dumps({k: v for k, v in report["cases"].items() if k != "rows"} | {
        "gemini_calls": report["gemini_calls"], "stopped": stopped}, ensure_ascii=False, indent=1))
    return 0


# Chặng 3F: 5006 (no diacritics in chặng 3E) again, plus 6001-6006.
DIACRITICS_CONFIGS = _configs(SUMMARY_SEED_OFFSET)[5:6] + _configs(4000)


async def diacritics_main(out: Path, cap: int) -> int:
    configure_logging("test")
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    cases, case_rows, stopped = [], [], None
    try:
        await _generate_cases(DIACRITICS_CONFIGS, settings, qdrant, cap, recorders, out, cases, case_rows)
    except Cap as cap_hit:
        stopped = str(cap_hit)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (402, 429):
            stopped = f"Gemini {error.response.status_code} - stopped"
        else:
            raise
    report = {"gemini_calls": calls(recorders), "cap": cap, "stopped": stopped, "cases": _case_summary(case_rows),
              "still_unaccented": sum(1 for r in case_rows if not r["ok"] and r["no_diacritics_last_attempt"])}
    (out / "diacritics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


async def format_main(out: Path, cap: int) -> int:
    configure_logging("test")
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    (out / "speeches").mkdir(exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    cases, case_rows, slot_rows, stopped = [], [], [], None
    try:
        await _generate_cases(_configs(FORMAT_SEED_OFFSET), settings, qdrant, cap, recorders, out, cases, case_rows)
        for creation in cases[:FORMAT_SLOT_CASES]:
            case = creation.case
            for key, role in LONG_SLOTS:
                if calls(recorders) + SLOT_WORST_CASE.get(key, 2) > cap:
                    raise Cap(f"cap reached before {key}")
                recorder = TrialCallRecorder()
                recorders.append(recorder)
                step, index = _slot_position(key)
                state = replace(new_session(role, shape_of(case)), current_step=step, slot_index=index,
                                pending_ai=True)
                ctx = TrialContext(case=case, pack=creation.pack, state=state, settings=settings, recorder=recorder)
                row = {"crime": case.crime_key, "slot": key}
                try:
                    produced = await run_ai_turn(ctx)
                    text = produced[-1].text
                    row.update({"paragraphs": len(paragraphs(text)), "bullets": text.count("\n- "),
                                "markdown_left": any(m in text for m in ("**", "#", "* ")),
                                "chars": len(text), "calls": len(recorder.records),
                                "rejected": sum(not r.accepted for r in recorder.records)})
                    (out / "speeches" / f"{case.crime_key}_{key}.txt").write_text(
                        render(text, case.participants), encoding="utf-8")
                except TrialGuardFailure as failure:
                    row.update({"guard_pause": [v.split(":")[0] for v in failure.violations],
                                "calls": len(recorder.records)})
                slot_rows.append(row)
    except Cap as cap_hit:
        stopped = str(cap_hit)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (402, 429):
            stopped = f"Gemini {error.response.status_code} - stopped"
        else:
            raise

    measured = [r for r in slot_rows if "paragraphs" in r]
    summary = {
        "gemini_calls": calls(recorders), "cap": cap, "stopped": stopped,
        "cases": _case_summary(case_rows),
        "long_slots": {"measured": len(measured), "with_3_plus_paragraphs": sum(r["paragraphs"] >= 3 for r in measured),
                       "rows": slot_rows},
    }
    (out / "format.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


# Chặng R1: full Người xem hearings on fresh seeds, one per crime.
OBSERVER_CONFIGS = (
    (9201, CaseOptions(crime_key="blhs_173", user_role="nguoi_xem", victim_present=True, witness_count=1)),
    (9202, CaseOptions(crime_key="blhs_134", user_role="nguoi_xem", victim_present=True, witness_count=2)),
    (9203, CaseOptions(crime_key="blhs_174", user_role="nguoi_xem", victim_present=False, witness_count=1,
                       has_related_party=True)),
)

OBSERVER_SESSION_WORST_CASE = 2   # one AI turn (attempt + one regeneration) checked before each turn


def _jaccard(a: str, b: str) -> float:
    left, right = set(a.casefold().split()), set(b.casefold().split())
    return round(len(left & right) / len(left | right), 3) if left | right else 0.0


def _record_complete(record) -> dict:
    """Mẫu 22-HS parts the code must always fill: I-IV (with IV.1-IV.4), closing, signatures, appendix."""
    headings = [s.heading.split(".")[0] for s in record.sections]
    debate = record.sections[-1].subsections
    return {"parts_I_IV": headings == ["I", "II", "III", "IV"], "iv_items": len(debate),
            "iv_items_with_content": sum(1 for s in debate if s.entries or s.summary),
            "signatures": len(record.signatures), "appendix_entries": len(record.appendix[0].entries) if record.appendix else 0,
            "opening_blank": [f.label for f in record.opening if f.value is None],
            "preamble": len(record.preamble)}


async def _play_observer(seed: int, options: CaseOptions, settings, qdrant, cap: int, recorders: list,
                         out: Path) -> dict:
    case_recorder, recorder = TrialCallRecorder(), TrialCallRecorder()
    recorders += [case_recorder, recorder]
    if calls(recorders) + 3 > cap:
        raise Cap("cap reached before case generation")
    started = time.monotonic()
    creation = await create_case(options, settings, qdrant, case_recorder, seed=seed)
    row = {"seed": seed, "crime": options.crime_key, "case_attempts": creation.attempts,
           "case_seconds": round(time.monotonic() - started, 1)}
    ctx = TrialContext(case=creation.case, pack=creation.pack, state=new_session("nguoi_xem", shape_of(creation.case)),
                       settings=settings, recorder=recorder)
    events: list = []
    steps_seen = []
    while ctx.state.status == "active":
        await ai_until_user(ctx, recorders, cap, events)
        if ctx.state.status != "active":
            break
        steps_seen.append(ctx.state.current_step)
        student(ctx, "advance", target_step=ctx.state.current_step + 1)
    steps_seen.append(ctx.state.current_step)
    if calls(recorders) + SUMMARY_RESERVE > cap:
        raise Cap("cap reached before the record summary")
    ctx.record_summary = await summarise_record(ctx)
    if any(f.startswith("error:HTTPStatusError") for f in ctx.record_summary["flags"]):
        raise Cap("Gemini error during the record summary - stopped")
    record = build_record(ctx.case, ctx.transcript, None, None, summary=ctx.record_summary, observer=True)

    long_keys = {(6, "KSV"): "luan_toi", (7, "LUAT_SU"): "bao_chua", (8, "KSV"): "doi_dap_KSV",
                 (8, "LUAT_SU"): "doi_dap_LUAT_SU", (11, "CHU_TOA"): "tuyen_an"}
    long_texts = {long_keys[(u.step, u.speaker_id)]: u.text for u in ctx.transcript
                  if u.kind == "speech" and (u.step, u.speaker_id) in long_keys}
    flags: dict[str, int] = {}
    for u in ctx.transcript:
        for f in u.guard_flags:
            flags[f.split(":")[0]] = flags.get(f.split(":")[0], 0) + 1
    rejected: dict[str, int] = {}
    for r in recorder.records:
        if not r.accepted:
            for label in {v.split(":")[0] for v in r.guard_violations}:
                rejected[label] = rejected.get(label, 0) + 1
    row.update({
        "completed": ctx.state.status == "completed", "steps_reached": sorted(set(steps_seen)),
        "hearing_calls": len(recorder.records), "case_calls": len(case_recorder.records),
        "calls_by_type": {t: sum(1 for r in recorder.records if r.call_type == t)
                          for t in sorted({r.call_type for r in recorder.records})},
        "rejected_attempts": sum(not r.accepted for r in recorder.records), "rejected_labels": rejected,
        "guard_pauses": [e["guard_pause"] for e in events if "guard_pause" in e],
        "utterance_flags": flags, "is_user_utterances": sum(u.is_user for u in ctx.transcript),
        "utterances": len(ctx.transcript),
        "long_paragraphs": {k: len(paragraphs(v)) for k, v in long_texts.items()},
        "debate_overlap": {"ksv_vs_luan_toi": _jaccard(long_texts.get("doi_dap_KSV", ""), long_texts.get("luan_toi", "")),
                           "ls_vs_bao_chua": _jaccard(long_texts.get("doi_dap_LUAT_SU", ""),
                                                      long_texts.get("bao_chua", ""))},
        "summary_flags": ctx.record_summary["flags"],
        "summary_sections": [k for k in ("iv2", "iv3") if ctx.record_summary.get(k)],
        "record": _record_complete(record),
    })
    (out / "observer").mkdir(parents=True, exist_ok=True)
    (out / "observer" / f"record_{seed}.txt").write_text(render_record_text(record), encoding="utf-8")
    return row


async def observer_main(out: Path, cap: int) -> int:
    configure_logging("test")  # INFO + redaction; never DEBUG
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    out.mkdir(parents=True, exist_ok=True)
    recorders: list[TrialCallRecorder] = []
    rows, stopped = [], None
    for seed, options in OBSERVER_CONFIGS:
        try:
            rows.append(await _play_observer(seed, options, settings, qdrant, cap, recorders, out))
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
    hearing = [r for rec in recorders for r in rec.records if r.call_type != "case_generation"]
    latencies = [r.latency_seconds for r in hearing]
    report = {
        "gemini_calls": len(records), "cap": cap, "stopped": stopped,
        "tokens": {"prompt": sum(r.prompt_tokens for r in records), "output": sum(r.output_tokens for r in records),
                   "thinking": sum(r.thinking_tokens for r in records), "cached": sum(r.cached_tokens for r in records)},
        "hearing_call_latency": {"median": statistics.median(latencies) if latencies else None, "p90": _p90(latencies)},
        "long_latency": {"median": statistics.median([r.latency_seconds for r in hearing if r.call_type == "long_speech"] or [0]),
                         "p90": _p90([r.latency_seconds for r in hearing if r.call_type == "long_speech"])},
        "sessions": rows,
    }
    (out / "observer.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


LAW_NAME_SUMMARIES = 6


def _summary_labels(violations: list[str]) -> list[str]:
    """"citation:ambiguous_law: Điều 65 (...)" -> "citation:ambiguous_law"; labels only, no text."""
    return sorted({":".join(v.split(":")[:2]).strip() if v.startswith("citation:") else v.split(":")[0]
                   for v in violations})


async def law_names_main(out: Path, cap: int, case_path: Path) -> int:
    """Chặng R1b: a Người xem hearing on a stored case (no case generation) up to the end of step 9,
    then LAW_NAME_SUMMARIES single-attempt biên bản summaries. Each raw output is checked twice by
    the real guard: as written (before R1b) and after attach_law_names (after R1b), so before/after
    compare the same model outputs. The transcript is saved to --out for reuse."""
    from app.models.trial import CaseFile
    from app.prompts.trial_prompts import RECORD_SUMMARY_SYSTEM_PROMPT
    from app.services import trial_record_summary as rs

    configure_logging("test")  # INFO + redaction; never DEBUG
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    out.mkdir(parents=True, exist_ok=True)
    case = CaseFile.model_validate_json(case_path.read_text(encoding="utf-8"))
    pack = await load_pack_for_crime(get_crime(case.crime_key), settings, qdrant)
    recorder = TrialCallRecorder()
    recorders = [recorder]
    ctx = TrialContext(case=case, pack=pack, state=new_session("nguoi_xem", shape_of(case)), settings=settings,
                       recorder=recorder)
    events: list = []
    rows, stopped = [], None
    try:
        while True:   # Người xem: the AI plays a whole step, then waits for "advance"
            await ai_until_user(ctx, recorders, cap - LAW_NAME_SUMMARIES, events)
            if ctx.state.current_step == 9:
                break
            student(ctx, "advance", target_step=ctx.state.current_step + 1)
        (out / "law_names_transcript.json").write_text(json.dumps(
            [u.__dict__ for u in ctx.transcript], ensure_ascii=False, indent=1), encoding="utf-8")
        sources = rs.section_sources(ctx)
        all_sources = "\n".join(sources.values())
        reference = rs._reference(ctx, all_sources)
        for run in range(1, LAW_NAME_SUMMARIES + 1):
            if calls(recorders) + 1 > cap:
                raise Cap(f"cap reached before summary {run}")
            response, _ = await recorder.call(
                settings, call_type="record_summary", slot="bien_ban", attempt=1,
                system_prompt=RECORD_SUMMARY_SYSTEM_PROMPT, user_prompt=rs._user_prompt(ctx, sources, ["iv2", "iv3"], ""),
                response_schema=rs._SCHEMA, thinking_level=None, temperature=rs.SUMMARY_TEMPERATURE)
            raw = json.loads(response.text)
            row = {"run": run}
            for key in ("iv2", "iv3"):
                before = rs.check_summary(ctx, raw[key], sources[key], all_sources)
                after = rs.check_summary(ctx, rs.attach_law_names(raw[key], reference), sources[key], all_sources)
                row[key] = {"before": _summary_labels(before), "after": _summary_labels(after)}
            rows.append(row)
    except Cap as cap_hit:
        stopped = str(cap_hit)
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (402, 429):
            stopped = f"Gemini {error.response.status_code} - stopped"
        else:
            raise
    fallback = {when: {key: sum(1 for r in rows if r[key][when]) for key in ("iv2", "iv3")}
                for when in ("before", "after")}
    report = {"gemini_calls": calls(recorders), "cap": cap, "stopped": stopped, "hearing_steps": ctx.state.current_step,
              "guard_pauses": [e.get("guard_pause") for e in events], "summaries": len(rows),
              "verbatim_fallback_first_attempt": fallback, "runs": rows}
    (out / "law_names.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


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
    parser.add_argument("--format", action="store_true", help="chặng 3D layout measurement")
    parser.add_argument("--summary", action="store_true", help="chặng 3E cases + full hearing + biên bản summary")
    parser.add_argument("--diacritics", action="store_true", help="chặng 3F: seed 5006 + 6001-6006")
    parser.add_argument("--observer", action="store_true", help="chặng R1: 3 full Người xem hearings + biên bản")
    parser.add_argument("--law-names", type=Path, metavar="CASE_JSON",
                        help="chặng R1b: Người xem hearing on a stored case + 6 summaries, before/after law names")
    parser.add_argument("--reliability", type=int, metavar="SEED_BASE",
                        help="chặng 3G: 12 cases on SEED_BASE+1..+12, rule labels per attempt")
    args = parser.parse_args()
    if args.law_names is not None:
        sys.exit(asyncio.run(law_names_main(args.out, args.hard_cap, args.law_names)))
    if args.reliability is not None:
        sys.exit(asyncio.run(reliability_main(args.out, args.hard_cap, args.reliability)))
    entry = (observer_main if args.observer else format_main if args.format else summary_main if args.summary else
             diacritics_main if args.diacritics else main)
    sys.exit(asyncio.run(entry(args.out, args.hard_cap)))
