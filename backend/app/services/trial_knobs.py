"""Diversity knobs for case generation (chặng 2, A2): CODE picks the shape of each case before
the model writes it, and the validator checks the draft keeps to it. Spike 2026-10-19 showed why:
left to itself the model produced near-identical cases (mitigating always b/s or s/i, never an
aggravating circumstance)."""
from __future__ import annotations

import random

from app.models.trial import CaseKnobs
from app.services.trial_config import (
    AGGRAVATING_POOL,
    BLHS_DOCUMENT,
    FORBIDDEN_POINT_TEXT,
    LESS_SERIOUS_KHOAN,
    MITIGATING_CRIME_ONLY,
    MITIGATING_LESS_SERIOUS_ONLY,
    MITIGATING_NEEDS_COMPENSATION,
    MITIGATING_NEEDS_FULL_ADMISSION,
    MITIGATING_NEEDS_SOME_ADMISSION,
    MITIGATING_POOL,
    PLEAS,
    CrimeConfig,
)
from app.services.trial_legal_pack import LegalPack


def eligible_mitigating(crime: CrimeConfig, khoan: str, plea: str, has_compensation: bool,
                        pack: LegalPack) -> list[str]:
    article = pack.get(BLHS_DOCUMENT, "51")
    points = []
    for letter in MITIGATING_POOL:
        if article is None or not article.has_diem("1", letter):
            continue
        if FORBIDDEN_POINT_TEXT.search(article.khoans["1"].diem_text(letter)):
            continue
        if letter in MITIGATING_NEEDS_COMPENSATION and not has_compensation:
            continue
        if letter in MITIGATING_NEEDS_FULL_ADMISSION and plea != "nhan_toan_bo":
            continue
        if letter in MITIGATING_NEEDS_SOME_ADMISSION and plea == "choi_toi":
            continue
        if letter in MITIGATING_LESS_SERIOUS_ONLY and khoan not in LESS_SERIOUS_KHOAN.get(crime.dieu, frozenset()):
            continue
        if letter in MITIGATING_CRIME_ONLY and crime.dieu not in MITIGATING_CRIME_ONLY[letter]:
            continue
        points.append(letter)
    return points


def eligible_aggravating(crime: CrimeConfig, pack: LegalPack) -> list[str]:
    article = pack.get(BLHS_DOCUMENT, "52")
    return [p for p in AGGRAVATING_POOL.get(crime.dieu, ())
            if article is not None and article.has_diem("1", p)
            and not FORBIDDEN_POINT_TEXT.search(article.khoans["1"].diem_text(p))]


def choose_knobs(crime: CrimeConfig, pack: LegalPack, rng: random.Random, *, plea: str | None = None,
                 has_aggravating: bool | None = None) -> CaseKnobs:
    """`plea` / `has_aggravating` force those knobs (evaluation coverage); the rest stays random and
    every rule (which mitigating points a plea allows, ...) is applied to the forced value."""
    khoan = rng.choice(crime.allowed_khoan)
    drawn_plea = rng.choice(PLEAS)
    plea = plea or drawn_plea
    has_compensation = rng.random() < 0.5
    drawn_aggravating = rng.random() < 0.5
    has_aggravating = drawn_aggravating if has_aggravating is None else has_aggravating
    aggravating_pool = eligible_aggravating(crime, pack)
    aggravating = [rng.choice(aggravating_pool)] if has_aggravating and aggravating_pool else []
    pool = eligible_mitigating(crime, khoan, plea, has_compensation, pack)
    count = min(len(pool), rng.choice((1, 2, 2, 3)))
    mitigating = sorted(rng.sample(pool, count)) if pool else []
    if has_compensation and "b" in pool and "b" not in mitigating:
        mitigating = sorted({*mitigating[:-1], "b"}) if mitigating else ["b"]
    return CaseKnobs(khoan=khoan, plea=plea, has_compensation=has_compensation,
                     aggravating_points=aggravating, mitigating_points=mitigating)
