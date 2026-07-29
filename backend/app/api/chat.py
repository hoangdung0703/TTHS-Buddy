from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.chat import ChatQueryRequest, ChatQueryResponse
from app.services.chat_log_service import log_chat_query
from app.services.rag_service import answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/query", response_model=ChatQueryResponse)
async def query_chat(
    body: ChatQueryRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
    settings: Settings = Depends(get_settings),
) -> ChatQueryResponse:
    qdrant_client = request.app.state.qdrant_client
    supabase_client = request.app.state.supabase_client

    result = answer_question(body.question, settings, qdrant_client)
    log_chat_query(supabase_client, current_user.user_id, body.question, result)

    return ChatQueryResponse(
        answer=result.answer,
        citations=result.citations,
        related_articles=result.related_articles,
    )
