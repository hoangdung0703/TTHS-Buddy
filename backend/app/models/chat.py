from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    # max_length: generous headroom for a detailed situational question, tight enough to block
    # spam-sized payloads that would otherwise cost a full embed + Gemini generate call each -
    # see requirements.md security audit mục 2.2/4.
    question: str = Field(max_length=2000)
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
# event, in order: answer_delta (one or more) -> citations -> suggested_followups -> done (the
# aggregate-structure and no-context-blocks cases emit citations, always empty, before their
# single answer_delta instead - see rag_service.stream_answer_question for the full order
# guarantee and why citations otherwise wait for the complete answer). intent=answer_evaluation
# additionally emits a "grading_result" event (ChatStreamGradingEvent) between answer_delta and
# suggested_followups - see that class below.
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


# Only emitted for intent=answer_evaluation (requirements.md "Sinh tình huống minh họa" Lượt 2),
# right after that turn's answer_delta (the qualitative "nhận xét" sentence). Deliberately has NO
# score/percentage field anywhere - matched/missing points only, mirroring EssaySubmitResponse's
# shape (see models/essay.py) since the frontend reuses that same matched/missing visual language.
class ChatStreamGradingEvent(BaseModel):
    matched_points: list[str]
    missing_points: list[str]
    missing_points_display: list[str] | None = None


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


# PATCH /api/chat/conversations/{conversation_id} (Feature nho - xoa/doi ten hoi thoai). An
# empty/whitespace-only title is treated as "clear the custom title" - see
# chat_log_service.rename_conversation - so min_length is not enforced here; the service strips
# and null-coalesces it instead.
class ConversationRenameRequest(BaseModel):
    title: str = Field(max_length=200)
