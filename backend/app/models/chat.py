from __future__ import annotations

import uuid

from pydantic import BaseModel


class ChatQueryRequest(BaseModel):
    question: str
    # Client-generated/held for the lifetime of one chat session; omitted (or a value never seen
    # before) starts a new conversation. See requirements.md Phase 4 Extension.
    conversation_id: uuid.UUID | None = None


class Citation(BaseModel):
    dieu_number: str
    dieu_title: str | None
    law_version: str | None


class RelatedArticle(BaseModel):
    dieu_number: str
    dieu_title: str | None


class SuggestedFollowup(BaseModel):
    dieu_number: str
    suggested_question: str


class ChatQueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    related_articles: list[RelatedArticle]
    suggested_followups: list[SuggestedFollowup]
    conversation_id: uuid.UUID
    # Surfaced (not just logged) so a bad answer can be diagnosed as "rewrite went wrong" vs
    # "retrieval went wrong" without needing direct Postgres access.
    rewritten_question: str


class ChatSuggestion(BaseModel):
    id: str
    text: str


class ChatSuggestionsResponse(BaseModel):
    suggestions: list[ChatSuggestion]
