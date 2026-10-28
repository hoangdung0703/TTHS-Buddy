"""Pydantic models for "Phiên tòa giả định" (design doc Mục 3.2).

Two layers:
- CaseDraft: exactly what the model generates. It contains NO personal names: every person is
  referred to by a placeholder id in braces ("{BI_CAO}", "{NLC_1}"). Names are assigned by code
  (trial_names.py) after validation, so a name from the sample judgment or a real person's name
  can never come out of the model.
- CaseFile: the stored case = draft + court info + code-assigned names + disclaimer.

Every model forbids extra fields, so a generated JSON with an unexpected key fails validation
instead of being silently accepted.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 2: extra_amounts, compensation_vnd, defendant_plea and the code-chosen knobs (chặng 2).
# 3: each inconsistency carries its own claimed_amount_vnd.
# 4: evidence links to the fact it proves (fact_id).
CASE_SCHEMA_VERSION = 4

TRIAL_DISCLAIMER = (
    "Mô phỏng học tập · Không phải phiên tòa hay bản án thật · "
    "Nhân vật và tình tiết đều là giả định."
)

UserRole = Literal["ksv", "luat_su"]  # phase 1 roles; trial_state_machine knows the full set
EvidenceType = Literal["vat_chung", "giam_dinh", "dinh_gia", "tai_lieu"]
Gender = Literal["nam", "nu"]
PleaValue = Literal["nhan_toan_bo", "nhan_mot_phan", "choi_toi"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonDraft(_Strict):
    id: str
    gender: Gender
    age: int
    occupation: str
    residence_place: str
    stance: str
    statement_summary: str
    knowledge: list[str]
    demeanor: str


class DefendantDraft(PersonDraft):
    education: str
    prior_record: str
    preventive_measure: str


class FactDraft(_Strict):
    id: str
    time: str
    place: str
    description: str


class EvidenceDraft(_Strict):
    id: str
    type: EvidenceType
    description: str
    value_vnd: int | None = None
    injury_percent: int | None = None
    # The fact this evidence proves. Lets code repair a circumstance that cites the evidence id
    # where a fact id belongs (remap_fact_ids) - seen in case generation and in nghị án.
    fact_id: str | None = None


class Inconsistency(_Strict):
    """One point where a pre-trial statement departs from the file. `claimed_amount_vnd` is the
    amount this person claimed, when the inconsistency is about money: code adds it to the
    declared amounts, so the money guard accepts it without the model having to remember to
    declare it elsewhere (A5 runs 2026-10-19 failed 3 times on exactly that)."""
    text: str
    claimed_amount_vnd: int | None = None


class PretrialStatement(_Strict):
    person_id: str
    summary: str
    inconsistencies: list[Inconsistency]


class ChargeDraft(_Strict):
    dieu: str
    khoan: str
    diem: list[str]
    crime_name: str


class CircumstanceDraft(_Strict):
    khoan: str
    diem: str
    fact_ids: list[str]


class CivilClaimDraft(_Strict):
    claimant_id: str
    amount_vnd: int
    basis: str


class ExtraAmount(_Strict):
    """A money amount the case mentions that is neither the measure value, an evidence valuation nor
    the civil claim - e.g. what a buyer paid for the stolen phone. Declaring it is what lets the
    money guard accept it (spike 2026-10-19: such side amounts failed a case outright)."""
    label: str
    amount_vnd: int
    evidence_id: str | None = None


class CaseDraft(_Strict):
    title: str
    incident_summary: str
    defendant: DefendantDraft
    victim: PersonDraft
    witnesses: list[PersonDraft]
    related_party: PersonDraft | None = None
    facts: list[FactDraft]
    evidence: list[EvidenceDraft]
    pretrial_statements: list[PretrialStatement]
    charge: ChargeDraft
    # Property value in VND (Điều 171/173/174) or injury percent (Điều 134): the number that
    # decides the khoản, checked against the evidence and the configured bands.
    measure_value: int
    defendant_plea: PleaValue
    # Amount the defendant has already paid back / compensated before trial; None = nothing paid.
    compensation_vnd: int | None = None
    extra_amounts: list[ExtraAmount] = []
    mitigating: list[CircumstanceDraft]
    aggravating: list[CircumstanceDraft]
    civil_claim: CivilClaimDraft | None = None
    indictment_text: str


class CaseOptions(_Strict):
    """What the student chooses (no free-text brief in phase 1, decision 2026-10-19)."""
    crime_key: str
    user_role: UserRole
    victim_present: bool = True
    witness_count: int = Field(default=1, ge=0, le=2)
    has_related_party: bool = False


class CaseKnobs(_Strict):
    """Chosen by code before generation (trial_knobs.py); the validator holds the draft to them."""
    khoan: str
    plea: PleaValue
    has_compensation: bool
    aggravating_points: list[str]
    mitigating_points: list[str]


class Participant(_Strict):
    id: str
    role: str
    name: str
    gender: Gender | None = None


class CourtInfo(_Strict):
    name: str
    hearing_date: str
    venue: str


class CaseFile(_Strict):
    schema_version: int = CASE_SCHEMA_VERSION
    crime_key: str
    disclaimer: str = TRIAL_DISCLAIMER
    options: CaseOptions
    knobs: CaseKnobs
    court: CourtInfo
    incident_date: str
    participants: dict[str, Participant]
    draft: CaseDraft


# --- Gemini responseSchema helpers ---------------------------------------------------------------
# Written by hand in Gemini's OpenAPI subset (STRING/INTEGER/OBJECT/ARRAY, enum, nullable). The
# case-generation schema is built per case (trial_case_frame.fill_schema, chặng 3H); Pydantic
# remains the authority and rejects anything off.

def _obj(properties: dict, required: list[str] | None = None, nullable: bool = False) -> dict:
    schema: dict = {"type": "OBJECT", "properties": properties,
                    "required": required if required is not None else list(properties)}
    if nullable:
        schema["nullable"] = True
    return schema


_STR = {"type": "STRING"}
_STR_LIST = {"type": "ARRAY", "items": _STR}


# --- Nghị án decision (step 10), kept hidden from the student until tuyên án ------------------

class VerdictCircumstance(_Strict):
    khoan: str
    diem: str
    fact_ids: list[str]


class Verdict(_Strict):
    guilty: bool
    dieu: str
    khoan: str
    diem: list[str]
    penalty_type: Literal["tu", "cai_tao_khong_giam_giu", "phat_tien", "khong"]
    penalty_months: int | None = None
    fine_vnd: int | None = None
    suspended: bool = False
    probation_months: int | None = None
    applies_dieu_54: bool = False
    mitigating: list[VerdictCircumstance]
    aggravating: list[VerdictCircumstance]
    civil_amount_vnd: int | None = None
    reasoning_summary: str


VERDICT_RESPONSE_SCHEMA: dict = _obj({
    "guilty": {"type": "BOOLEAN"},
    "dieu": _STR, "khoan": _STR, "diem": _STR_LIST,
    "penalty_type": {"type": "STRING", "enum": ["tu", "cai_tao_khong_giam_giu", "phat_tien", "khong"]},
    "penalty_months": {"type": "INTEGER", "nullable": True},
    "fine_vnd": {"type": "INTEGER", "nullable": True},
    "suspended": {"type": "BOOLEAN"},
    "probation_months": {"type": "INTEGER", "nullable": True},
    "applies_dieu_54": {"type": "BOOLEAN"},
    "mitigating": {"type": "ARRAY", "items": _obj({"khoan": _STR, "diem": _STR, "fact_ids": _STR_LIST})},
    "aggravating": {"type": "ARRAY", "items": _obj({"khoan": _STR, "diem": _STR, "fact_ids": _STR_LIST})},
    "civil_amount_vnd": {"type": "INTEGER", "nullable": True},
    "reasoning_summary": _STR,
}, required=["guilty", "dieu", "khoan", "diem", "penalty_type", "suspended", "applies_dieu_54",
             "mitigating", "aggravating", "reasoning_summary"])
