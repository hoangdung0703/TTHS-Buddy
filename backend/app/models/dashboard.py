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


class WeakTopicsResponse(BaseModel):
    weak_topics: list[WeakTopic]


class DashboardStats(BaseModel):
    total_quiz_attempts: int
    average_score: int
    dieu_studied_count: int
