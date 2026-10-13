import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.rate_limit import DEFAULT_RATE_LIMIT, LLM_ROUTE_RATE_LIMIT, limiter
from app.core.request_telemetry import finish_request, stage, start_request
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.chat import (
    ChatQueryRequest,
    ChatStreamErrorEvent,
    ChatStreamStatusEvent,
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
    get_last_assistant_turn,
    get_recent_turns,
    list_conversations,
    log_chat_query,
    rename_conversation,
)
from app.services.chat_suggestions_service import load_static_suggestions
from app.services.query_understanding_service import rewrite_question
from app.services.rag_service import STATUS_READING_QUESTION, RagAnswer, stream_answer_question

logger = get_logger(__name__)

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
    this handler only does auth, SSE transport, and logging the final result once the stream ends.

    Everything that touches the network - the two Supabase history reads and the query-understanding
    Gemini call - runs INSIDE the generator, not in this function body. Running them here would
    hold back the response headers until all of them finished (measured on production at 3.1-4.6s
    before the first byte). Auth and rate limiting deliberately stay outside, as the Depends and
    the decorator, because a rejected request must still get a real 401/429 status code, which is
    only possible before the response starts.

    Because the status line is already 200 by the time that work runs, a failure in it cannot
    become a 5xx. It is reported inside the stream instead, as an `error` event followed by a clean
    close - see the generator below.

    Event order: status (marker 0, immediately) -> ... -> answer_delta (one or more) -> citations
    -> suggested_followups -> done. The status events are additive and always precede the first
    answer_delta, so the relative order of the pre-existing events is unchanged and a client that
    does not know them ignores them.
    """
    qdrant_client = request.app.state.qdrant_client
    supabase_client = request.app.state.supabase_client

    # First thing after auth + rate limiting, before any I/O: emits the chat_request_start log
    # line so a request that later hangs, errors, or has its connection dropped still leaves
    # evidence. log_chat_query only runs once the stream completes, so it cannot do this - see
    # app/core/request_telemetry.py.
    start_request(current_user.user_id)

    conversation_id = body.conversation_id or uuid.uuid4()

    # Mutated in place by stream_answer_question as the stream progresses - holds the fields
    # (is_fallback, used_academic_reference, retrieved_chunks) that are intentionally never sent
    # over SSE, only logged (see requirements.md Phase 9).
    result = RagAnswer(
        answer="", citations=[], related_articles=[], suggested_followups=[],
        is_fallback=False, retrieved_chunks=[], used_academic_reference=False
    )

    async def event_stream() -> AsyncIterator[str]:
        # Bound before the try so the finally block can always read it, even if the failure
        # happened before query understanding ran. Falls back to the student's original wording,
        # which is what rewrite_question itself does on failure.
        rewritten_question = body.question

        # EVERYTHING that touches the network now lives inside this generator, including the two
        # Supabase reads and the query-understanding Gemini call that used to run in the handler
        # body. Those three ran BEFORE the StreamingResponse was returned, so no response header
        # could be sent until all three finished - measured on production as 3.76-5.81s before the
        # first byte, on top of the retrieval and generation the client then waits through. Moving
        # them here lets headers and the first status event go out immediately.
        #
        # Auth and rate limiting deliberately stay OUTSIDE (the Depends and the decorator): a
        # rejected request must still get a real 401/429 status code, which is only possible
        # before the response starts.
        #
        # The cost of the move is that a failure in those three can no longer become a 5xx - the
        # status line is already 200 by the time they run. So the whole body is wrapped and a
        # failure becomes an `error` SSE event followed by a clean close, never an exception
        # escaping into the stream (which would truncate it mid-event and look like a dropped
        # connection to the client).
        try:
            # Marker 0, sent before anything else happens. Everything after this point costs at
            # least one Supabase round trip and a Gemini call, so without it the client's first
            # byte waits ~3s even though the server started work immediately. Emitted for EVERY
            # chat turn, including the short-circuit intents: at this point the intent is not
            # known yet (query understanding is what determines it), and for those turns the
            # answer follows so quickly that the client replaces this almost at once.
            yield _sse_format("status", ChatStreamStatusEvent(message=STATUS_READING_QUESTION))

            # Two independent Supabase reads, so they run CONCURRENTLY rather than one after the
            # other - neither needs the other's result; both are needed before rewrite_question.
            # They have never actually been concurrent: before E2, get_recent_turns ran
            # synchronously ON THE EVENT LOOP (blocking every other in-flight request for the
            # duration) and only get_last_assistant_turn was offloaded; E2 moved both into
            # threads but still awaited them one at a time. Gathering them removes one full
            # Supabase round trip from the critical path ahead of the first status event.
            #
            # last_turn is fetched UNCONDITIONALLY (requirements.md "Sinh tình huống minh họa"
            # Lượt 2) - has_pending_scenario below must be known BEFORE rewrite_question runs,
            # since query_understanding_service needs it as part of its own classification (and
            # as the deterministic gate on intent=answer_evaluation).
            recent_turns, last_turn = await asyncio.gather(
                asyncio.to_thread(
                    get_recent_turns, supabase_client, current_user.user_id, conversation_id
                ),
                asyncio.to_thread(
                    get_last_assistant_turn, supabase_client, current_user.user_id, conversation_id
                ),
            )
            has_pending_scenario = bool(last_turn and last_turn.get("scenario_key_points"))
            # rewrite_question calls Gemini synchronously (httpx.post, not AsyncClient) - offloaded
            # to a thread so it doesn't block the event loop for every other in-flight request.
            with stage("query_understanding"):
                query_understanding = await asyncio.to_thread(
                    rewrite_question, body.question, recent_turns, settings, has_pending_scenario
                )
            rewritten_question = query_understanding.rewritten_question

            async for event_name, event_payload in stream_answer_question(
                rewritten_question, conversation_id, settings, qdrant_client, result, recent_turns,
                intent=query_understanding.intent, last_turn=last_turn,
                needs_anonymization=query_understanding.needs_anonymization,
                anonymized_names=query_understanding.anonymized_names,
                sub_questions=query_understanding.sub_questions
            ):
                yield _sse_format(event_name, event_payload)
        # A client that goes away mid-stream must not be recorded as a failure, or the logs cannot
        # tell "student closed the tab" from "something broke". Measured against a real aborted
        # request: the abort arrives as asyncio.CancelledError from anyio's cancel scope, NOT as
        # GeneratorExit; GeneratorExit is kept because Starlette can also close a generator that
        # way. Both are re-raised - swallowing a cancellation would break finalisation.
        except (asyncio.CancelledError, GeneratorExit):
            finish_request("cancelled")
            raise
        except BaseException as error:  # noqa: BLE001 - deliberately broad; see below
            # Deliberately broad and deliberately NOT re-raised. Past this point the client is
            # mid-stream, so the only way to report a failure is inside the stream; letting the
            # exception propagate would cut the connection and be indistinguishable from a network
            # drop. The telemetry line carries the real exception for diagnosis; the client gets a
            # fixed sentence that cannot leak an exception string (which may quote the question).
            logger.exception("Chat request failed after the response started (conversation_id=%s)",
                              conversation_id)
            finish_request("error", error)
            yield _sse_format("error", ChatStreamErrorEvent(
                message="Xin lỗi, đã có lỗi xảy ra khi xử lý câu hỏi. Bạn vui lòng thử lại."
            ))
        else:
            finish_request("ok")
        finally:
            # In `finally` so a turn that errored part-way through still persists whatever it did
            # produce, instead of the answer being shown and then silently lost. Guarded on there
            # actually being an answer: a request that failed or was cancelled before generation
            # has nothing worth storing, and writing an empty row would surface as a blank turn in
            # the student's own history and in the sidebar conversation list. Nothing is lost
            # diagnostically - request_telemetry already recorded the failure.
            if result.answer:
                log_chat_query(
                    supabase_client, current_user.user_id, conversation_id, body.question,
                    rewritten_question, result
                )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
