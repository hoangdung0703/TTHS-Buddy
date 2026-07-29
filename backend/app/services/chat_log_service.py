"""Persists every chat query + retrieved chunks + answer into Postgres (Supabase table
chat_query_logs, see migrations/0001_chat_query_logs.sql) for Phase 9 evaluation - citation
accuracy, groundedness, and correct-refusal rate all need the retrieved chunks, not just the
final answer text.
"""
from __future__ import annotations

from typing import Any

from supabase import Client

from app.core.logging import get_logger
from app.services.rag_service import RagAnswer, RetrievedChunk

logger = get_logger(__name__)

CHAT_QUERY_LOGS_TABLE = "chat_query_logs"


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


def log_chat_query(supabase_client: Client, user_id: str, question: str, result: RagAnswer) -> None:
    row = {
        "user_id": user_id,
        "question": question,
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
