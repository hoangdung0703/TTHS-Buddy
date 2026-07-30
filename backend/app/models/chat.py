from __future__ import annotations

from pydantic import BaseModel


class ChatQueryRequest(BaseModel):
    question: str


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


class ChatSuggestion(BaseModel):
    id: str
    text: str


class ChatSuggestionsResponse(BaseModel):
    suggestions: list[ChatSuggestion]
