"""Vở ghi cá nhân - storage + CRUD (Supabase table user_notes, see migrations/0010_user_notes.sql).

Chat no longer reads notes. Until 2026-10-12 this module also held retrieve_relevant_notes, a
brute-force cosine scan over the asking user's own notes that rag_service.py called on every chat
turn, so that Chat could answer "theo ghi chú của bạn". That direction was dropped in favour of
asking about a passage the student selects inside the Vở ghi page itself, so the retrieval half of
this module (note embedding, the in-process vector cache, the 0.70 score threshold) is gone and
only CRUD remains. The replacement flow sends the selected passage up from the client and never
reads this table during a question, so nothing here should grow a retrieval path again.

Unlike chat_log_service's conversation helpers (which swallow DB exceptions and turn them into a
plain 404, because a failed delete/rename of a side-effect log must never break an
already-successful chat turn), every function here lets exceptions propagate. A note write IS
the primary content of its own request - masking a real DB error as "note not found" would hide
data loss from the user instead of surfacing it as the 500 it actually is.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from app.core.logging import get_logger

logger = get_logger(__name__)

NOTES_TABLE = "user_notes"


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
