"""Lượt 2 of "Sinh tình huống minh họa" (see requirements.md): LLM-as-judge qualitative grading of
the student's free-text analysis of a Lượt 1 scenario, against that scenario's own hidden
key_points rubric (persisted by scenario_service.generate_scenario via chat_log_service). Reuses
rubric_grading_service's positional matched/missing parsing (same principle as essay_service.py) -
NO score/percentage in any form, per requirements.md's core philosophy for this feature line.
"""
from __future__ import annotations

from app.core.config import Settings
from app.prompts.scenario_grading_prompts import SCENARIO_GRADING_SYSTEM_PROMPT, build_grading_prompt
from app.services.gemini_client import generate_answer
from app.services.rubric_grading_service import PositionalGradingResult, parse_positional_grading_response


def grade_scenario_answer(
    scenario: str, key_points: list[str], user_answer: str, settings: Settings
) -> PositionalGradingResult:
    user_prompt = build_grading_prompt(scenario, key_points, user_answer)
    response_text = generate_answer(SCENARIO_GRADING_SYSTEM_PROMPT, user_prompt, settings, response_json=True)
    return parse_positional_grading_response(response_text, key_points)
