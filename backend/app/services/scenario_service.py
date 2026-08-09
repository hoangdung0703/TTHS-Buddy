"""Lượt 1 of the "Sinh tình huống minh họa" feature (see requirements.md): generates a fictional
scenario grounded in the conversation's own recent turns (no new retrieval) plus a hidden
key_points rubric saved for Lượt 2 (LLM-as-judge grading, not built yet - see requirements.md,
built/tested separately on purpose to control Gemini budget). Mirrors essay_service.py's
"grounded strictly in given material" discipline, except the material here is recent_turns
instead of a fixed question-bank rubric.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.prompts.scenario_prompts import SCENARIO_RESPONSE_SCHEMA, SCENARIO_SYSTEM_PROMPT, build_scenario_prompt
from app.services.gemini_client import generate_answer

logger = get_logger(__name__)


@dataclass
class ScenarioResult:
    scenario: str
    key_points: list[str]


_EMPTY_RESULT = ScenarioResult(scenario="", key_points=[])


def _parse_scenario_response(response_text: str) -> ScenarioResult:
    try:
        parsed = json.loads(response_text)
        scenario = str(parsed["scenario"]).strip()
        key_points_raw = parsed["key_points"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.exception("Failed to parse scenario generation JSON response - treating as no scenario")
        return _EMPTY_RESULT

    if not isinstance(key_points_raw, list) or not all(isinstance(item, str) for item in key_points_raw):
        logger.warning("Scenario key_points malformed (not a list of strings) - treating as no scenario")
        return _EMPTY_RESULT

    key_points = [item.strip() for item in key_points_raw if item.strip()]
    if not scenario or not key_points:
        # Either the model correctly reported "nothing to illustrate" (rule 4 - both empty) or it
        # violated the schema (one empty, one not) - both cases are unsafe to show a half-formed
        # scenario for, so treat either the same way as "no context available".
        return _EMPTY_RESULT

    return ScenarioResult(scenario=scenario, key_points=key_points)


def generate_scenario(recent_turns: list[dict[str, str]], question: str, settings: Settings) -> ScenarioResult:
    user_prompt = build_scenario_prompt(recent_turns, question)
    response_text = generate_answer(
        SCENARIO_SYSTEM_PROMPT, user_prompt, settings,
        response_json=True, response_schema=SCENARIO_RESPONSE_SCHEMA
    )
    return _parse_scenario_response(response_text)
