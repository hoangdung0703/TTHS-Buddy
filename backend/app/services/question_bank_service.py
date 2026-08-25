"""Loads the question bank (ingestion/question_bank.json) shared by Phase 5a (MCQ) and Phase 5b
(essay), and selects questions for an attempt:
  - MCQ (select_quiz_questions): each quiz_set is a FIXED 5-question set (15 sets total, reshuffled
    once at parse time - see ingestion/parse_question_bank_v2.py, requirements.md "Phase 5a/5b v2"
    Buoc B). The UI shows sets 01-15 with persisted per-set status, not a randomly-regenerated
    subset each time, so an attempt is simply "all 5 questions of the chosen set" - no
    pool-vs-attempt-size rotation is needed any more (the whole set IS the attempt).
  - Essay (select_essay_question): only ly_thuyet remains (20 questions) - van_dung/
    ban_trac_nghiem/tinh_huong were removed at the instructor's request (copyrighted source
    material) both from question_bank.json and from ESSAY_CATEGORIES below, so any request for
    those categories 404s at the API layer rather than relying on the frontend not showing them.
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

QUIZ_SET_COUNT = 15

# Essay bank categories exposed via the API. Only ly_thuyet is offered - van_dung/
# ban_trac_nghiem/tinh_huong were pulled at the instructor's request, and are deliberately
# absent here (not just hidden in the frontend) so /banks and /banks/{category}/questions
# reject them outright even if called directly.
ESSAY_CATEGORIES = ("ly_thuyet",)


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
    for quiz_set in range(1, QUIZ_SET_COUNT + 1):
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
        "total_quiz_sets": QUIZ_SET_COUNT,
    }


def select_quiz_questions(quiz_set: int) -> list[dict[str, Any]]:
    """A quiz_set is a fixed 5-question set (see module docstring) - an "attempt" is simply all
    of that set's questions, shuffled for presentation order. No rotation/exclusion logic is
    needed any more: there is no larger pool to rotate against within a single set."""
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


ESSAY_ATTEMPTS_TABLE = "essay_attempts"

# 20 essay questions total (ly_thuyet only). Avoiding the last 5 distinct questions served
# (scoped to whichever pool is in play - a single category for bank practice, or the whole pool
# for the "Toi hoi ban tra loi" minigame, which is now the same 20-question pool since ly_thuyet
# is the only remaining category) still leaves enough fresh candidates for rotation to matter.
RECENT_ESSAY_QUESTIONS_TO_AVOID = 5


def get_essay_questions(category: str | None = None) -> list[dict[str, Any]]:
    questions = [q for q in load_question_bank() if q["question_type"] == "essay"]
    if category:
        questions = [q for q in questions if q["category"] == category]
    return questions


def _get_recent_essay_question_ids(supabase_client: Client, user_id: str, category: str | None) -> set[str]:
    try:
        query = (
            supabase_client.table(ESSAY_ATTEMPTS_TABLE)
            .select("question_id")
            .eq("user_id", user_id)
        )
        if category:
            query = query.eq("category", category)
        response = query.order("created_at", desc=True).limit(RECENT_ESSAY_QUESTIONS_TO_AVOID).execute()
    except Exception:
        logger.exception("Failed to read essay attempt history (user_id=%s, category=%s) - "
                          "proceeding without rotation exclusion", user_id, category)
        return set()

    return {row["question_id"] for row in response.data or []}


def select_essay_question(supabase_client: Client, user_id: str, category: str | None = None,
                           exclude_question_id: str | None = None) -> dict[str, Any] | None:
    candidates = get_essay_questions(category)
    if not candidates:
        return None

    recent_ids = _get_recent_essay_question_ids(supabase_client, user_id, category)
    if exclude_question_id:
        # "Cau khac" (skip): the currently-shown question must never repeat immediately, even if
        # it wasn't part of the persisted rotation history (skipping is explicitly NOT an
        # attempt - see requirements.md - so it's never written to essay_attempts at all; the
        # only way to exclude it is the caller telling us which one it just saw).
        recent_ids = recent_ids | {exclude_question_id}

    fresh = [q for q in candidates if q["question_id"] not in recent_ids]
    pool = fresh if fresh else candidates
    return random.choice(pool)


def _get_latest_essay_attempt_per_question(supabase_client: Client, user_id: str,
                                            category: str) -> dict[str, dict[str, Any]]:
    """Returns {question_id: {"missing_points": list}} for the user's most recent attempt at
    each question in this category - same "latest row wins" pattern as
    _get_latest_attempt_per_set, so the grid status can never disagree with what get_essay_banks_summary
    counts as practiced."""
    try:
        response = (
            supabase_client.table(ESSAY_ATTEMPTS_TABLE)
            .select("question_id, missing_points, created_at")
            .eq("user_id", user_id)
            .eq("category", category)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.exception("Failed to read essay_attempts for question grid (user_id=%s, category=%s) - "
                          "treating all questions as not done", user_id, category)
        return {}

    latest: dict[str, dict[str, Any]] = {}
    for row in response.data or []:
        question_id = row["question_id"]
        if question_id not in latest:  # rows are already ordered newest-first
            latest[question_id] = {"missing_points": row.get("missing_points") or []}
    return latest


def get_essay_bank_question_list(supabase_client: Client, user_id: str, category: str) -> list[dict[str, Any]]:
    """All questions in one essay bank, in bank order, each tagged with the status derived from
    the user's latest attempt at that question (or "not_done" if never attempted) - backs the
    question grid (requirements.md "Doi luong Tu luan")."""
    questions = get_essay_questions(category)
    latest_by_question = _get_latest_essay_attempt_per_question(supabase_client, user_id, category)

    result = []
    for order, question in enumerate(questions, start=1):
        attempt = latest_by_question.get(question["question_id"])
        if attempt is None:
            status = "not_done"
        elif attempt["missing_points"]:
            status = "needs_review"
        else:
            status = "done"
        result.append({
            "question_id": question["question_id"],
            "order": order,
            "question_text": question["question_text"],
            "status": status,
        })
    return result


def get_essay_banks_summary(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    try:
        response = (
            supabase_client.table(ESSAY_ATTEMPTS_TABLE)
            .select("category, question_id")
            .eq("user_id", user_id)
            .execute()
        )
        practiced_by_category: dict[str, set[str]] = {}
        for row in response.data or []:
            if row.get("category"):
                practiced_by_category.setdefault(row["category"], set()).add(row["question_id"])
    except Exception:
        logger.exception("Failed to read essay_attempts for banks summary (user_id=%s)", user_id)
        practiced_by_category = {}

    return [
        {
            "category": category,
            "total_questions": len(get_essay_questions(category)),
            "questions_practiced": len(practiced_by_category.get(category, set())),
        }
        for category in ESSAY_CATEGORIES
    ]


def save_essay_attempt(supabase_client: Client, user_id: str, question: dict[str, Any],
                        user_answer: str, grading_result: Any) -> None:
    row = {
        "user_id": user_id,
        "question_id": question["question_id"],
        "topic_category": question["topic_category"],
        "category": question["category"],
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
