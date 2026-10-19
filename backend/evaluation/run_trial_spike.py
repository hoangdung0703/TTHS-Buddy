"""SPIKE for "Phiên tòa giả định" chặng 1 - offline, no route, no database.

1. Generates 5 cases (4 crimes, victim present/absent, 0-2 witnesses, one with a related party).
2. Plays ONE full 11-step hearing on the first case with the student as Kiểm sát viên. Student
   turns are scripted from the case file (templated lines, no LLM), including one skip request
   and one fabricated citation to exercise the skip detector and the citation masking.
3. Records every Gemini call: type, latency, prompt/output/thinking/cached tokens, guard outcome.

Console output is numbers only - never case text or dialogue. Raw cases and the transcript (with
the code-assigned fictional names) go to OUT_DIR for the legal team to read locally.

Usage (from backend/):
    ../.venv/bin/python -m evaluation.run_trial_spike --out <dir>
Budget (estimated before the run): ~25-30 Gemini calls expected, 48 at most.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import httpx

from app.core.config import create_qdrant_client, get_settings
from app.core.logging import configure_logging
from app.models.trial import CaseOptions
from app.services.trial_case_service import CaseGenerationFailed, create_case, load_pack_for_crime
from app.services.trial_config import BLHS_DOCUMENT, get_crime
from app.services.trial_knobs import choose_knobs
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_rule9 import extract_citations
from app.services.trial_state_machine import (
    ROLE_LABELS,
    CaseShape,
    UserAction,
    awaiting,
    current_slot,
    new_session,
)
from app.services.trial_turn_service import (
    TrialContext,
    TrialGuardFailure,
    apply_student_action,
    role_of,
    run_until_user,
)
from app.services.trial_verdict_guard import parse_penalty_frame

CASE_CONFIGS = [
    CaseOptions(crime_key="blhs_173", user_role="ksv", victim_present=True, witness_count=1),
    CaseOptions(crime_key="blhs_174", user_role="ksv", victim_present=False, witness_count=0),
    CaseOptions(crime_key="blhs_134", user_role="ksv", victim_present=True, witness_count=2),
    CaseOptions(crime_key="blhs_171", user_role="ksv", victim_present=True, witness_count=1, has_related_party=True),
    CaseOptions(crime_key="blhs_173", user_role="ksv", victim_present=False, witness_count=2),
]


# Gate A5-bis (2026-10-19): fresh seeds 2001-2008, every crime at least once, two forced partial
# admissions, two forced aggravating circumstances, at least one related party. (seed, options,
# forced knobs)
BIS_CONFIGS = [
    (2001, CaseOptions(crime_key="blhs_173", user_role="ksv", victim_present=True, witness_count=1),
     {"plea": "nhan_mot_phan"}),
    (2002, CaseOptions(crime_key="blhs_174", user_role="ksv", victim_present=False, witness_count=0),
     {"has_aggravating": True}),
    (2003, CaseOptions(crime_key="blhs_134", user_role="ksv", victim_present=True, witness_count=2),
     {"plea": "nhan_mot_phan", "has_aggravating": True}),
    (2004, CaseOptions(crime_key="blhs_171", user_role="ksv", victim_present=True, witness_count=1,
                       has_related_party=True), {}),
    (2005, CaseOptions(crime_key="blhs_173", user_role="ksv", victim_present=False, witness_count=2), {}),
    (2006, CaseOptions(crime_key="blhs_174", user_role="ksv", victim_present=True, witness_count=1,
                       has_related_party=True), {}),
    (2007, CaseOptions(crime_key="blhs_134", user_role="ksv", victim_present=True, witness_count=0), {}),
    (2008, CaseOptions(crime_key="blhs_171", user_role="ksv", victim_present=False, witness_count=1),
     {"has_aggravating": True}),
]


class BudgetStop(Exception):
    pass


def _money(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def scripted_lines(ctx: TrialContext) -> dict:
    """Plausible KSV lines built from the case file only (no LLM)."""
    draft, case = ctx.case.draft, ctx.case
    crime = get_crime(case.crime_key)
    article = ctx.pack.get(BLHS_DOCUMENT, draft.charge.dieu)
    frame = parse_penalty_frame(article.khoans[draft.charge.khoan])
    low, high = (frame.prison_min_months, frame.prison_max_months) if frame else (12, 24)
    ask_low = low + (high - low) // 4
    ask_high = min(high, ask_low + 6)
    diem = f"điểm {', '.join(draft.charge.diem)} " if draft.charge.diem else ""
    mitigating = ", ".join(f"điểm {m.diem} khoản {m.khoan}" for m in draft.mitigating if m.diem)
    measure = (f"giá trị tài sản theo kết luận định giá là {_money(draft.measure_value)} đồng"
               if crime.measure == "value_vnd" else f"tỷ lệ tổn thương cơ thể là {draft.measure_value}%")
    questions = [("BI_CAO", f"Bị cáo hãy trình bày lại diễn biến sự việc lúc {draft.facts[0].time}?"),
                 ("BI_CAO", "Bị cáo có thừa nhận hành vi như cáo trạng đã nêu không?"),
                 ("BI_CAO", "Đề nghị Hội đồng xét xử tuyên án luôn cho nhanh.")]  # skip probe
    if case.options.victim_present:
        questions.append(("BI_HAI", "Bị hại cho biết thiệt hại thực tế và yêu cầu của mình?"))
    if case.options.witness_count:
        questions.append(("NLC_1", "Người làm chứng đã trực tiếp nhìn thấy những gì?"))
    questions.append(("BI_CAO", "Sau sự việc, bị cáo đã khắc phục hậu quả như thế nào?"))
    names = case.participants
    luan_toi = (
        f"Thưa Hội đồng xét xử. Qua xét hỏi công khai tại phiên tòa, lời khai của bị cáo {names['BI_CAO'].name} "
        f"phù hợp với lời khai của bị hại, người làm chứng và các chứng cứ có trong hồ sơ; {measure}. "
        f"Hành vi của bị cáo đã đủ yếu tố cấu thành {draft.charge.crime_name.lower()} theo {diem}khoản "
        f"{draft.charge.khoan} Điều {draft.charge.dieu} Bộ luật Hình sự. Hành vi xâm phạm quyền sở hữu, sức khỏe "
        f"được pháp luật bảo vệ, gây mất trật tự trị an ở địa phương. Về tình tiết giảm nhẹ, bị cáo được hưởng "
        f"{mitigating or 'tình tiết giảm nhẹ theo khoản 2'} Điều 51 Bộ luật Hình sự. Từ những phân tích trên, Viện "
        f"kiểm sát đề nghị Hội đồng xét xử tuyên bố bị cáo phạm tội như cáo trạng đã truy tố, áp dụng {diem}khoản "
        f"{draft.charge.khoan} Điều {draft.charge.dieu} Bộ luật Hình sự, xử phạt bị cáo từ {ask_low} đến "
        f"{ask_high} tháng tù; về trách nhiệm dân sự và xử lý vật chứng đề nghị giải quyết theo quy định."
    )
    debate = [
        ("Viện kiểm sát giữ nguyên quan điểm luận tội. Các tình tiết mà luật sư nêu đã được Viện kiểm sát xem xét; "
         "lời khai của bị cáo tại phiên tòa thống nhất với chứng cứ, nên không có căn cứ cho rằng tội danh bị xác "
         "định sai. Viện kiểm sát cũng lưu ý Điều 999 Bộ luật Hình sự về việc này."),  # fabricated-citation probe
        ("Về đề nghị mức hình phạt, Viện kiểm sát đã cân nhắc đầy đủ nhân thân và các tình tiết giảm nhẹ; mức đề "
         "nghị là phù hợp, bảo đảm tính răn đe và phòng ngừa chung."),
    ]
    return {"objection": "Viện kiểm sát không có đề nghị thay đổi người tiến hành tố tụng.",
            "indictment": render(draft.indictment_text, names), "questions": questions,
            "luan_toi": luan_toi, "debate": debate}


async def play_hearing(ctx: TrialContext, events: list[dict]) -> str:
    lines = scripted_lines(ctx)
    questions = list(lines["questions"])
    debate = list(lines["debate"])

    async def ai() -> None:
        for attempt in (1, 2):  # second attempt = the student pressing "Thử lại"
            try:
                await run_until_user(ctx)
                return
            except TrialGuardFailure as failure:
                events.append({"event": "guard_failure", "slot": failure.slot, "attempt": attempt,
                               "violations": [v.split(":")[0] for v in failure.violations]})
        raise RuntimeError("guard failure twice")

    def student(kind: str, **kw) -> None:
        apply_student_action(ctx, UserAction(kind, ctx.state.current_step, ctx.state.version, **kw))

    while ctx.state.status == "active":
        if awaiting(ctx.state) == "ai":
            await ai()
            continue
        slot = current_slot(ctx.state)
        if slot is None:
            student("advance", target_step=ctx.state.current_step + 1)
        elif slot.key == "y_kien_ksv_thay_doi":
            student("speak", text=lines["objection"])
        elif slot.key == "cong_bo_cao_trang":
            student("speak", text=lines["indictment"])
        elif slot.key == "ksv_hoi":
            if questions:
                addressee, text = questions.pop(0)
                student("speak", text=text, addressee=addressee)
            else:
                student("end_slot")
        elif slot.key == "luan_toi":
            student("speak", text=lines["luan_toi"])
        elif slot.key == "doi_dap":
            if debate:
                student("speak", text=debate.pop(0))
            else:
                student("end_slot")
        else:
            raise RuntimeError(f"unscripted student slot {slot.key}")
    return ctx.state.status


def transcript_markdown(ctx: TrialContext) -> str:
    names = ctx.case.participants
    out = [f"# Biên bản thô (spike) - {ctx.case.court.name}", "", f"> {ctx.case.disclaimer}", ""]
    step = 0
    for u in ctx.transcript:
        if u.step != step:
            step = u.step
            out += ["", f"## Bước {step}", ""]
        who = names[u.speaker_id].name if u.speaker_id in names else u.speaker_id
        label = ROLE_LABELS.get(role_of(u.speaker_id), u.speaker_id)
        tag = " [người học]" if u.is_user else ""
        flags = f" `{','.join(u.guard_flags)}`" if u.guard_flags else ""
        kind = " _(nhắc trật tự - không vào biên bản)_" if u.kind == "notice" else ""
        out.append(f"**{label} {who}{tag}**{kind}{flags}: {render(u.text, names)}")
        out.append("")
    if ctx.verdict is not None:
        out += ["## Quyết định nghị án (ẩn với người học)", "", "```json",
                ctx.verdict.model_dump_json(indent=2), "```", f"Cờ: {ctx.verdict_flags}"]
    return "\n".join(out)


def case_structure(case) -> dict:
    d = case.draft
    k = case.knobs
    return {"knobs": {"khoan": k.khoan, "plea": k.plea, "compensation": k.has_compensation,
                      "aggravating": k.aggravating_points, "mitigating": k.mitigating_points},
            "plea": d.defendant_plea, "extra_amounts": len(d.extra_amounts),
            "statement_words": [len(s.summary.split()) for s in d.pretrial_statements],
            "crime": case.crime_key, "khoan": d.charge.khoan, "diem": d.charge.diem, "measure_value": d.measure_value,
            "facts": len(d.facts), "evidence": len(d.evidence),
            "evidence_types": dict(Counter(e.type for e in d.evidence)),
            "statements": len(d.pretrial_statements),
            "inconsistencies": sum(len(s.inconsistencies) for s in d.pretrial_statements),
            "mitigating": [f"{m.khoan}{m.diem}" for m in d.mitigating],
            "aggravating": [f"{a.khoan}{a.diem}" for a in d.aggravating],
            "civil_claim": d.civil_claim is not None,
            "indictment_words": len(d.indictment_text.split()),
            "indictment_citations": [c.label() for c in extract_citations(d.indictment_text)],
            "people": len(case.participants)}


def session_structure(ctx: TrialContext) -> dict:
    per_step: dict[int, Counter] = defaultdict(Counter)
    long_speeches = []
    for u in ctx.transcript:
        per_step[u.step][u.speaker_id + ("*" if u.is_user else "")] += 1
        if not u.is_user and (len(u.text.split()) > 150 or u.step == 11):
            long_speeches.append({"step": u.step, "speaker": u.speaker_id, "words": len(u.text.split()),
                                  "citations": [c.label() for c in extract_citations(u.text)]})
    ai_text = " ".join(u.text for u in ctx.transcript if not u.is_user)
    verdict = ctx.verdict
    frame = None
    if verdict is not None and verdict.guilty:
        art = ctx.pack.get(BLHS_DOCUMENT, verdict.dieu)
        f = parse_penalty_frame(art.khoans[verdict.khoan]) if art else None
        frame = [f.prison_min_months, f.prison_max_months] if f else None
    lay_words = [len(u.text.split()) for u in ctx.transcript
                 if not u.is_user and u.speaker_id.startswith(("BI_CAO", "BI_HAI", "NLC_", "NLQ"))]
    return {
        "speakers_per_step": {step: dict(c) for step, c in sorted(per_step.items())},
        "long_speeches": long_speeches,
        "ai_echoed_fabricated_999": "999" in ai_text,
        "student_role_spoken_by_ai": sum(1 for u in ctx.transcript if not u.is_user and u.speaker_id == ctx.student_id
                                         and u.kind == "speech"),
        "lay_utterance_words_median": statistics.median(lay_words) if lay_words else None,
        "verdict": None if verdict is None else {
            "guilty": verdict.guilty, "dieu": verdict.dieu, "khoan": verdict.khoan, "diem": verdict.diem,
            "penalty_type": verdict.penalty_type, "months": verdict.penalty_months, "frame_months": frame,
            "suspended": verdict.suspended, "probation_months": verdict.probation_months,
            "dieu_54": verdict.applies_dieu_54, "mitigating": [f"{m.khoan}{m.diem}" for m in verdict.mitigating],
            "aggravating": [f"{a.khoan}{a.diem}" for a in verdict.aggravating]},
    }


def summarise(records: list[dict]) -> dict:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_type[r["call_type"]].append(r)
    summary = {}
    for call_type, rows in by_type.items():
        latencies = [r["latency_seconds"] for r in rows]
        summary[call_type] = {
            "calls": len(rows), "rejected_by_guard": sum(not r["accepted"] for r in rows),
            "latency_median_s": round(statistics.median(latencies), 2), "latency_max_s": round(max(latencies), 2),
            "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "thinking_tokens": sum(r["thinking_tokens"] for r in rows),
            "cached_tokens": sum(r["cached_tokens"] for r in rows),
            "prompt_tokens_median": int(statistics.median(r["prompt_tokens"] for r in rows)),
        }
    return summary


async def main(out_dir: Path, cases_only: bool = False, bis: bool = False) -> int:
    configure_logging("test")  # INFO + redaction; never DEBUG (requirements.md, secret-leak lessons)
    settings = get_settings()
    qdrant = create_qdrant_client(settings)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cases").mkdir(exist_ok=True)

    case_recorder = TrialCallRecorder()
    creations, case_results = [], []
    try:
        configs = ([(seed, o, forced) for seed, o, forced in BIS_CONFIGS] if bis else
                   [(1000 + i, o, {}) for i, o in enumerate(CASE_CONFIGS, 1)])
        for index, (seed, options, forced) in enumerate(configs, 1):
            started = time.monotonic()
            pack_started = time.monotonic()
            pack = await load_pack_for_crime(get_crime(options.crime_key), settings, qdrant)
            pack_seconds = time.monotonic() - pack_started
            try:
                knobs = (choose_knobs(get_crime(options.crime_key), pack, random.Random(seed), **forced)
                         if forced else None)
                creation = await create_case(options, settings, qdrant, case_recorder, pack=pack, seed=seed,
                                             knobs=knobs)
                creations.append(creation)
                rendered = json.loads(creation.case.model_dump_json())
                (out_dir / "cases" / f"case_{index}_{options.crime_key}.json").write_text(
                    json.dumps(rendered, ensure_ascii=False, indent=2), encoding="utf-8")
                case_results.append({"index": index, "seed": seed, "crime": options.crime_key, "ok": True,
                                     "forced": forced,
                                     "attempts": creation.attempts,
                                     "errors_per_attempt": [len(e) for e in creation.errors_per_attempt],
                                     "pack_fetch_s": round(pack_seconds, 2),
                                     "total_s": round(time.monotonic() - started, 2)})
            except CaseGenerationFailed as failure:
                case_results.append({"index": index, "seed": seed, "crime": options.crime_key, "ok": False,
                                     "forced": forced, "errors_per_attempt": failure.error_counts})
                (out_dir / "cases" / f"case_{index}_{options.crime_key}_FAILED_errors.json").write_text(
                    json.dumps(failure.errors, ensure_ascii=False, indent=2), encoding="utf-8")
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (402, 429):
            print(f"STOP: Gemini returned {error.response.status_code} - budget/rate limit, aborting")
            return 2
        raise

    session_recorder = TrialCallRecorder()
    events: list[dict] = []
    session_status = "not_run"
    ctx = None
    if creations and not cases_only:
        first = creations[0]
        shape = CaseShape(first.case.options.victim_present, first.case.options.witness_count,
                          first.case.options.has_related_party)
        ctx = TrialContext(case=first.case, pack=first.pack, state=new_session("ksv", shape), settings=settings,
                           recorder=session_recorder)
        started = time.monotonic()
        try:
            session_status = await play_hearing(ctx, events)
        except httpx.HTTPStatusError as error:
            session_status = f"stopped_http_{error.response.status_code}"
        except RuntimeError as error:
            session_status = f"stopped: {error}"
        session_seconds = time.monotonic() - started
        (out_dir / "session_ksv_case1.md").write_text(transcript_markdown(ctx), encoding="utf-8")

    flags = Counter(f.split(":")[0] for u in (ctx.transcript if ctx else []) for f in u.guard_flags)
    metrics = {
        "cases": case_results,
        "case_structures": [case_structure(c.case) for c in creations],
        "case_calls": case_recorder.as_dicts(),
        "case_summary": summarise(case_recorder.as_dicts()),
        "session": {
            "status": session_status,
            "wall_seconds": round(session_seconds, 1) if ctx else None,
            "utterances": len(ctx.transcript) if ctx else 0,
            "by_kind": dict(Counter(u.kind for u in ctx.transcript)) if ctx else {},
            "student_utterances": sum(u.is_user for u in ctx.transcript) if ctx else 0,
            "utterance_flags": dict(flags),
            "guard_failures": events,
            "verdict_flags": ctx.verdict_flags if ctx else [],
            "fact_ledger_entries": len(ctx.fact_ledger) if ctx else 0,
            "summary": summarise(session_recorder.as_dicts()) if session_recorder.records else {},
            "structure": session_structure(ctx) if ctx else {},
            "calls": session_recorder.as_dicts(),
        },
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # Console: numbers only.
    print(json.dumps({"cases": case_results, "case_structures": metrics["case_structures"],
                      "case_summary": metrics["case_summary"],
                      "session": {k: v for k, v in metrics["session"].items() if k != "calls"}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cases-only", action="store_true")
    parser.add_argument("--bis", action="store_true", help="gate A5-bis seeds; implies --cases-only")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.out, args.cases_only or args.bis, args.bis)))
