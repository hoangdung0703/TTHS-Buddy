"""Vở ghi cá nhân - storage + CRUD only (Supabase table user_notes, see
migrations/0010_user_notes.sql). NOT wired into Chat/rag_service.py yet - that integration is a
separate, later step (see requirements.md "Feature - Vở ghi cá nhân + Chat trả lời dựa trên nội
dung ghi chú").

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
