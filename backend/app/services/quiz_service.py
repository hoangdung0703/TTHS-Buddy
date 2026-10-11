"""MCQ format validation and answer grading. Only mcq_4choice exists in the question bank - the
mcq_true_false questions were deliberately dropped entirely (not converted) when the bank was
restructured into fixed sets (see requirements.md "Phase 5a/5b v2" Buoc B) -
EXPECTED_OPTION_COUNT is a dict keyed by question_type rather than a
single constant so a second MCQ shape could still be reintroduced later without touching
is_valid_mcq_question's logic, but there is deliberately only one entry today.

The bank file assigns each question to a fixed quiz_set - the "generate more via LLM if the bank
isn't big enough" fallback mentioned in requirements.md is not implemented: requirements.md
explicitly prioritizes the law students' pre-written questions over LLM-generated ones.
"""
from __future__ import annotations

from typing import Any

EXPECTED_OPTION_COUNT = {
    "mcq_4choice": 4,
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
