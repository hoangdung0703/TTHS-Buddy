"""Request/response and SSE event models for /api/trials (design doc Mục 2.2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.trial_state_machine import ENABLED_USER_ROLES


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrialCreateRequest(_Strict):
    """No free-text brief (decision 2026-10-19): only choices from the approved lists."""
    crime_key: str
    user_role: str
    victim_present: bool = True
    witness_count: int = Field(default=1, ge=0, le=2)
    has_related_party: bool = False

    @field_validator("user_role")
    @classmethod
    def _role_enabled(cls, value: str) -> str:
        # Single source: a role is accepted only once its stage is enabled (config.user_roles).
        if value not in ENABLED_USER_ROLES:
            raise ValueError("user_role is not enabled")
        return value


class TrialTurnRequest(_Strict):
    expected_step: int = Field(ge=1, le=11)
    expected_version: int = Field(ge=0)
    # "continue" resumes an AI turn that was interrupted (client gone, guard pause); the rest map
    # onto trial_state_machine.UserAction.
    action: Literal["speak", "end_slot", "advance", "continue", "decline"]
    text: str | None = Field(default=None, max_length=6000)
    addressee: str | None = Field(default=None, max_length=16)
    target_step: int | None = Field(default=None, ge=1, le=11)


class TrialTextLimits(BaseModel):
    min: int
    max: int


class TrialProcedureNote(BaseModel):
    """Static note on the current step (Người xem only). `reviewed` stays false until the legal team
    has approved the text."""
    step: int
    title: str
    text: str
    legal_basis: list[str]
    reviewed: bool


class TrialClerkPrompt(BaseModel):
    """Thư ký only: what to note down at this step. `reviewed` stays false until the legal team
    has approved the text."""
    step: int
    text: str
    reviewed: bool


class TrialAttendanceEntry(BaseModel):
    speaker_id: str
    role: str
    name: str
    present: bool


class TrialClerkReport(BaseModel):
    """Thư ký only, while the step-1 report is due: the template report to prefill the textarea
    with (names rendered) and the summoned people per the case file, to check it against."""
    prefill: str
    attendance: list[TrialAttendanceEntry]


class TrialDeclineNote(BaseModel):
    """Bị cáo only: why "Từ chối trả lời" exists, shown next to the button. `reviewed` stays false
    until the legal team has approved the text."""
    text: str
    legal_basis: list[str]
    reviewed: bool


class TrialPendingQuestion(BaseModel):
    """Bị cáo only: the question the student must answer now (đoạn xen), so the composer can quote it
    after a reload. `seq` is that utterance in the transcript."""
    seq: int
    speaker_id: str
    speaker_role: str
    speaker_name: str
    text: str
    # The step-2 identity question only: the answer prefilled from the case file (editable).
    prefill: str | None = None
    # Present when "decline" is in allowed_actions.
    decline_note: TrialDeclineNote | None = None


class TrialRoleBrief(BaseModel):
    """Bị cáo only ("Vai của bạn", decision 9): the defendant's own character card, as a role-play
    hint. Never sent for any other role (the key is absent from GET /{id})."""
    stance: str
    knowledge: list[str]
    demeanor: str
    note: str


class TrialStateOut(BaseModel):
    session_id: uuid.UUID
    current_step: int
    step_title: str
    status: str
    awaiting: str
    allowed_actions: list[str]
    version: int
    # Character limits for the next "speak" in the current slot; null when speaking is not allowed.
    text_limits: TrialTextLimits | None = None
    # Người xem only: the procedure note of current_step; null for every other role.
    procedure_note: TrialProcedureNote | None = None
    # Thư ký only: the note-taking prompt of current_step; null for every other role.
    clerk_prompt: TrialClerkPrompt | None = None
    # Thư ký only, and only while the step-1 report is the student's turn; null otherwise.
    clerk_report: TrialClerkReport | None = None
    # Bị cáo only, while a question put to the student is pending; null otherwise.
    pending_question: TrialPendingQuestion | None = None


class TrialUtteranceOut(BaseModel):
    seq: int
    step: int
    speaker_id: str
    speaker_role: str
    speaker_name: str
    is_user: bool
    kind: str
    text: str
    addressee: str | None = None


class TrialSummaryOut(BaseModel):
    session_id: uuid.UUID
    title: str
    crime_key: str
    user_role: str
    current_step: int
    status: str
    updated_at: datetime


class TrialCrimeOut(BaseModel):
    crime_key: str
    crime_name: str
    dieu: str
    allowed_khoan: list[str]


class TrialLimitsOut(BaseModel):
    max_cases_per_day: int
    max_active_sessions: int
    max_witnesses: int
    abandon_after_days: int


class TrialRemainingOut(BaseModel):
    cases_today: int
    active_sessions: int
    # False: the usage log could not be read; cases_today is then 0 because creation is refused
    # (503 trial_usage_log_unavailable), not because the daily limit was used up.
    usage_available: bool = True


class TrialConfigOut(BaseModel):
    crimes: list[TrialCrimeOut]
    user_roles: list[str]
    limits: TrialLimitsOut
    remaining: TrialRemainingOut


class TrialListResponse(BaseModel):
    sessions: list[TrialSummaryOut]
    # Everything the new-hearing screen needs, in the same call (no separate config route).
    config: TrialConfigOut


class TrialDetailResponse(BaseModel):
    state: TrialStateOut
    title: str
    crime_key: str
    user_role: str
    disclaimer: str
    court: dict
    participants: dict[str, dict]
    case_file: dict
    steps: list[dict]
    utterances: list[TrialUtteranceOut]
    # Bị cáo sessions only; the key is left out of the response for every other role.
    role_brief: TrialRoleBrief | None = None


class TrialRecordField(BaseModel):
    label: str
    # None = no data: the frontend shows the form's dotted blank. Never filled with invented facts.
    value: str | None = None
    # True when the value is assigned by code for the simulation (date, venue, prosecutor office...),
    # not taken from the case file or the hearing.
    simulated: bool = False


class TrialRecordEntry(BaseModel):
    """One utterance of the hearing, verbatim (full names)."""
    seq: int
    step: int
    speaker_role: str
    speaker_name: str
    text: str


class TrialRecordSection(BaseModel):
    heading: str
    # "summary": show `summary` (clerk's summary, chặng 3E) instead of `entries`; "verbatim": show
    # `entries`. `summary_fallback` = a summary was attempted but failed its checks.
    # "user": `summary` holds the text the student playing Thư ký wrote (null while still empty).
    content: Literal["verbatim", "summary", "user"] = "verbatim"
    summary: str | None = None
    # Who wrote `summary` when it is not the code, e.g. "Do Thư ký (người học) ghi".
    author_note: str | None = None
    summary_fallback: bool = False
    fields: list[TrialRecordField] = []
    entries: list[TrialRecordEntry] = []
    # Fixed sentences of the form, e.g. "Hội đồng xét xử vào phòng nghị án để nghị án."
    notes: list[str] = []
    subsections: list[TrialRecordSection] = []


class TrialRecordSignature(BaseModel):
    title: str
    note: str
    name: str


class TrialRecordOut(BaseModel):
    """Biên bản phiên tòa laid out after Mẫu số 22-HS (Nghị quyết 05/2017/NQ-HĐTP)."""
    disclaimer: str
    form_reference: str
    # Lines outside the form shown right under the first simulation line (e.g. the Người xem note).
    preamble: list[str] = []
    court_name: str
    national_header: list[str]
    title: str
    subtitle: str
    opening: list[TrialRecordField]
    sections: list[TrialRecordSection]
    closing: list[TrialRecordField]
    signatures: list[TrialRecordSignature]
    # Outside Mẫu 22-HS: the judgment as pronounced, verbatim from the transcript.
    appendix: list[TrialRecordSection] = []
    # Thư ký sessions only: true until the clerk has finalised IV.2 and IV.3 (the preamble then
    # carries the "Bản nháp" line).
    draft: bool = False


class TrialClerkNotice(BaseModel):
    """One "Lưu ý" on a clerk-written section: feedback, never a refusal or a score."""
    section: Literal["iv2", "iv3"]
    code: str
    message: str


class TrialClerkSectionLimits(BaseModel):
    min: int        # suggested; shorter gives a notice
    max: int        # suggested; longer gives a notice
    hard_max: int   # refused above this (422)


class TrialClerkDraftOut(BaseModel):
    """The clerk's IV.2 / IV.3 as stored (cleaned), with the notices computed on it."""
    iv2: str
    iv3: str
    updated_at: datetime | None = None
    finalized: bool
    finalized_at: datetime | None = None
    notices: list[TrialClerkNotice]
    limits: TrialClerkSectionLimits


class TrialRecordResponse(BaseModel):
    session_id: uuid.UUID
    # Plain-text rendering of `record` (same paragraph convention as utterances), both simulation
    # lines included: for copy and print.
    text: str
    record: TrialRecordOut
    # Thư ký sessions only: the editable draft and its notices; null for every other role.
    clerk: TrialClerkDraftOut | None = None


class TrialNotesRequest(_Strict):
    # Must match trial_clerk.NOTES_MAX_CHARS (a test checks it).
    text: str = Field(max_length=20000)


class TrialNotesOut(BaseModel):
    notes: str
    updated_at: datetime | None = None
    max_chars: int


class TrialRecordDraftRequest(_Strict):
    """Either section may be omitted (null) to keep its stored text. Bounds must match
    trial_clerk.SECTION_HARD_MAX_CHARS (a test checks it)."""
    iv2: str | None = Field(default=None, max_length=6000)
    iv3: str | None = Field(default=None, max_length=6000)


class TrialSessionEvent(BaseModel):
    session_id: uuid.UUID
    title: str


class TrialDoneEvent(BaseModel):
    pass
