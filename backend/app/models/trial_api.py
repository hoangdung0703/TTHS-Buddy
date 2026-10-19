"""Request/response and SSE event models for /api/trials (design doc Mục 2.2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrialCreateRequest(_Strict):
    """No free-text brief (decision 2026-10-19): only choices from the approved lists."""
    crime_key: str
    user_role: Literal["ksv", "luat_su"]
    victim_present: bool = True
    witness_count: int = Field(default=1, ge=0, le=2)
    has_related_party: bool = False


class TrialTurnRequest(_Strict):
    expected_step: int = Field(ge=1, le=11)
    expected_version: int = Field(ge=0)
    # "continue" resumes an AI turn that was interrupted (client gone, guard pause); the rest map
    # onto trial_state_machine.UserAction.
    action: Literal["speak", "end_slot", "advance", "continue"]
    text: str | None = Field(default=None, max_length=6000)
    addressee: str | None = Field(default=None, max_length=16)
    target_step: int | None = Field(default=None, ge=1, le=11)


class TrialTextLimits(BaseModel):
    min: int
    max: int


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


class TrialRecordResponse(BaseModel):
    session_id: uuid.UUID
    text: str


class TrialSessionEvent(BaseModel):
    session_id: uuid.UUID
    title: str


class TrialDoneEvent(BaseModel):
    pass
