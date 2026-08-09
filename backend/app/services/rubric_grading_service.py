"""Shared LLM-as-judge positional-grading parsing - matched/missing decided by rubric ARRAY INDEX,
never by fuzzy-matching LLM-reconstructed text back against the rubric. Originally built for
essay_service.py's essay grading (see essay_prompts.py's module docstring for why judging by
position matters); extracted here so the "Sinh tình huống minh họa" Lượt 2 feature
(scenario_grading_service.py) can reuse the exact same discipline instead of duplicating it.

Both callers pass their own rubric (essay_key_points vs a per-scenario key_points list, in the
same numbered order their own prompt presented to the model) and get back the same
matched/missing/feedback/missing_points_display shape - deliberately no score/percentage field
anywhere, per this whole feature line's core philosophy (chữa bài, không chấm điểm).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

FALLBACK_FEEDBACK = "Không thể chấm tự động đầy đủ câu trả lời này do lỗi hệ thống, vui lòng thử lại."


@dataclass
class PositionalGradingResult:
    matched: list[str]
    missing: list[str]
    feedback: str
    missing_points_display: list[str] | None


def _validate_missing_points_display(raw: Any, missing: list[str]) -> list[str] | None:
    """Display-only field - never lets a malformed value reach the frontend. Structural checks
    only (type, non-empty strings, empty-iff-no-missing-points): verifying the LLM didn't drop or
    invent content within a merged sentence isn't mechanically checkable here, so that constraint
    is enforced via each caller's own grading prompt rule, not this function."""
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        logger.warning("missing_points_display malformed (not a list of non-empty strings) - falling back")
        return None
    if len(missing) == 0:
        return [] if len(raw) == 0 else None
    if len(raw) == 0:
        logger.warning("missing_points_display empty despite %d missing rubric points - falling back", len(missing))
        return None
    return [item.strip() for item in raw]


def parse_positional_grading_response(response_text: str, rubric: list[str]) -> PositionalGradingResult:
    try:
        parsed = json.loads(response_text)
        results = list(parsed["results"])
        feedback = str(parsed.get("feedback", "")).strip()
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.exception("Failed to parse grading JSON response - treating all rubric points as missing")
        return PositionalGradingResult(
            matched=[], missing=list(rubric), feedback=FALLBACK_FEEDBACK, missing_points_display=None
        )

    if len(results) != len(rubric):
        logger.warning("Grading response length mismatch: got %d results for %d rubric points - "
                        "treating all rubric points as missing", len(results), len(rubric))
        return PositionalGradingResult(
            matched=[], missing=list(rubric), feedback=feedback or FALLBACK_FEEDBACK, missing_points_display=None
        )

    matched = [point for point, status in zip(rubric, results) if status == "matched"]
    missing = [point for point, status in zip(rubric, results) if status != "matched"]
    missing_points_display = _validate_missing_points_display(parsed.get("missing_points_display"), missing)
    return PositionalGradingResult(matched=matched, missing=missing, feedback=feedback,
                                    missing_points_display=missing_points_display)
