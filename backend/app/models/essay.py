from __future__ import annotations

from pydantic import BaseModel


class EssayQuestionOut(BaseModel):
    question_id: str
    question_text: str
    dieu_number: str | None
    topic_category: str | None


class EssaySubmitRequest(BaseModel):
    question_id: str
    user_answer: str


class EssaySubmitResponse(BaseModel):
    matched_points: list[str]
    missing_points: list[str]
    feedback: str
    suggested_dieu: list[str]
