"""Glue between stored rows (trial_repository) and the in-memory hearing (trial_turn_service):
rebuild a TrialContext from rows, turn state/utterances back into rows, and build the views the
routes return. No I/O here - the routes call the repository."""
from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.models.trial import CaseFile, ChairDecision, Verdict
from app.models.trial_api import TrialPendingQuestion, TrialStateOut, TrialSummaryOut, TrialUtteranceOut
from app.services import trial_presiding
from app.services.trial_chair_decision import CIRCUMSTANCE_KHOANS, check_decision, is_penalty_khoan
from app.services.trial_config import BLHS_DOCUMENT
from app.services.trial_anonymise import anonymise_case_view
from app.services.trial_clerk import attendance, clerk_prompt, report_prefill
from app.services.trial_defendant import DECLINE_NOTE, IDENTITY_SLOT, identity_prefill
from app.services.trial_legal_pack import LegalPack, build_pack
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_procedure_notes import procedure_note
from app.services.trial_repository import utc_now
from app.services.trial_state_machine import (
    ROLE_LABELS,
    STEP_BY_NUMBER,
    STEPS,
    OBSERVER_ROLE,
    CLERK_ROLE,
    DEFENDANT_ROLE,
    PRESIDING_ROLE,
    CaseShape,
    SessionState,
    allowed_actions,
    awaiting,
    current_slot,
    is_interleaved,
    text_limits,
)
from app.services.trial_verdict_guard import parse_penalty_frame
from app.services.trial_turn_service import (
    ASSESSOR_KEY,
    DECISION_DRAFT_KEY,
    PRONOUNCEMENT_KEY,
    STUDENT_QUESTION_FLAG,
    TrialContext,
    Utterance,
    role_of,
)


RECORD_SUMMARY_KEY = "record_summary"
# Keys verdict_json carries beside the Verdict fields in a Chủ tọa session (TrialContext.verdict_meta).
VERDICT_META_KEYS = ("source", "extras", "assessor_opinions")
PRESIDE_KEY = "preside"
# Decision Q7: the simulation differs from the order of Điều 326 khoản 1 BLTTHS ("Hội thẩm biểu
# quyết trước, Thẩm phán biểu quyết sau cùng"); the frontend shows this next to the Hội thẩm comments.
ASSESSOR_ORDER_NOTE = ("Mô phỏng khác thứ tự của khoản 1 Điều 326 Bộ luật Tố tụng hình sự: theo luật, Hội thẩm biểu "
                       "quyết trước, Thẩm phán biểu quyết sau cùng. Ở đây Hội thẩm chỉ góp ý trên bản nháp của Chủ "
                       "tọa và không biểu quyết thay.")
DECISION_STEP = 10


def shape_of(case: CaseFile) -> CaseShape:
    return CaseShape(case.options.victim_present, case.options.witness_count, case.options.has_related_party)


def state_from_row(row: dict[str, Any], case: CaseFile) -> SessionState:
    preside = None
    if row["user_role"] == PRESIDING_ROLE:
        preside = trial_presiding.preside_from_dict((row.get("user_work") or {}).get(PRESIDE_KEY))
    return SessionState(user_role=row["user_role"], shape=shape_of(case), current_step=row["current_step"],
                        slot_index=row["slot_index"], version=row["version"], status=row["status"],
                        slot_user_turns=row["slot_user_turns"], pending_ai=row["pending_ai"], preside=preside)


def state_fields(ctx: TrialContext) -> dict[str, Any]:
    state = ctx.state
    fields = {"current_step": state.current_step, "slot_index": state.slot_index,
              "slot_user_turns": state.slot_user_turns, "pending_ai": state.pending_ai, "status": state.status,
              "version": state.version, "fact_ledger": ctx.fact_ledger,
              "verdict_json": verdict_json(ctx),
              "verdict_flags": ctx.verdict_flags}
    if state.preside is not None:
        # Chủ tọa only: user_work is written WITH the version (decision Q1), so a stream and a draft
        # save can never overwrite each other. Every other role keeps the version-free writes.
        fields["user_work"] = {**ctx.user_work, PRESIDE_KEY: trial_presiding.preside_to_dict(state.preside)}
    if state.status == "completed":
        fields["completed_at"] = utc_now().isoformat()
    return fields


