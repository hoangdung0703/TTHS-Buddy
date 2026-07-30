from __future__ import annotations

from pydantic import BaseModel


class QuizSetSummary(BaseModel):
    quiz_set: int
    total_questions: int
    main_topics: list[str]


class QuizSetsResponse(BaseModel):
    quiz_sets: list[QuizSetSummary]


class QuizGenerateRequest(BaseModel):
    quiz_set: int
    dieu_number: str | None = None
    topic_category: str | None = None


class QuizQuestionOut(BaseModel):
    question_id: str
    question_text: str
    mcq_options: list[str]
    dieu_number: str | None
    topic_category: str | None


class QuizGenerateResponse(BaseModel):
    questions: list[QuizQuestionOut]


class QuizAnswerIn(BaseModel):
    question_id: str
    selected_option: str


class QuizSubmitRequest(BaseModel):
    quiz_set: int
    answers: list[QuizAnswerIn]


class QuizResultOut(BaseModel):
    question_id: str
    is_correct: bool
    mcq_correct: str
    dieu_number: str | None
    explanation: str | None


class QuizSubmitResponse(BaseModel):
    score: int
    total: int
    results: list[QuizResultOut]
