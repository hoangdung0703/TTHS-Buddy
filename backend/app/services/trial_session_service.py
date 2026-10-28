"""Glue between stored rows (trial_repository) and the in-memory hearing (trial_turn_service):
rebuild a TrialContext from rows, turn state/utterances back into rows, and build the views the
routes return. No I/O here - the routes call the repository."""
from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.models.trial import CaseFile, Verdict
from app.models.trial_api import TrialStateOut, TrialSummaryOut, TrialUtteranceOut
from app.services.trial_anonymise import anonymise_case_view
from app.services.trial_legal_pack import build_pack
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_names import render
from app.services.trial_repository import utc_now
from app.services.trial_state_machine import (
    ROLE_LABELS,
    STEP_BY_NUMBER,
    STEPS,
    CaseShape,
    SessionState,
    allowed_actions,
    awaiting,
    text_limits,
)
from app.services.trial_turn_service import TrialContext, Utterance, role_of


RECORD_SUMMARY_KEY = "record_summary"


def shape_of(case: CaseFile) -> CaseShape:
    return CaseShape(case.options.victim_present, case.options.witness_count, case.options.has_related_party)


def state_from_row(row: dict[str, Any], case: CaseFile) -> SessionState:
    return SessionState(user_role=row["user_role"], shape=shape_of(case), current_step=row["current_step"],
                        slot_index=row["slot_index"], version=row["version"], status=row["status"],
                        slot_user_turns=row["slot_user_turns"], pending_ai=row["pending_ai"])


def state_fields(ctx: TrialContext) -> dict[str, Any]:
    state = ctx.state
    fields = {"current_step": state.current_step, "slot_index": state.slot_index,
              "slot_user_turns": state.slot_user_turns, "pending_ai": state.pending_ai, "status": state.status,
              "version": state.version, "fact_ledger": ctx.fact_ledger,
              "verdict_json": verdict_json(ctx),
              "verdict_flags": ctx.verdict_flags}
    if state.status == "completed":
        fields["completed_at"] = utc_now().isoformat()
    return fields


def verdict_json(ctx: TrialContext) -> dict[str, Any] | None:
    """The verdict plus, once computed, the biên bản summaries - kept in the same jsonb column so
    chặng 3E needs no migration. Never returned to the client."""
    if ctx.verdict is None:
        return None
    data = ctx.verdict.model_dump()
    if ctx.record_summary is not None:
        data[RECORD_SUMMARY_KEY] = ctx.record_summary
    return data


def utterance_from_row(row: dict[str, Any]) -> Utterance:
    return Utterance(seq=row["seq"], step=row["step"], speaker_id=row["speaker_id"], is_user=row["is_user"],
                     kind=row["kind"], text=row["content"], guard_flags=list(row.get("guard_flags") or []),
                     addressee=row.get("addressee"))


def utterance_rows(utterances: list[Utterance], session_id: str, user_id: str) -> list[dict[str, Any]]:
    return [{"session_id": session_id, "user_id": user_id, "seq": u.seq, "step": u.step, "speaker_id": u.speaker_id,
             "is_user": u.is_user, "kind": u.kind, "content": u.text, "addressee": u.addressee,
             "guard_flags": u.guard_flags} for u in utterances]


def build_context(case_row: dict[str, Any], session_row: dict[str, Any], utterance_rows_: list[dict[str, Any]],
                  settings: Settings, recorder: TrialCallRecorder) -> TrialContext:
    case = CaseFile.model_validate(case_row["case_json"])
    stored = dict(session_row.get("verdict_json") or {})
    record_summary = stored.pop(RECORD_SUMMARY_KEY, None)
    verdict = Verdict.model_validate(stored) if stored else None
    return TrialContext(
        case=case, pack=build_pack(case_row["legal_pack"]), state=state_from_row(session_row, case),
        settings=settings, recorder=recorder, transcript=[utterance_from_row(r) for r in utterance_rows_],
        fact_ledger=list(session_row.get("fact_ledger") or []), verdict=verdict,
        verdict_flags=list(session_row.get("verdict_flags") or []), record_summary=record_summary,
    )


def state_out(session_id: str, state: SessionState, guard_exhausted: bool = False) -> TrialStateOut:
    actions = allowed_actions(state)
    if state.status == "active" and awaiting(state) == "ai":
        actions = [] if guard_exhausted else ["continue"]
    limits = text_limits(state)
    return TrialStateOut(session_id=session_id, current_step=state.current_step,
                         step_title=STEP_BY_NUMBER[state.current_step].title, status=state.status,
                         awaiting=awaiting(state), allowed_actions=actions, version=state.version,
                         text_limits={"min": limits[0], "max": limits[1]} if limits else None)


def utterance_out(u: Utterance, case: CaseFile) -> TrialUtteranceOut:
    names = case.participants
    return TrialUtteranceOut(
        seq=u.seq, step=u.step, speaker_id=u.speaker_id, speaker_role=ROLE_LABELS.get(role_of(u.speaker_id), ""),
        speaker_name=names[u.speaker_id].name if u.speaker_id in names else "", is_user=u.is_user, kind=u.kind,
        text=u.text if u.is_user else render(u.text, names), addressee=u.addressee)


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