def verdict_json(ctx: TrialContext) -> dict[str, Any] | None:
    """The verdict plus, once computed, the biên bản summaries - kept in the same jsonb column so
    chặng 3E needs no migration. Never returned to the client."""
    if ctx.verdict is None:
        return None
    data = ctx.verdict.model_dump()
    data.update(ctx.verdict_meta)
    if ctx.record_summary is not None:
        data[RECORD_SUMMARY_KEY] = ctx.record_summary
    return data


def utterance_from_row(row: dict[str, Any]) -> Utterance:
    return Utterance(seq=row["seq"], step=row["step"], speaker_id=row["speaker_id"], is_user=row["is_user"],
                     kind=row["kind"], text=row["content"], guard_flags=list(row.get("guard_flags") or []),
                     addressee=row.get("addressee"), procedure_item=row.get("procedure_item"))


def utterance_rows(utterances: list[Utterance], session_id: str, user_id: str) -> list[dict[str, Any]]:
    return [{"session_id": session_id, "user_id": user_id, "seq": u.seq, "step": u.step, "speaker_id": u.speaker_id,
             "is_user": u.is_user, "kind": u.kind, "content": u.text, "addressee": u.addressee,
             "guard_flags": u.guard_flags, "procedure_item": u.procedure_item} for u in utterances]


def build_context(case_row: dict[str, Any], session_row: dict[str, Any], utterance_rows_: list[dict[str, Any]],
                  settings: Settings, recorder: TrialCallRecorder) -> TrialContext:
    case = CaseFile.model_validate(case_row["case_json"])
    stored = dict(session_row.get("verdict_json") or {})
    record_summary = stored.pop(RECORD_SUMMARY_KEY, None)
    meta = {key: stored.pop(key) for key in VERDICT_META_KEYS if key in stored}
    verdict = Verdict.model_validate(stored) if stored else None
    user_work = dict(session_row.get("user_work") or {})
    return TrialContext(
        case=case, pack=build_pack(case_row["legal_pack"]), state=state_from_row(session_row, case),
        settings=settings, recorder=recorder, transcript=[utterance_from_row(r) for r in utterance_rows_],
        fact_ledger=list(session_row.get("fact_ledger") or []), verdict=verdict,
        verdict_flags=list(session_row.get("verdict_flags") or []), record_summary=record_summary,
        user_work=user_work if session_row["user_role"] == PRESIDING_ROLE else {}, verdict_meta=meta,
    )


REPORT_SLOT = "bao_cao_co_mat"


def state_out(session_id: str, state: SessionState, guard_exhausted: bool = False,
              case: CaseFile | None = None, transcript: list[Utterance] | None = None,
              pack: LegalPack | None = None, user_work: dict | None = None) -> TrialStateOut:
    """`case` is needed for the Thư ký's step-1 report (names in the prefill) and, with `transcript`,
    for the Bị cáo's pending question; with `pack` and `user_work`, for the Chủ tọa's checklist and
    decision."""
    actions = allowed_actions(state)
    presiding = decision = None
    if state.preside is not None and case is not None and pack is not None:
        decision = decision_view(state, case, pack, user_work or {})
        actions = _presiding_actions(actions, decision)
        if state.current_step >= 2:
            presiding = trial_presiding.presiding_view(state, case)
    if state.status == "active" and awaiting(state) == "ai":
        actions = [] if guard_exhausted else ["continue"]
    limits = text_limits(state)
    clerk = state.user_role == CLERK_ROLE
    slot = current_slot(state)
    report_due = (clerk and case is not None and awaiting(state) == "user" and slot is not None
                  and slot.key == REPORT_SLOT)
    return TrialStateOut(session_id=session_id, current_step=state.current_step,
                         step_title=STEP_BY_NUMBER[state.current_step].title, status=state.status,
                         awaiting=awaiting(state), allowed_actions=actions, version=state.version,
                         text_limits={"min": limits[0], "max": limits[1]} if limits else None,
                         procedure_note=procedure_note(state.current_step) if state.user_role == OBSERVER_ROLE
                         else None,
                         clerk_prompt=clerk_prompt(state.current_step) if clerk else None,
                         clerk_report={"prefill": report_prefill(case, state.shape),
                                       "attendance": attendance(case, state.shape)} if report_due else None,
                         pending_question=_pending_question(state, case, transcript),
                         presiding=presiding, decision=decision)


