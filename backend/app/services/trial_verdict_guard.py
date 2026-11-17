"""Checks on the structured AI nghị án decision before any tuyên án text is written (design doc
Mục 5.2, Mục 11.16).

Since nhóm B the legal rules are the ones the Chủ tọa's form uses (trial_sentencing_rules): a HARD
finding rejects the decision (it is regenerated once with the findings as feedback, then the hearing
pauses); a SOFT finding is measured only - its code is logged with the call, never blocks. The
`penalty_unchecked` flag (frame of the chosen khoản not parsed with certainty, decision 2026-10-19)
still travels in `flags` and is stored with the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.trial import CaseFile, Verdict
from app.services.trial_case_validator import evidence_fact_map, remap_fact_ids
from app.services.trial_legal_pack import LegalPack
from app.services.trial_sentencing_rules import (  # noqa: F401 - re-exported for existing importers
    DIEU_54_MIN_MITIGATING,
    NON_CUSTODIAL_MIN_MONTHS,
    PROBATION_MAX_MONTHS,
    PROBATION_MIN_MONTHS,
    SUSPENDED_MAX_PRISON_MONTHS,
    Finding,
    PenaltyFrame,
    check_ai_decision,
    parse_penalty_frame,
)


@dataclass
class VerdictCheck:
    """`errors`: messages of the hard findings (with their legal basis), used as regeneration
    feedback; `hard`/`soft`: the findings themselves; `flags`: stored with the verdict."""
    hard: list[Finding] = field(default_factory=list)
    soft: list[Finding] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return [f"{f.message} ({'; '.join(f.basis)})" for f in self.hard]

    def labels(self) -> list[str]:
        """Codes for the call log: "verdict:<code>" blocks, "soft:<code>" is measured only."""
        return [f"verdict:{f.code}" for f in self.hard] + [f"soft:{f.code}" for f in self.soft] + self.flags


def normalise_verdict(verdict: Verdict, case: CaseFile) -> Verdict:
    """Same repair as at case generation: an evidence id cited as a fact becomes its linked fact."""
    fact_ids = {f.id for f in case.draft.facts}
    by_evidence = evidence_fact_map(case.draft.evidence, fact_ids)

    def fix(items):
        return [i.model_copy(update={"fact_ids": remap_fact_ids(i.fact_ids, fact_ids, by_evidence)}) for i in items]
    return verdict.model_copy(update={"mitigating": fix(verdict.mitigating), "aggravating": fix(verdict.aggravating)})


def check_verdict(verdict: Verdict, case: CaseFile, pack: LegalPack) -> VerdictCheck:
    check = check_ai_decision(verdict, case, pack)
    return VerdictCheck(hard=list(check.errors), soft=list(check.warnings), flags=list(dict.fromkeys(check.flags)))
