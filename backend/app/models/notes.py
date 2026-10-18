from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class NoteUpsertRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    # max_length: generous headroom for a real study note, tight enough to block spam-sized
    # payloads.
    content: str = Field(min_length=1, max_length=20000)
    tag: str | None = Field(default=None, max_length=100)


class NoteOut(BaseModel):
    id: str
    title: str | None
    content: str
    tag: str | None
    created_at: str
    updated_at: str


class NoteListResponse(BaseModel):
    notes: list[NoteOut]


# Vở ghi Giai đoạn 2 - POST /api/notes/ask. Over the limit is a plain 422 (the validation handler
# in core/middleware.py returns a fixed message and never echoes the submitted text back). The page
# counts characters against the same number, so a student never reaches the 422 by typing.
PASSAGE_MAX_CHARS = 3000


class NotesAskRequest(BaseModel):
    # The selected passage. Sent to the model and then discarded - never stored, never logged.
    passage: str = Field(min_length=1, max_length=PASSAGE_MAX_CHARS)
    # Same ceiling as ChatQueryRequest.question.
    question: str = Field(min_length=1, max_length=2000)
    # Omitted (or never seen before) starts a new Vở ghi conversation; Vở ghi conversations live in
    # chat_query_logs with source='notes' and never appear in the Chat sidebar.
    conversation_id: uuid.UUID | None = None