def _presiding_actions(actions: list[str], decision: dict | None) -> list[str]:
    """"decide" and the Hội thẩm comment need a stored draft with no hard error."""
    if decision is not None and decision["check"] is not None and not decision["check"]["errors"]:
        return actions
    out = []
    for action in actions:
        if action == "decide":
            continue
        if action.startswith("invite:"):
            keys = [k for k in action.split(":", 1)[1].split("|") if k != "y_kien_hoi_tham"]
            if not keys:
                continue
            action = "invite:" + "|".join(keys)
        out.append(action)
    return out


def decision_view(state: SessionState, case: CaseFile, pack: LegalPack, user_work: dict) -> dict | None:
    """Chủ tọa, steps 10-11: the student's OWN draft or locked decision with its check, the Hội thẩm
    comments on it, the judgment text written from it, and the form's choices. Never an AI decision:
    none exists in this role."""
    if state.preside is None or state.current_step < DECISION_STEP:
        return None
    draft = user_work.get(DECISION_DRAFT_KEY)
    check = check_decision(ChairDecision.model_validate(draft), case, pack).as_dict() if draft else None
    assessor = user_work.get(ASSESSOR_KEY)
    opinions = None
    if assessor:
        opinions = [{"speaker_id": o["speaker_id"], "speaker_name": case.participants[o["speaker_id"]].name,
                     "agrees": o["agrees"], "text": render(o["text"], case.participants)}
                    for o in assessor["opinions"]]
    preview = user_work.get(PRONOUNCEMENT_KEY)
    return {"draft": draft, "updated_at": user_work.get("decision_updated_at"), "check": check,
            "locked": state.preside.decided, "assessor_opinions": opinions,
            "assessor_draft_updated_at": (assessor or {}).get("draft_updated_at"),
            "assessor_order_note": ASSESSOR_ORDER_NOTE,
            "pronouncement_preview": render(preview["text"], case.participants) if preview else None,
            "form": decision_form(case, pack)}


def decision_form(case: CaseFile, pack: LegalPack) -> dict:
    """The choices of the decision form, from the case file and the articles in the pack."""
    charge = case.draft.charge
    article = pack.get(BLHS_DOCUMENT, charge.dieu)
    khoans = sorted((k for k in article.khoans if is_penalty_khoan(article, k)), key=int) if article else [charge.khoan]
    frames = {}
    for k in khoans:
        frame = parse_penalty_frame(article.khoans[k]) if article else None
        frames[k] = None if frame is None else {
            "prison_min_months": frame.prison_min_months, "prison_max_months": frame.prison_max_months,
            "non_custodial_max_months": frame.non_custodial_max_months, "fine_as_main": frame.fine_as_main}

    def points(dieu: str) -> dict[str, list[str]]:
        found = pack.get(BLHS_DOCUMENT, dieu)
        return {k: sorted(found.khoans[k].diem) for k in CIRCUMSTANCE_KHOANS[dieu] if k in found.khoans} if found else {}

    return {
        "dieu": charge.dieu, "charged_khoan": charge.khoan, "charged_diem": list(charge.diem), "khoan": khoans,
        "diem": {k: sorted(article.khoans[k].diem) for k in khoans} if article else {}, "frames": frames,
        "mitigating_points": points("51"), "aggravating_points": points("52"),
        "penalty_types": ["tu", "cai_tao_khong_giam_giu", "phat_tien", "khong"],
        "facts": [f.id for f in case.draft.facts],
        "exhibits": [e.id for e in case.draft.evidence if e.type == "vat_chung"],
        "dispositions": ["tra_lai", "tich_thu_sung_ngan_sach", "tich_thu_tieu_huy", "luu_ho_so"],
        "civil_claim_vnd": case.draft.civil_claim.amount_vnd if case.draft.civil_claim else None,
        "compensation_vnd": case.draft.compensation_vnd,
        "reasoning_limits": {"min": trial_presiding.REASONING_MIN_CHARS, "max": trial_presiding.REASONING_MAX_CHARS},
    }


