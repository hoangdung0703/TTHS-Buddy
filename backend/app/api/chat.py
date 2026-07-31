import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.chat import ChatQueryRequest, ChatSuggestion, ChatSuggestionsResponse
from app.services.chat_log_service import get_recent_turns, log_chat_query
from app.services.chat_suggestions_service import load_static_suggestions
from app.services.query_understanding_service import rewrite_question
from app.services.rag_service import RagAnswer, stream_answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/suggestions", response_model=ChatSuggestionsResponse)
async def get_chat_suggestions(current_user: AuthUser = Depends(require_supabase_user)) -> ChatSuggestionsResponse:
    return ChatSuggestionsResponse(suggestions=[ChatSuggestion(**s) for s in load_static_suggestions()])


def _sse_format(event: str, payload) -> str:  # noqa: ANN001 - payload is one of the ChatStream*Event models
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


@router.post("/query")
async def query_chat(
    body: ChatQueryRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """SSE endpoint (Phase 4 Extension - see requirements.md). Event order: citations ->
    answer_delta (one or more) -> suggested_followups -> done. The route stays thin per
    requirements.md mục 4 ("khong viet logic don het vao route") - all retrieval/generation/
    fallback logic lives in rag_service.stream_answer_question; this handler only does auth,
    query understanding, SSE transport, and logging the final result once the stream ends.
    """
    qdrant_client = request.app.state.qdrant_client
    supabase_client = request.app.state.supabase_client

    conversation_id = body.conversation_id or uuid.uuid4()
    recent_turns = get_recent_turns(supabase_client, current_user.user_id, conversation_id)
    rewritten_question = rewrite_question(body.question, recent_turns, settings)

    # Mutated in place by stream_answer_question as the stream progresses - holds the fields
    # (is_fallback, used_academic_reference, retrieved_chunks) that are intentionally never sent
    # over SSE, only logged (see requirements.md Phase 9).
    result = RagAnswer(
        answer="", citations=[], related_articles=[], suggested_followups=[],
        is_fallback=False, retrieved_chunks=[], used_academic_reference=False
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event_name, event_payload in stream_answer_question(
            rewritten_question, conversation_id, settings, qdrant_client, result, recent_turns
        ):
            yield _sse_format(event_name, event_payload)

        log_chat_query(supabase_client, current_user.user_id, conversation_id, body.question, rewritten_question, result)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
