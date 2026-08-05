from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.quiz import (
    QuizAnswerIn,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestionOut,
    QuizResultOut,
    QuizSetsResponse,
    QuizSetSummary,
    QuizStatsResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
)
from app.services.question_bank_service import (
    QUIZ_SET_COUNT,
    get_quiz_set_summaries,
    get_quiz_stats,
    load_question_bank,
    save_quiz_attempt,
    select_quiz_questions,
)
from app.services.quiz_service import grade_mcq_answer

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

VALID_QUIZ_SETS = set(range(1, QUIZ_SET_COUNT + 1))


def _validate_quiz_set(quiz_set: int) -> None:
    if quiz_set not in VALID_QUIZ_SETS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"quiz_set must be between 1 and {QUIZ_SET_COUNT}")


@router.get("/sets", response_model=QuizSetsResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_quiz_sets(
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> QuizSetsResponse:
    summaries = get_quiz_set_summaries(request.app.state.supabase_client, current_user.user_id)
    return QuizSetsResponse(quiz_sets=[QuizSetSummary(**s) for s in summaries])


@router.get("/stats", response_model=QuizStatsResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_quiz_statistics(
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> QuizStatsResponse:
    return QuizStatsResponse(**get_quiz_stats(request.app.state.supabase_client, current_user.user_id))


@router.post("/generate", response_model=QuizGenerateResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def generate_quiz(
    body: QuizGenerateRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> QuizGenerateResponse:
    _validate_quiz_set(body.quiz_set)

    questions = select_quiz_questions(body.quiz_set)
    if not questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="No questions found for the given quiz_set")

    return QuizGenerateResponse(questions=[
        QuizQuestionOut(
            question_id=q["question_id"], question_text=q["question_text"],
            mcq_options=q["mcq_options"], dieu_number=q["dieu_number"], topic_category=q["topic_category"],
        )
        for q in questions
    ])


def _grade_one(question_bank_by_id: dict, quiz_set: int, answer: QuizAnswerIn) -> tuple[QuizResultOut, dict]:
    question = question_bank_by_id.get(answer.question_id)
    if question is None or question["quiz_set"] != quiz_set:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Unknown question_id for this quiz_set: {answer.question_id}")

    is_correct = grade_mcq_answer(question, answer.selected_option)
    result = QuizResultOut(
        question_id=question["question_id"], is_correct=is_correct,
        mcq_correct=question["mcq_correct"], dieu_number=question["dieu_number"],
        explanation=question["explanation"],
    )
    stored_answer = {
        "question_id": question["question_id"], "selected_option": answer.selected_option,
        "is_correct": is_correct, "topic_category": question["topic_category"],
    }
    return result, stored_answer


@router.post("/submit", response_model=QuizSubmitResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def submit_quiz(
    body: QuizSubmitRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> QuizSubmitResponse:
    _validate_quiz_set(body.quiz_set)

    question_bank_by_id = {q["question_id"]: q for q in load_question_bank()}

    results: list[QuizResultOut] = []
    stored_answers: list[dict] = []
    for answer in body.answers:
        result, stored_answer = _grade_one(question_bank_by_id, body.quiz_set, answer)
        results.append(result)
        stored_answers.append(stored_answer)

    score = sum(1 for r in results if r.is_correct)

    save_quiz_attempt(
        request.app.state.supabase_client, current_user.user_id, body.quiz_set,
        question_ids=[a.question_id for a in body.answers], answers=stored_answers,
        score=score, total=len(results),
    )

    return QuizSubmitResponse(score=score, total=len(results), results=results)