def _pending_question(state: SessionState, case: CaseFile | None,
                      transcript: list[Utterance] | None) -> TrialPendingQuestion | None:
    """Bị cáo, while a đoạn xen waits for the student: the latest question put to them."""
    slot = current_slot(state)
    if (state.user_role != DEFENDANT_ROLE or case is None or not transcript or awaiting(state) != "user"
            or slot is None or not is_interleaved(slot, state.user_role)):
        return None
    question = next((u for u in reversed(transcript) if STUDENT_QUESTION_FLAG in u.guard_flags), None)
    if question is None:
        return None
    shown = utterance_out(question, case)
    return TrialPendingQuestion(
        seq=shown.seq, speaker_id=shown.speaker_id, speaker_role=shown.speaker_role,
        speaker_name=shown.speaker_name, text=shown.text,
        prefill=identity_prefill(case) if slot.key == IDENTITY_SLOT and state.slot_user_turns == 0 else None,
        decline_note=DECLINE_NOTE if slot.decline else None)


def utterance_out(u: Utterance, case: CaseFile) -> TrialUtteranceOut:
    names = case.participants
    return TrialUtteranceOut(
        seq=u.seq, step=u.step, speaker_id=u.speaker_id, speaker_role=ROLE_LABELS.get(role_of(u.speaker_id), ""),
        speaker_name=names[u.speaker_id].name if u.speaker_id in names else "", is_user=u.is_user, kind=u.kind,
        text=u.text if u.is_user else render(u.text, names), addressee=u.addressee, procedure_item=u.procedure_item)


def _render_tree(value: Any, case: CaseFile) -> Any:
    if isinstance(value, str):
        return render(value, case.participants)
    if isinstance(value, list):
        return [_render_tree(v, case) for v in value]
    if isinstance(value, dict):
        return {k: _render_tree(v, case) for k, v in value.items()}
    return value


# Character cards are acting notes for the AI, not part of the file a KSV or defence lawyer reads:
# showing them would tell the student in advance how each person will testify.
HIDDEN_PERSON_FIELDS = ("stance", "knowledge", "demeanor")
HIDDEN_CASE_FIELDS = ("defendant_plea",)


def student_case_view(case: CaseFile) -> dict[str, Any]:
    """The hồ sơ the student's role may read (KSV and luật sư both read the file, BLTTHS Điều 73).
    The knobs are generation internals, the character cards are hidden (HIDDEN_PERSON_FIELDS),
    and the verdict lives on the session and is never returned. Lay participants' names are
    abbreviated (trial_anonymise) - in this view only."""
    data = case.draft.model_dump()
    for key in HIDDEN_CASE_FIELDS:
        data.pop(key, None)
    people = [data["defendant"], data["victim"], *data["witnesses"]]
    if data.get("related_party"):
        people.append(data["related_party"])
    for person in people:
        for key in HIDDEN_PERSON_FIELDS:
            person.pop(key, None)
    return anonymise_case_view(_render_tree(data, case), case.participants)


def steps_view() -> list[dict[str, Any]]:
    return [{"number": s.number, "title": s.title, "legal_basis": list(s.legal_basis)} for s in STEPS]


def summary_out(row: dict[str, Any]) -> TrialSummaryOut:
    return TrialSummaryOut(session_id=row["id"], title=row["title"], crime_key=row["crime_key"],
                           user_role=row["user_role"], current_step=row["current_step"], status=row["status"],
                           updated_at=row["updated_at"])
