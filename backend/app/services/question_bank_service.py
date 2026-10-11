"""Loads the question bank (ingestion/question_bank.json) and selects MCQ questions for an
attempt. Each quiz_set is a fixed set of questions pre-assigned in the bank file; the UI shows
the sets with persisted per-set status, not a randomly-regenerated subset each time, so an
attempt is simply "all questions of the chosen set" - no pool-vs-attempt-size rotation is
needed (the whole set IS the attempt).
"""
from __future__ import annotations

import json
import random
from functools import lru_cache
from typing import Any

from supabase import Client

from app.core.config import QUESTION_BANK_PATH
from app.core.logging import get_logger
from app.services.quiz_service import is_valid_mcq_question

logger = get_logger(__name__)

QUIZ_ATTEMPTS_TABLE = "quiz_attempts"
MCQ_QUESTION_TYPES = ("mcq_4choice",)


@lru_cache(maxsize=1)
def load_question_bank() -> list[dict[str, Any]]:
    questions = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
    valid = [q for q in questions if is_valid_mcq_question(q)]
    if len(valid) != len(questions):
        logger.warning("Dropped %d invalid questions from question bank on load",
                        len(questions) - len(valid))
    return valid


@lru_cache(maxsize=1)
def get_quiz_set_ids() -> tuple[int, ...]:
    """The quiz_set ids the bank actually defines, ascending. Derived from the data rather than a
    constant so a replacement question bank can ship any number of sets (or none at all, while the
    law students are still compiling it) without a code change."""
    return tuple(sorted({
        q["quiz_set"] for q in load_question_bank()
        if q["question_type"] in MCQ_QUESTION_TYPES and q["quiz_set"] is not None
    }))


def get_mcq_questions_for_set(quiz_set: int, dieu_number: str | None = None,
                               topic_category: str | None = None) -> list[dict[str, Any]]:
    questions = [
        q for q in load_question_bank()
        if q["question_type"] in MCQ_QUESTION_TYPES and q["quiz_set"] == quiz_set
    ]
    if dieu_number:
        questions = [q for q in questions if q["dieu_number"] == dieu_number]
    if topic_category:
        questions = [q for q in questions if q["topic_category"] == topic_category]
    return questions


def _get_latest_attempt_per_set(supabase_client: Client, user_id: str) -> dict[int, dict[str, int]]:
    """Returns {quiz_set: {"score": int, "total": int}} for the user's most recent attempt at
    each set they've touched - the single source both get_quiz_set_summaries (per-set status)
    and get_quiz_stats (overall %/sets-touched) are built from, so they can never disagree with
    each other about which attempt is "the" latest one for a given set."""
    try:
        response = (
            supabase_client.table(QUIZ_ATTEMPTS_TABLE)
            .select("quiz_set, score, total, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.exception("Failed to read quiz_attempts for user_id=%s - treating all sets as untouched", user_id)
        return {}

    latest: dict[int, dict[str, int]] = {}
    for row in response.data or []:
        quiz_set = row["quiz_set"]
        if quiz_set not in latest:  # rows are already ordered newest-first
            latest[quiz_set] = {"score": row["score"], "total": row["total"]}
    return latest


def get_quiz_set_summaries(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    latest_by_set = _get_latest_attempt_per_set(supabase_client, user_id)
    summaries = []
    for quiz_set in get_quiz_set_ids():
        total_questions = len(get_mcq_questions_for_set(quiz_set))
        attempt = latest_by_set.get(quiz_set)
        status = (
            {"kind": "done", "correct_count": attempt["score"]}
            if attempt is not None
            else {"kind": "untouched", "correct_count": 0}
        )
        summaries.append({
            "quiz_set_id": quiz_set,
            "total_questions": total_questions,
            "status": status,
        })
    return summaries


def get_quiz_stats(supabase_client: Client, user_id: str) -> dict[str, Any]:
    latest_by_set = _get_latest_attempt_per_set(supabase_client, user_id)
    correct_total = sum(a["score"] for a in latest_by_set.values())
    questions_total = sum(a["total"] for a in latest_by_set.values())
    return {
        "average_score_percentage": round(100 * correct_total / questions_total) if questions_total > 0 else 0,
        "correct_total": correct_total,
        "questions_total": questions_total,
        "quiz_sets_attempted": len(latest_by_set),
        "total_quiz_sets": len(get_quiz_set_ids()),
    }


def select_quiz_questions(quiz_set: int) -> list[dict[str, Any]]:
    """An "attempt" is simply all of that set's questions, shuffled for presentation order (see
    module docstring) - no rotation/exclusion logic is needed, there is no larger pool to rotate
    against within a single set."""
    candidates = get_mcq_questions_for_set(quiz_set)
    shuffled = candidates[:]
    random.shuffle(shuffled)
    return shuffled


def save_quiz_attempt(supabase_client: Client, user_id: str, quiz_set: int,
                       question_ids: list[str], answers: list[dict[str, Any]],
                       score: int, total: int) -> None:
    row = {
        "user_id": user_id,
        "quiz_set": quiz_set,
        "question_ids": question_ids,
        "answers": answers,
        "score": score,
        "total": total,
    }
    try:
        supabase_client.table(QUIZ_ATTEMPTS_TABLE).insert(row).execute()
    except Exception:
        # Persistence feeds rotation history and Phase 7 stats, but a transient DB failure
        # must not turn an already-graded submission into a 500 for the student.
        logger.exception("Failed to save quiz attempt (user_id=%s, quiz_set=%d)", user_id, quiz_set)
