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


class EssayBankQuestionListItem(BaseModel):
    question_id: str
    order: int
    question_text: str
    # KHÔNG có dieu_number ở đây dù đã có sẵn trong dữ liệu câu hỏi - dieu_number là "Căn cứ pháp
    # lý" của đáp án (xem ingestion/question_bank.json), gửi kèm trong response của TOÀN BỘ danh
    # sách trước khi user chọn/nộp bài sẽ lộ đáp án qua network payload dù UI không render, kể cả
    # cho các câu chưa mở. Chỉ trả lại sau khi chấm (EssaySubmitResponse.suggested_dieu).
    # "done": lần gần nhất không có missing_points. "needs_review": lần gần nhất có missing_points.
    # "not_done": chưa từng làm.
    status: str


class EssayBankQuestionListResponse(BaseModel):
    category: str
    questions: list[EssayBankQuestionListItem]
