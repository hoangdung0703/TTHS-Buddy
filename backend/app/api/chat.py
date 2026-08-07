import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.rate_limit import DEFAULT_RATE_LIMIT, LLM_ROUTE_RATE_LIMIT, limiter
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.chat import (
    ChatQueryRequest,
    ChatSuggestion,
    ChatSuggestionsResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationRenameRequest,
    ConversationSummary,
    ConversationTurn,
)
from app.services.chat_log_service import (
    delete_conversation,
    get_conversation_detail,
    get_recent_turns,
    list_conversations,
    log_chat_query,
    rename_conversation,
)
from app.services.chat_suggestions_service import load_static_suggestions
from app.services.query_understanding_service import rewrite_question
from app.services.rag_service import RagAnswer, stream_answer_question

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/suggestions", response_model=ChatSuggestionsResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_chat_suggestions(
    request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> ChatSuggestionsResponse:
    return ChatSuggestionsResponse(suggestions=[ChatSuggestion(**s) for s in load_static_suggestions()])


@router.get("/conversations", response_model=ConversationListResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_conversations(
    request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> ConversationListResponse:
    """Phase 4 Extension 2 - Sidebar history list. See chat_log_service.list_conversations for
    the grouping/ownership logic; this route only wires auth + the service call."""
    supabase_client = request.app.state.supabase_client
    conversations = list_conversations(supabase_client, current_user.user_id)
    return ConversationListResponse(conversations=[ConversationSummary(**c) for c in conversations])


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_conversation(
    conversation_id: uuid.UUID, request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> ConversationDetailResponse:
    """Phase 4 Extension 2 - reload one conversation's full turn history. SECURITY: ownership is
    enforced inside get_conversation_detail (filters by current_user.user_id in the same Supabase
    query as conversation_id) - a conversation_id that exists but belongs to a different user
    returns None here exactly like one that doesn't exist at all, so this 404s instead of ever
    confirming "that id belongs to someone else" to the caller."""
    supabase_client = request.app.state.supabase_client
    turns = get_conversation_detail(supabase_client, current_user.user_id, conversation_id)
    if turns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationDetailResponse(conversation_id=conversation_id, turns=[ConversationTurn(**t) for t in turns])


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def delete_conversation_route(
    conversation_id: uuid.UUID, request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> None:
    """Feature nho - xoa hoi thoai. SECURITY: same 404-not-403 ownership pattern as GET detail
    above - see delete_conversation's docstring."""
    supabase_client = request.app.state.supabase_client
    deleted = delete_conversation(supabase_client, current_user.user_id, conversation_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.patch("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def rename_conversation_route(
    conversation_id: uuid.UUID,
    body: ConversationRenameRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> None:
    """Feature nho - doi ten hoi thoai. An empty/whitespace-only title clears the custom title
    (falls back to the auto-generated one from the first question - see list_conversations).
    SECURITY: same 404-not-403 ownership pattern as GET detail/DELETE above - see
    rename_conversation's docstring."""
    supabase_client = request.app.state.supabase_client
    resolved_title = body.title.strip() or None
    renamed = rename_conversation(supabase_client, current_user.user_id, conversation_id, resolved_title)
    if not renamed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


def _sse_format(event: str, payload) -> str:  # noqa: ANN001 - payload is one of the ChatStream*Event models
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


@router.post("/query")
@limiter.limit(LLM_ROUTE_RATE_LIMIT)
async def query_chat(
    body: ChatQueryRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """SSE endpoint (Phase 4 Extension - see requirements.md). Event order: answer_delta (one or
    more) -> citations -> suggested_followups -> done - citations moved after answer_delta so
    they can be computed from the complete generated answer (which legal_text Dieu the model
    actually cited), not guessed from retrieval alone; see rag_service.stream_answer_question's
    docstring. The route stays thin per requirements.md mục 4 ("khong viet logic don het vao
    route") - all retrieval/generation/fallback logic lives in rag_service.stream_answer_question;
    this handler only does auth, query understanding, SSE transport, and logging the final result
    once the stream ends.
    """
    qdrant_client = request.app.state.qdrant_client
    supabase_client = request.app.state.supabase_client

    conversation_id = body.conversation_id or uuid.uuid4()
    recent_turns = get_recent_turns(supabase_client, current_user.user_id, conversation_id)
    # rewrite_question calls Gemini synchronously (httpx.post, not AsyncClient) - offloaded to a
    # thread so it doesn't block the single event loop for every other in-flight request, same
    # pattern already used for the sync QdrantClient calls in rag_service.retrieve_context (see
    # requirements.md security/capacity audit - this was the main cause of near-total
    # serialization measured under concurrent chat load before this fix).
    query_understanding = await asyncio.to_thread(rewrite_question, body.question, recent_turns, settings)
    rewritten_question = query_understanding.rewritten_question

    # Mutated in place by stream_answer_question as the stream progresses - holds the fields
    # (is_fallback, used_academic_reference, retrieved_chunks) that are intentionally never sent
    # over SSE, only logged (see requirements.md Phase 9).
    result = RagAnswer(
        answer="", citations=[], related_articles=[], suggested_followups=[],
        is_fallback=False, retrieved_chunks=[], used_academic_reference=False
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event_name, event_payload in stream_answer_question(
            rewritten_question, conversation_id, settings, qdrant_client, result, recent_turns,
            is_out_of_scope=query_understanding.is_out_of_scope
        ):
            yield _sse_format(event_name, event_payload)

        log_chat_query(supabase_client, current_user.user_id, conversation_id, body.question, rewritten_question, result)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
