from __future__ import annotations

from pydantic import BaseModel, Field


class EssayQuestionOut(BaseModel):
    question_id: str
    question_text: str
    dieu_number: str | None
    topic_category: str | None
    category: str


class EssayQuestionRequest(BaseModel):
    # category=None: draws from the whole 111-question pool (the "Toi hoi ban tra loi"
    # minigame, requirements.md "Phase 5a/5b v2"). category set: scoped to that bank.
    category: str | None = None
    # Set by the "Cau khac" (skip) button to guarantee a different question than the one just
    # shown, without recording an attempt (skipping is explicitly not an attempt).
    exclude_question_id: str | None = None


class EssaySubmitRequest(BaseModel):
    question_id: str
    # max_length: generous headroom for a thorough essay answer, tight enough to block
    # spam-sized payloads that would otherwise cost a full LLM grading call each - see
    # requirements.md security audit mục 2.2/4.
    user_answer: str = Field(max_length=5000)


class EssaySubmitResponse(BaseModel):
    matched_points: list[str]
    missing_points: list[str]
    feedback: str
    suggested_dieu: list[str]
    # Display-only, natural-language merge of missing_points (requirements.md "Gộp câu tự nhiên
    # cho danh sách Ý còn thiếu/sai"). Does not affect scoring - null when the LLM didn't return
    # a usable value (frontend falls back to rendering missing_points as separate bullets).
    missing_points_display: list[str] | None = None


class EssayBankSummary(BaseModel):
    category: str
    total_questions: int
    questions_practiced: int


class EssayBanksResponse(BaseModel):
    banks: list[EssayBankSummary]
