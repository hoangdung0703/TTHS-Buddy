"""LLM-as-judge grading for Phase 5b essay questions. Grounds strictly in each question's
essay_key_points rubric (from ingestion/question_bank.json, spot-checked in Phase 5a) - the LLM
never invents its own pass/fail criteria, it only classifies which rubric points the student's
answer covers. suggested_dieu is derived directly from the question's own legal-basis text
(the "explanation" field, e.g. "Cơ sở pháp lý: Điều 13 và Điều 15 BLTTHS năm 2015."), not
LLM-generated, so it can never suggest an Điều that isn't actually grounded in the source data.

The actual matched/missing-by-position parsing lives in rubric_grading_service.py, shared with
scenario_grading_service.py (Lượt 2 of "Sinh tình huống minh họa") - this module only supplies the
essay-specific rubric source (essay_key_points) and suggested_dieu extraction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.prompts.essay_prompts import ESSAY_GRADING_SYSTEM_PROMPT, build_grading_prompt
from app.services.gemini_client import generate_answer
from app.services.rubric_grading_service import parse_positional_grading_response

# Same convention as parse_question_bank.py / rag_service.py - a student-typed or already
# clean-text "explanation" field uses standard Vietnamese diacritics.
DIEU_NUMBER_PATTERN = re.compile(r"Điều\s+(\d+[a-zA-Z]?)")


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


def grade_essay_answer(question: dict[str, Any], user_answer: str, settings: Settings) -> EssayGradingResult:
    rubric: list[str] = question["essay_key_points"]
    user_prompt = build_grading_prompt(question["question_text"], rubric, user_answer)
    response_text = generate_answer(ESSAY_GRADING_SYSTEM_PROMPT, user_prompt, settings, response_json=True)

    grading = parse_positional_grading_response(response_text, rubric)
    suggested_dieu = _extract_suggested_dieu(question)

    return EssayGradingResult(
        matched_points=grading.matched, missing_points=grading.missing, feedback=grading.feedback,
        suggested_dieu=suggested_dieu, missing_points_display=grading.missing_points_display,
    )
