"""Loads the question bank (ingestion/question_bank.json) shared by Phase 5a (MCQ) and Phase 5b
(essay), and selects questions for an attempt with rotation logic:
  - MCQ (select_quiz_questions): rotation is scoped to the single quiz_set the user chose -
    avoid repeating the previous attempt's questions at that quiz_set, topic-balanced sampling.
    Never rotates across the whole bank, since the user explicitly picks which set to practice.
  - Essay (select_essay_question): no quiz_set concept exists for essay questions (Phase 5b),
    so rotation is scoped to the whole 25-question essay pool instead.
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
MCQ_QUESTION_TYPES = ("mcq_4choice", "mcq_true_false")

# Each quiz_set has 18 MCQ questions (15 mcq_4choice + 3 mcq_true_false). 10 per attempt leaves
# enough of the set unseen to make rotation meaningful across repeated attempts, without being
# so small that topic-balanced sampling has nothing to work with.
QUESTIONS_PER_ATTEMPT = 10
RECENT_ATTEMPTS_TO_AVOID = 1


@lru_cache(maxsize=1)
def load_question_bank() -> list[dict[str, Any]]:
    questions = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
    valid = [q for q in questions if q["question_type"] == "essay" or is_valid_mcq_question(q)]
    if len(valid) != len(questions):
        logger.warning("Dropped %d invalid questions from question bank on load",
                        len(questions) - len(valid))
    return valid


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


def get_quiz_set_summaries() -> list[dict[str, Any]]:
    summaries = []
    for quiz_set in range(1, 6):
        questions = get_mcq_questions_for_set(quiz_set)
        topics: list[str] = []
        for q in questions:
            if q["topic_category"] and q["topic_category"] not in topics:
                topics.append(q["topic_category"])
        summaries.append({
            "quiz_set": quiz_set,
            "total_questions": len(questions),
            "main_topics": topics[:5],
        })
    return summaries


def _get_recent_attempt_question_ids(supabase_client: Client, user_id: str, quiz_set: int) -> set[str]:
    try:
        response = (
            supabase_client.table(QUIZ_ATTEMPTS_TABLE)
            .select("question_ids")
            .eq("user_id", user_id)
            .eq("quiz_set", quiz_set)
            .order("created_at", desc=True)
            .limit(RECENT_ATTEMPTS_TO_AVOID)
            .execute()
        )
    except Exception:
        # Missing/unreachable history must degrade to "no rotation history yet", not break
        # quiz generation - e.g. before migrations/0002_quiz_attempts.sql has been applied.
        logger.exception("Failed to read quiz attempt history (user_id=%s, quiz_set=%d) - "
                          "proceeding without rotation exclusion", user_id, quiz_set)
        return set()

    seen: set[str] = set()
    for row in response.data or []:
        seen.update(row["question_ids"])
    return seen


def _balanced_sample(questions: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Round-robins across topic_category buckets so no single topic dominates the attempt."""
    buckets: dict[str | None, list[dict[str, Any]]] = {}
    for q in questions:
        buckets.setdefault(q["topic_category"], []).append(q)
    for bucket in buckets.values():
        random.shuffle(bucket)

    selected: list[dict[str, Any]] = []
    active_buckets = [b for b in buckets.values() if b]
    while len(selected) < count and active_buckets:
        for bucket in active_buckets:
            if len(selected) == count:
                break
            selected.append(bucket.pop())
        active_buckets = [b for b in active_buckets if b]

    return selected


def select_quiz_questions(supabase_client: Client, user_id: str, quiz_set: int,
                           dieu_number: str | None = None,
                           topic_category: str | None = None) -> list[dict[str, Any]]:
    candidates = get_mcq_questions_for_set(quiz_set, dieu_number, topic_category)
    if not candidates:
        return []

    recent_ids = _get_recent_attempt_question_ids(supabase_client, user_id, quiz_set)
    fresh = [q for q in candidates if q["question_id"] not in recent_ids]

    target_count = min(QUESTIONS_PER_ATTEMPT, len(candidates))
    selected = _balanced_sample(fresh, target_count)

    if len(selected) < target_count:
        # Pool too small to fully avoid the last attempt's questions - top up with
        # recently-seen ones instead of returning a short attempt.
        already_selected_ids = {q["question_id"] for q in selected}
        leftover = [q for q in candidates if q["question_id"] not in already_selected_ids]
        selected += _balanced_sample(leftover, target_count - len(selected))

    random.shuffle(selected)
    return selected


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


ESSAY_ATTEMPTS_TABLE = "essay_attempts"

# 25 essay questions total, no quiz_set to scope rotation to - avoiding the last 5 distinct
# questions the user was served still leaves 20 fresh candidates, which is enough for
# meaningful rotation without letting the exclusion set grow so large that later attempts have
# nothing fresh left to pick from.
RECENT_ESSAY_QUESTIONS_TO_AVOID = 5


def get_essay_questions() -> list[dict[str, Any]]:
    return [q for q in load_question_bank() if q["question_type"] == "essay"]


def _get_recent_essay_question_ids(supabase_client: Client, user_id: str) -> set[str]:
    try:
        response = (
            supabase_client.table(ESSAY_ATTEMPTS_TABLE)
            .select("question_id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(RECENT_ESSAY_QUESTIONS_TO_AVOID)
            .execute()
        )
    except Exception:
        logger.exception("Failed to read essay attempt history (user_id=%s) - "
                          "proceeding without rotation exclusion", user_id)
        return set()

    return {row["question_id"] for row in response.data or []}


def select_essay_question(supabase_client: Client, user_id: str) -> dict[str, Any] | None:
    candidates = get_essay_questions()
    if not candidates:
        return None

    recent_ids = _get_recent_essay_question_ids(supabase_client, user_id)
    fresh = [q for q in candidates if q["question_id"] not in recent_ids]
    pool = fresh if fresh else candidates
    return random.choice(pool)


def save_essay_attempt(supabase_client: Client, user_id: str, question: dict[str, Any],
                        user_answer: str, grading_result: Any) -> None:
    row = {
        "user_id": user_id,
        "question_id": question["question_id"],
        "topic_category": question["topic_category"],
        "user_answer": user_answer,
        "matched_points": grading_result.matched_points,
        "missing_points": grading_result.missing_points,
        "feedback": grading_result.feedback,
        "suggested_dieu": grading_result.suggested_dieu,
    }
    try:
        supabase_client.table(ESSAY_ATTEMPTS_TABLE).insert(row).execute()
    except Exception:
        # Same tradeoff as save_quiz_attempt: persistence feeds rotation history and Phase 7/9,
        # but a transient DB failure must not turn an already-graded submission into a 500.
        logger.exception("Failed to save essay attempt (user_id=%s, question_id=%s)",
                          user_id, question["question_id"])
