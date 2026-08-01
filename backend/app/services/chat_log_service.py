"""Persists every chat query + retrieved chunks + answer into Postgres (Supabase table
chat_query_logs, see migrations/0001_chat_query_logs.sql) for Phase 9 evaluation - citation
accuracy, groundedness, and correct-refusal rate all need the retrieved chunks, not just the
final answer text.
"""
from __future__ import annotations

import uuid
from typing import Any

from supabase import Client

from app.core.logging import get_logger
from app.services.rag_service import RagAnswer, RetrievedChunk

logger = get_logger(__name__)

CHAT_QUERY_LOGS_TABLE = "chat_query_logs"
# How many prior turns of the SAME conversation feed into query rewriting + the final answer
# prompt - deliberately small per requirements.md Phase 4 Extension ("khong phai toan bo lich
# su") to avoid token bloat on long conversations.
RECENT_TURNS_LIMIT = 3

# Phase 4 Extension 2: the Sidebar's "title" for a conversation is its first question, possibly
# long - truncated here so the list view stays a clean chip/row, not a full sentence.
CONVERSATION_TITLE_MAX_LENGTH = 60


def get_recent_turns(supabase_client: Client, user_id: str, conversation_id: uuid.UUID) -> list[dict[str, str]]:
    """Returns up to RECENT_TURNS_LIMIT prior turns of this conversation, oldest first, as
    {"question", "answer"} pairs - the rewritten_question (self-contained) is preferred over the
    raw question when available, since that's what the history should read like for the next
    rewrite/generation step."""
    try:
        response = (
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("question, rewritten_question, answer")
            .eq("user_id", user_id)
            .eq("conversation_id", str(conversation_id))
            .order("created_at", desc=True)
            .limit(RECENT_TURNS_LIMIT)
            .execute()
        )
    except Exception:
        # Missing/unreachable history must degrade to "first turn of the conversation", not
        # break the chat request - e.g. before migrations/0004_chat_multiturn.sql has been
        # applied.
        logger.exception(
            "Failed to read conversation history (user_id=%s, conversation_id=%s) - "
            "proceeding as if this is the first turn", user_id, conversation_id
        )
        return []

    rows = list(reversed(response.data or []))
    return [{"question": row.get("rewritten_question") or row["question"], "answer": row["answer"]} for row in rows]


def _truncate_title(question: str) -> str:
    stripped = question.strip()
    if len(stripped) <= CONVERSATION_TITLE_MAX_LENGTH:
        return stripped
    return stripped[:CONVERSATION_TITLE_MAX_LENGTH].rstrip() + "…"


def list_conversations(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    """Groups chat_query_logs rows by conversation_id, most-recently-updated first. Grouping is
    done in Python from one filtered select, not a Postgres GROUP BY/RPC - this codebase has no
    custom Postgres functions anywhere (see dashboard_service.py for the same aggregate-on-read
    pattern used for keywords/weak-topics), only the supabase-py fluent .table() client. Rows
    with conversation_id IS NULL (logged before migrations/0004_chat_multiturn.sql, or before a
    client ever attached one) are excluded - they predate the conversation concept and can't be
    grouped into one.

    Ownership: filtered by user_id in this same query (the backend uses the Supabase
    service-role key, which bypasses RLS - per migrations/0001 comments - so this explicit
    filter is the ONLY thing preventing one user's rows from leaking into another's list)."""
    try:
        response = (
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("conversation_id, question, created_at")
            .eq("user_id", user_id)
            .not_.is_("conversation_id", "null")
            .order("created_at", desc=False)
            .execute()
        )
    except Exception:
        logger.exception("Failed to list conversations (user_id=%s)", user_id)
        return []

    # Rows arrive oldest-first (asc), so the first time a conversation_id is seen its question
    # is the conversation's opening question (-> title), and each subsequent sighting keeps
    # pushing updated_at forward to that conversation's latest turn.
    grouped: dict[str, dict[str, Any]] = {}
    for row in response.data or []:
        conversation_id = row["conversation_id"]
        if conversation_id not in grouped:
            grouped[conversation_id] = {
                "conversation_id": conversation_id,
                "title": _truncate_title(row["question"]),
                "updated_at": row["created_at"],
            }
        else:
            grouped[conversation_id]["updated_at"] = row["created_at"]

    conversations = list(grouped.values())
    conversations.sort(key=lambda c: c["updated_at"], reverse=True)
    return conversations


def get_conversation_detail(supabase_client: Client, user_id: str,
                             conversation_id: uuid.UUID) -> list[dict[str, Any]] | None:
    """Returns all turns of one conversation, oldest first, or None if it doesn't exist OR
    doesn't belong to this user - both cases are indistinguishable on purpose (404, not 403):
    ownership is enforced by filtering on user_id in the SAME query as conversation_id, so a
    nonexistent conversation_id and another user's real conversation_id both come back as an
    empty result here, never revealing to a caller that a given id belongs to someone else."""
    try:
        response = (
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("question, answer, created_at")
            .eq("user_id", user_id)
            .eq("conversation_id", str(conversation_id))
            .order("created_at", desc=False)
            .execute()
        )
    except Exception:
        logger.exception(
            "Failed to read conversation detail (user_id=%s, conversation_id=%s)", user_id, conversation_id
        )
        return None

    rows = response.data or []
    if not rows:
        return None

    return [{"question": row["question"], "answer": row["answer"], "created_at": row["created_at"]} for row in rows]


def _serialize_retrieved_chunk(chunk: RetrievedChunk) -> dict[str, Any]:
    payload = chunk.payload
    return {
        "point_id": chunk.point_id,
        "score": chunk.score,
        "is_exact_match": chunk.is_exact_match,
        "source_type": payload["source_type"],
        "source_document": payload["source_document"],
        "dieu_number": payload["dieu_number"],
        "khoan_number": payload["khoan_number"],
    }


def log_chat_query(supabase_client: Client, user_id: str, conversation_id: uuid.UUID, question: str,
                    rewritten_question: str, result: RagAnswer) -> None:
    row = {
        "user_id": user_id,
        "conversation_id": str(conversation_id),
        "question": question,
        "rewritten_question": rewritten_question,
        "answer": result.answer,
        "is_fallback": result.is_fallback,
        "used_academic_reference": result.used_academic_reference,
        "citations": [c.model_dump() for c in result.citations],
        "related_articles": [r.model_dump() for r in result.related_articles],
        "retrieved_chunks": [_serialize_retrieved_chunk(c) for c in result.retrieved_chunks],
    }
    try:
        supabase_client.table(CHAT_QUERY_LOGS_TABLE).insert(row).execute()
    except Exception:
        # Logging is for later evaluation, not part of the user-facing contract - a logging
        # failure must never turn a successful answer into a 500 for the student.
        logger.exception("Failed to log chat query to Postgres (user_id=%s)", user_id)
