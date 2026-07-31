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
