from __future__ import annotations

from pydantic import BaseModel


class KeywordYesterday(BaseModel):
    dieu_number: str
    keyword: str
    count: int


class KeywordsYesterdayResponse(BaseModel):
    keywords: list[KeywordYesterday]


class WeakTopic(BaseModel):
    topic_category: str
    score_percentage: int
    # Real essay bank category (ly_thuyet/van_dung/ban_trac_nghiem/tinh_huong) the user actually
    # practiced this topic under, derived from essay_attempts.category - None when the topic only
    # has quiz attempts (no essay history yet to derive a bank from).
    essay_bank_category: str | None = None


class WeakTopicsResponse(BaseModel):
    weak_topics: list[WeakTopic]


class DashboardStats(BaseModel):
    total_quiz_attempts: int
    average_score: int
    dieu_studied_count: int
