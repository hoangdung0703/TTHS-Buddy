"""Checks on the Chủ tọa's own decision (chặng R4, design doc Mục 11.4.4, plan KE-HOACH-CHU-TOA.md Mục 3).

Feedback, never a score (decision 17): an ERROR blocks "Chốt quyết định" because no real judgment
could contain it; a WARNING is shown and the student may still lock the decision. Every finding
names the field it is about and its legal basis, checked against ingestion/chunks.json.

The legal rules live in trial_sentencing_rules (nhóm B, design doc Mục 11.16), shared with the AI
nghị án guard of the other roles; their severity table (RULES) decides error or warning. This module
only adds what is specific to the student's form: the length of the nhận định. The order of the
findings is the one the form has always shown.
"""
from __future__ import annotations

from app.models.trial import CaseFile, ChairDecision
from app.services import trial_sentencing_rules as rules
from app.services.trial_legal_pack import LegalPack
from app.services.trial_sentencing_rules import (  # noqa: F401 - re-exported for existing importers
    BLHS,
    BLTTHS,
    CIRCUMSTANCE_KHOANS,
    CONFISCATIONS,
    DIEU_54_MIN_MITIGATING,
    FINE_MIN_VND,
    PRISON_MAX_MONTHS,
    PRISON_MIN_MONTHS,
    SERIOUS_MAX_MONTHS,
    Finding,
    RuleCheck,
    is_penalty_khoan,
)

REASONING_MIN_CHARS, REASONING_MAX_CHARS = 200, 2000

# The Chủ tọa's result type: errors (hard rules), warnings (soft rules), flags.
DecisionCheck = RuleCheck


def check_decision(decision: ChairDecision, case: CaseFile, pack: LegalPack) -> DecisionCheck:
    check = DecisionCheck()
    rules.circumstances(decision, case, pack, check)
    _reasoning(decision, check)
    rules.exhibits(decision, case, check)
    rules.fine_and_civil_amounts(decision, case, pack, check)
    rules.civil_over_claim(decision, case, check)
    rules.civil_fee(decision, check)
    if not decision.guilty:
        rules.acquittal_penalty(decision, check)
        rules.acquittal_fees(decision, case, check)
    else:
        rules.conviction(decision, case, pack, check)
    return check


def _reasoning(decision: ChairDecision, check: DecisionCheck) -> None:
    length = len(decision.reasoning_summary.strip())
    if not REASONING_MIN_CHARS <= length <= REASONING_MAX_CHARS:
        check.add("reasoning_length", "reasoning_summary", f"Nhận định cần từ {REASONING_MIN_CHARS} đến "
                  f"{REASONING_MAX_CHARS} ký tự (hiện có {length}).", f"điểm d khoản 2 Điều 260 {BLTTHS}")
