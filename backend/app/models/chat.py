from __future__ import annotations

import uuid
from datetime import datetime

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


class ChatSuggestion(BaseModel):
    id: str
    text: str


class ChatSuggestionsResponse(BaseModel):
    suggestions: list[ChatSuggestion]


# POST /api/chat/query is SSE (Phase 4 Extension) - one of these is the "data" payload of each
# event, in this fixed order: citations -> answer_delta (one or more) -> suggested_followups ->
# done. See rag_service.stream_answer_question for the event order guarantee.
class ChatStreamCitationsEvent(BaseModel):
    citations: list[Citation]
    related_articles: list[RelatedArticle]
    conversation_id: uuid.UUID
    # Surfaced (not just logged) so a bad answer can be diagnosed as "rewrite went wrong" vs
    # "retrieval went wrong" without needing direct Postgres access.
    rewritten_question: str


class ChatStreamAnswerDeltaEvent(BaseModel):
    delta: str


class ChatStreamSuggestedFollowupsEvent(BaseModel):
    suggested_followups: list[SuggestedFollowup]


class ChatStreamDoneEvent(BaseModel):
    pass


# Phase 4 Extension 2: read-back of chat_query_logs, grouped by conversation_id, for the
# Sidebar history list and conversation reload. See chat_log_service.list_conversations /
# get_conversation_detail.
class ConversationSummary(BaseModel):
    conversation_id: uuid.UUID
    title: str
    updated_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class ConversationTurn(BaseModel):
    question: str
    answer: str
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    conversation_id: uuid.UUID
    turns: list[ConversationTurn]
