"""Vở ghi cá nhân - storage + CRUD (Supabase table user_notes, see migrations/0010_user_notes.sql)
plus retrieve_relevant_notes, the Chat-side retrieval used by rag_service.py (requirements.md
"Feature - Vở ghi cá nhân + Chat trả lời dựa trên nội dung ghi chú" - typed notes only, file upload
is not built yet).

Unlike chat_log_service's conversation helpers (which swallow DB exceptions and turn them into a
plain 404, because a failed delete/rename of a side-effect log must never break an
already-successful chat turn), every function here lets exceptions propagate. A note write IS
the primary content of its own request - masking a real DB error as "note not found" would hide
data loss from the user instead of surfacing it as the 500 it actually is.
"""
from __future__ import annotations

import math
import uuid
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.gemini_client import embed_documents

logger = get_logger(__name__)

NOTES_TABLE = "user_notes"

# Retrieval is a brute-force cosine scan over the asking user's own notes, done in Python - no
# vector column/index (would need a pgvector migration) and no Qdrant copy (a second store for
# private data, where one forgotten user_id filter leaks it). At the small per-user volume this
# feature starts with, fetching <= NOTES_MAX_SCAN rows and comparing in memory is cheap, and the
# ONLY data source is a Supabase query filtered by user_id - there is no shared index another
# user's note could ever be scored from. Revisit (pgvector + embedding column) if per-user note
# counts grow well past this cap.
NOTES_MAX_SCAN = 200
NOTES_TOP_K = 3
# Calibrated on real gemini-embedding-001 scores (RETRIEVAL_QUERY question vs RETRIEVAL_DOCUMENT
# note): on-topic question/note pairs measured 0.75-0.82, adjacent-topic (tạm giam question vs a
# tạm giữ note) 0.75, unrelated legal topics and non-legal notes (lịch học, nấu ăn) all <= 0.66.
NOTES_SCORE_THRESHOLD = 0.70
# Embedding input cap - gemini-embedding-001 accepts ~2048 tokens; anything past this is not
# represented in the note's vector (a fact deep inside a very long note may not be matched).
NOTE_EMBED_MAX_CHARS = 6000
# How much of a matched note's content is fed into generation - bounds prompt growth from the
# 20000-char NoteUpsertRequest.content limit.
NOTE_CONTEXT_MAX_CHARS = 3000

# note_id -> (updated_at, vector). Keyed by note_id (a global UUID) and only ever LOOKED UP for ids
# that came back from this user's own user_id-filtered query, so the cache cannot surface another
# user's note - it only saves re-embedding an unchanged note on every chat turn. updated_at in the
# value invalidates an edited note. Per-process and bounded; a restart just re-embeds on demand.
_NOTE_EMBEDDING_CACHE_MAX = 5000
_note_embedding_cache: OrderedDict[str, tuple[str, array]] = OrderedDict()


@dataclass
class RetrievedNote:
    note_id: str
    title: str | None
    tag: str | None
    content: str
    score: float


def list_notes(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    response = (
        supabase_client.table(NOTES_TABLE)
        .select("id, title, content, tag, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data or []


def create_note(supabase_client: Client, user_id: str, title: str | None, content: str,
                 tag: str | None) -> dict[str, Any]:
    row = {"user_id": user_id, "title": title, "content": content, "tag": tag}
    response = supabase_client.table(NOTES_TABLE).insert(row).execute()
    return response.data[0]


def update_note(supabase_client: Client, user_id: str, note_id: uuid.UUID, title: str | None,
                 content: str, tag: str | None) -> dict[str, Any] | None:
    """Returns the updated row, or None if note_id doesn't exist or doesn't belong to this user -
    both cases indistinguishable on purpose (404, not 403), same ownership pattern as
    chat_log_service.rename_conversation: user_id and note_id are filtered in the SAME update
    query, so a nonexistent id and another user's real id both match 0 rows here."""
    row = {"title": title, "content": content, "tag": tag, "updated_at": datetime.now(timezone.utc).isoformat()}
    response = (
        supabase_client.table(NOTES_TABLE)
        .update(row)
        .eq("user_id", user_id)
        .eq("id", str(note_id))
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def delete_note(supabase_client: Client, user_id: str, note_id: uuid.UUID) -> bool:
    """Same ownership pattern as update_note above - returns whether a row was actually
    deleted, so the route can 404 on either a nonexistent id or another user's id."""
    response = (
        supabase_client.table(NOTES_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("id", str(note_id))
        .execute()
    )
    return len(response.data or []) > 0


def _note_embedding_text(note: dict[str, Any]) -> str:
    header = " - ".join(part for part in (note.get("title"), note.get("tag")) if part)
    text = f"{header}\n{note['content']}" if header else note["content"]
    return text[:NOTE_EMBED_MAX_CHARS]


def _cosine(a: array | list[float], b: array | list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _note_vectors(notes: list[dict[str, Any]], settings: Settings) -> list[array]:
    missing = [n for n in notes
               if (cached := _note_embedding_cache.get(n["id"])) is None or cached[0] != n["updated_at"]]
    if missing:
        vectors = embed_documents([_note_embedding_text(n) for n in missing], settings)
        for note, vector in zip(missing, vectors):
            _note_embedding_cache[note["id"]] = (note["updated_at"], array("f", vector))
    result: list[array] = []
    for note in notes:
        _note_embedding_cache.move_to_end(note["id"])
        result.append(_note_embedding_cache[note["id"]][1])
    while len(_note_embedding_cache) > _NOTE_EMBEDDING_CACHE_MAX:
        _note_embedding_cache.popitem(last=False)
    return result


def retrieve_relevant_notes(supabase_client: Client, user_id: str, question_vector: list[float],
                             settings: Settings) -> list[RetrievedNote]:
    """Top NOTES_TOP_K of THIS user's notes scoring >= NOTES_SCORE_THRESHOLD against
    question_vector (the raw-question RETRIEVAL_QUERY embedding rag_service.retrieve_context
    already computes - no extra embed call for the question). SECURITY: the user_id filter below
    is the only thing standing between one user's private notes and another user's prompt - it
    must stay in the same query as the fetch, never applied after the fact.

    Returns [] on ANY failure (Supabase/embedding error) - notes are an optional enrichment, so a
    failure here must degrade to the pre-notes behavior, never break the chat turn (same contract
    as rag_service._generate_hyde_passage)."""
    try:
        response = (
            supabase_client.table(NOTES_TABLE)
            .select("id, title, content, tag, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(NOTES_MAX_SCAN)
            .execute()
        )
        notes = response.data or []
        if not notes:
            return []
        vectors = _note_vectors(notes, settings)
    except Exception:
        logger.exception("Note retrieval failed - answering without the user's notes")
        return []

    scored = sorted(
        ((note, _cosine(question_vector, vector)) for note, vector in zip(notes, vectors)),
        key=lambda pair: pair[1], reverse=True
    )
    return [
        RetrievedNote(note_id=note["id"], title=note.get("title"), tag=note.get("tag"),
                      content=note["content"][:NOTE_CONTEXT_MAX_CHARS], score=score)
        for note, score in scored[:NOTES_TOP_K] if score >= NOTES_SCORE_THRESHOLD
    ]
