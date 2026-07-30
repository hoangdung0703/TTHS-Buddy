"""MCQ format validation and answer grading for Phase 5a. mcq_4choice (4 options) and
mcq_true_false (2 options) share the same "exactly 1 correct answer" shape, just a different
expected option count, so both are validated through the same function.

The question bank currently has 18 MCQ questions per quiz_set (15 mcq_4choice + 3
mcq_true_false, verified in ingestion/question_bank.json) - enough for a full rotation-based
attempt (see question_bank_service.QUESTIONS_PER_ATTEMPT), so the "generate more via LLM if the
bank isn't big enough" fallback mentioned in requirements.md is not implemented: it isn't
needed against the real data, and requirements.md explicitly prioritizes the law students'
pre-written questions over LLM-generated ones anyway.
"""
from __future__ import annotations

from typing import Any

EXPECTED_OPTION_COUNT = {
    "mcq_4choice": 4,
    "mcq_true_false": 2,
}


def is_valid_mcq_question(question: dict[str, Any]) -> bool:
    expected_count = EXPECTED_OPTION_COUNT.get(question.get("question_type"))
    if expected_count is None:
        return False

    options = question.get("mcq_options")
    if not isinstance(options, list) or len(options) != expected_count:
        return False
    if len(set(options)) != expected_count:
        return False

    return question.get("mcq_correct") in options


def grade_mcq_answer(question: dict[str, Any], selected_option: str) -> bool:
    return selected_option == question["mcq_correct"]
