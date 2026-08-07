"""LLM-as-judge grading for Phase 5b essay questions. Grounds strictly in each question's
essay_key_points rubric (from ingestion/question_bank.json, spot-checked in Phase 5a) - the LLM
never invents its own pass/fail criteria, it only classifies which rubric points the student's
answer covers. suggested_dieu is derived directly from the question's own legal-basis text
(the "explanation" field, e.g. "Cơ sở pháp lý: Điều 13 và Điều 15 BLTTHS năm 2015."), not
LLM-generated, so it can never suggest an Điều that isn't actually grounded in the source data.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.prompts.essay_prompts import ESSAY_GRADING_SYSTEM_PROMPT, build_grading_prompt
from app.services.gemini_client import generate_answer

logger = get_logger(__name__)

# Same convention as parse_question_bank.py / rag_service.py - a student-typed or already
# clean-text "explanation" field uses standard Vietnamese diacritics.
DIEU_NUMBER_PATTERN = re.compile(r"Điều\s+(\d+[a-zA-Z]?)")

FALLBACK_FEEDBACK = "Không thể chấm tự động đầy đủ câu trả lời này do lỗi hệ thống, vui lòng thử lại."


@dataclass
class EssayGradingResult:
    matched_points: list[str]
    missing_points: list[str]
    feedback: str
    suggested_dieu: list[str]
    missing_points_display: list[str] | None = None


def _extract_suggested_dieu(question: dict[str, Any]) -> list[str]:
    text = question.get("explanation") or ""
    seen: list[str] = []
    for match in DIEU_NUMBER_PATTERN.finditer(text):
        dieu = match.group(1)
        if dieu not in seen:
            seen.append(dieu)
    return seen


def _validate_missing_points_display(raw: Any, missing: list[str]) -> list[str] | None:
    """Display-only field - never lets a malformed value reach the frontend. Structural checks
    only (type, non-empty strings, empty-iff-no-missing-points): verifying the LLM didn't drop or
    invent content within a merged sentence isn't mechanically checkable here, so that constraint
    is enforced via the prompt (essay_prompts.py rule 8), not this function."""
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


def _parse_grading_response(
    response_text: str, rubric: list[str]
) -> tuple[list[str], list[str], str, list[str] | None]:
    try:
        parsed = json.loads(response_text)
        results = list(parsed["results"])
        feedback = str(parsed.get("feedback", "")).strip()
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.exception("Failed to parse essay grading JSON response - treating all rubric points as missing")
        return [], list(rubric), FALLBACK_FEEDBACK, None

    if len(results) != len(rubric):
        logger.warning("Grading response length mismatch: got %d results for %d rubric points - "
                        "treating all rubric points as missing", len(results), len(rubric))
        return [], list(rubric), feedback or FALLBACK_FEEDBACK, None

    matched = [point for point, status in zip(rubric, results) if status == "matched"]
    missing = [point for point, status in zip(rubric, results) if status != "matched"]
    missing_points_display = _validate_missing_points_display(parsed.get("missing_points_display"), missing)
    return matched, missing, feedback, missing_points_display


def grade_essay_answer(question: dict[str, Any], user_answer: str, settings: Settings) -> EssayGradingResult:
    rubric: list[str] = question["essay_key_points"]
    user_prompt = build_grading_prompt(question["question_text"], rubric, user_answer)
    response_text = generate_answer(ESSAY_GRADING_SYSTEM_PROMPT, user_prompt, settings, response_json=True)

    matched, missing, feedback, missing_points_display = _parse_grading_response(response_text, rubric)
    suggested_dieu = _extract_suggested_dieu(question)

    return EssayGradingResult(
        matched_points=matched, missing_points=missing, feedback=feedback, suggested_dieu=suggested_dieu,
        missing_points_display=missing_points_display,
    )
