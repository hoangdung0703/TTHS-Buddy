import uuid

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.chat import ChatQueryRequest, ChatQueryResponse, ChatSuggestion, ChatSuggestionsResponse
from app.services.chat_log_service import get_recent_turns, log_chat_query
from app.services.chat_suggestions_service import load_static_suggestions
from app.services.query_understanding_service import rewrite_question
from app.services.rag_service import answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/suggestions", response_model=ChatSuggestionsResponse)
async def get_chat_suggestions(current_user: AuthUser = Depends(require_supabase_user)) -> ChatSuggestionsResponse:
    return ChatSuggestionsResponse(suggestions=[ChatSuggestion(**s) for s in load_static_suggestions()])


@router.post("/query", response_model=ChatQueryResponse)
async def query_chat(
    body: ChatQueryRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
    settings: Settings = Depends(get_settings),
) -> ChatQueryResponse:
    qdrant_client = request.app.state.qdrant_client
    supabase_client = request.app.state.supabase_client

    conversation_id = body.conversation_id or uuid.uuid4()
    recent_turns = get_recent_turns(supabase_client, current_user.user_id, conversation_id)
    rewritten_question = rewrite_question(body.question, recent_turns, settings)

    result = answer_question(rewritten_question, settings, qdrant_client, recent_turns=recent_turns)
    log_chat_query(supabase_client, current_user.user_id, conversation_id, body.question, rewritten_question, result)

    return ChatQueryResponse(
        answer=result.answer,
        citations=result.citations,
        related_articles=result.related_articles,
        suggested_followups=result.suggested_followups,
        conversation_id=conversation_id,
        rewritten_question=rewritten_question,
    )
