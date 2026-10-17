"""Phase 7: aggregates data already logged by Phase 4 (chat_query_logs) and Phase 5a
(quiz_attempts) into the dashboard's views. No new logging is introduced here - everything is
computed on read from tables that already exist.

Every read here raises DataUnavailable when it fails (after one retry on a transient error) instead
of returning an empty result. An empty result is not a neutral fallback on this page: an empty
weak-topics list renders as "Không có chủ đề nào cần ôn lại" - actively reassuring a student about
data that was never read - and empty stats render as 0% and zero attempts. get_dashboard_stats
makes two reads and fails as a whole if either does, rather than showing half-real numbers.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from supabase import Client

from app.core.data_access import execute_with_retry
from app.core.logging import get_logger
from app.services.question_bank_service import get_question_ids, is_stale_attempt

logger = get_logger(__name__)

CHAT_QUERY_LOGS_TABLE = "chat_query_logs"
QUIZ_ATTEMPTS_TABLE = "quiz_attempts"

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
WEAK_TOPIC_THRESHOLD_PERCENT = 50


def _yesterday_vn_range_utc() -> tuple[str, str]:
    """Returns [start, end) of "yesterday" in VN local time, converted to UTC ISO strings, so
    the Postgres timestamptz comparison lands on VN calendar days rather than UTC ones."""
    today_vn = datetime.now(VN_TZ).date()
    yesterday_start_vn = datetime.combine(today_vn - timedelta(days=1), time.min, tzinfo=VN_TZ)
    today_start_vn = datetime.combine(today_vn, time.min, tzinfo=VN_TZ)
    return yesterday_start_vn.isoformat(), today_start_vn.isoformat()


def get_keywords_yesterday(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    start_utc, end_utc = _yesterday_vn_range_utc()
    response = execute_with_retry(
        lambda: supabase_client.table(CHAT_QUERY_LOGS_TABLE)
        .select("citations")
        .eq("user_id", user_id)
        .gte("created_at", start_utc)
        .lt("created_at", end_utc),
        "read chat_query_logs for keywords-yesterday",
    )

    counts: dict[str, int] = defaultdict(int)
    titles: dict[str, str] = {}
    for row in response.data or []:
        # Dedupe within a single query so one answer citing the same Dieu twice doesn't
        # inflate its count relative to a Dieu asked about in two separate questions.
        seen_in_query: set[str] = set()
        for citation in row.get("citations") or []:
            dieu_number = citation.get("dieu_number")
            if not dieu_number or dieu_number in seen_in_query:
                continue
            seen_in_query.add(dieu_number)
            counts[dieu_number] += 1
            titles.setdefault(dieu_number, citation.get("dieu_title") or dieu_number)

    keywords = [
        {"dieu_number": dieu_number, "keyword": titles[dieu_number], "count": count}
        for dieu_number, count in counts.items()
    ]
    keywords.sort(key=lambda k: k["count"], reverse=True)
    return keywords


def _accumulate_quiz_topic_scores(supabase_client: Client, user_id: str,
                                   correct: dict[str, int], total: dict[str, int]) -> None:
    response = execute_with_retry(
        lambda: supabase_client.table(QUIZ_ATTEMPTS_TABLE)
        .select("answers")
        .eq("user_id", user_id),
        "read quiz_attempts for weak-topics",
    )

    live_question_ids = get_question_ids()
    for row in response.data or []:
        for answer in row.get("answers") or []:
            # Scored per ANSWER rather than per attempt: a topic's percentage should only reflect
            # questions the current bank still has, so answers left over from a replaced question
            # bank are skipped (the rows themselves are never deleted).
            if answer.get("question_id") not in live_question_ids:
                continue
            topic = answer.get("topic_category")
            if not topic:
                continue
            total[topic] += 1
            if answer.get("is_correct"):
                correct[topic] += 1


def get_weak_topics(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    correct: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)

    _accumulate_quiz_topic_scores(supabase_client, user_id, correct, total)

    weak_topics = []
    for topic, topic_total in total.items():
        score_percentage = round(100 * correct[topic] / topic_total)
        if score_percentage < WEAK_TOPIC_THRESHOLD_PERCENT:
            weak_topics.append({
                "topic_category": topic,
                "score_percentage": score_percentage,
            })

    weak_topics.sort(key=lambda t: t["score_percentage"])
    return weak_topics


def get_dashboard_stats(supabase_client: Client, user_id: str) -> dict[str, Any]:
    attempt_percentages: list[float] = []
    total_quiz_attempts = 0

    quiz_response = execute_with_retry(
        lambda: supabase_client.table(QUIZ_ATTEMPTS_TABLE)
        .select("score, total, question_ids")
        .eq("user_id", user_id),
        "read quiz_attempts for stats",
    )
    for row in quiz_response.data or []:
        if is_stale_attempt(row.get("question_ids")):
            continue
        total_quiz_attempts += 1
        if row["total"] > 0:
            attempt_percentages.append(100 * row["score"] / row["total"])

    average_score = round(sum(attempt_percentages) / len(attempt_percentages)) if attempt_percentages else 0

    dieu_studied: set[str] = set()
    chat_response = execute_with_retry(
        lambda: supabase_client.table(CHAT_QUERY_LOGS_TABLE).select("citations").eq("user_id", user_id),
        "read chat_query_logs for stats",
    )
    for row in chat_response.data or []:
        for citation in row.get("citations") or []:
            dieu_number = citation.get("dieu_number")
            if dieu_number:
                dieu_studied.add(dieu_number)

    return {
        "total_quiz_attempts": total_quiz_attempts,
        "average_score": average_score,
        "dieu_studied_count": len(dieu_studied),
    }
