import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.rate_limit import DEFAULT_RATE_LIMIT, LLM_ROUTE_RATE_LIMIT, limiter
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.essay import (
    EssayBanksResponse,
    EssayBankSummary,
    EssayQuestionOut,
    EssayQuestionRequest,
    EssaySubmitRequest,
    EssaySubmitResponse,
)
from app.services.essay_service import grade_essay_answer
from app.services.question_bank_service import (
    get_essay_banks_summary,
    get_essay_questions,
    save_essay_attempt,
    select_essay_question,
)

router = APIRouter(prefix="/api/essay", tags=["essay"])


@router.get("/banks", response_model=EssayBanksResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_essay_banks(
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> EssayBanksResponse:
    banks = get_essay_banks_summary(request.app.state.supabase_client, current_user.user_id)
    return EssayBanksResponse(banks=[EssayBankSummary(**b) for b in banks])


@router.post("/question", response_model=EssayQuestionOut)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_essay_question(
    body: EssayQuestionRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> EssayQuestionOut:
    question = select_essay_question(
        request.app.state.supabase_client, current_user.user_id,
        category=body.category, exclude_question_id=body.exclude_question_id,
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No essay questions available")

    return EssayQuestionOut(
        question_id=question["question_id"], question_text=question["question_text"],
        dieu_number=question["dieu_number"], topic_category=question["topic_category"],
        category=question["category"],
    )


@router.post("/submit", response_model=EssaySubmitResponse)
@limiter.limit(LLM_ROUTE_RATE_LIMIT)
async def submit_essay(
    body: EssaySubmitRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
    settings: Settings = Depends(get_settings),
) -> EssaySubmitResponse:
    question_bank_by_id = {q["question_id"]: q for q in get_essay_questions()}
    question = question_bank_by_id.get(body.question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Unknown essay question_id: {body.question_id}")

    # grade_essay_answer calls Gemini synchronously (httpx.post, not AsyncClient) - offloaded to
    # a thread so it doesn't block the single event loop for every other in-flight request, same
    # pattern as chat.py's rewrite_question/rag_service.py's embed_query.
    result = await asyncio.to_thread(grade_essay_answer, question, body.user_answer, settings)

    save_essay_attempt(request.app.state.supabase_client, current_user.user_id, question, body.user_answer, result)

    return EssaySubmitResponse(
        matched_points=result.matched_points, missing_points=result.missing_points,
        feedback=result.feedback, suggested_dieu=result.suggested_dieu,
    )
