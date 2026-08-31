from __future__ import annotations

from pydantic import BaseModel, Field


class NoteUpsertRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    # max_length: generous headroom for a real study note, tight enough to block spam-sized
    # payloads - same reasoning as EssaySubmitRequest.user_answer.
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
