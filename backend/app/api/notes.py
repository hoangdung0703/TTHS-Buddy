import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.chat import _sse_format
from app.core.config import Settings, get_settings
from app.core.data_access import DataUnavailable
from app.core.logging import get_logger
from app.core.rate_limit import DEFAULT_RATE_LIMIT, LLM_ROUTE_RATE_LIMIT, limiter
from app.core.request_telemetry import finish_request, mark_context_unavailable, set_history_saved, start_request
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.chat import ChatStreamErrorEvent, ChatStreamStatusEvent
from app.models.notes import NoteListResponse, NoteOut, NotesAskRequest, NoteUpsertRequest
from app.services.chat_log_service import SOURCE_NOTES, get_recent_turns, log_chat_query
from app.services.notes_ask_service import stream_answer_about_passage
from app.services.notes_service import create_note, delete_note, list_notes, update_note
from app.services.rag_service import STATUS_READING_QUESTION, RagAnswer

logger = get_logger(__name__)

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=NoteListResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_notes(
    request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> NoteListResponse:
    supabase_client = request.app.state.supabase_client
    notes = list_notes(supabase_client, current_user.user_id)
    return NoteListResponse(notes=[NoteOut(**n) for n in notes])


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_note_route(
    body: NoteUpsertRequest, request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> NoteOut:
    supabase_client = request.app.state.supabase_client
    note = create_note(supabase_client, current_user.user_id, body.title, body.content, body.tag)
    return NoteOut(**note)


@router.put("/{note_id}", response_model=NoteOut)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def update_note_route(
    note_id: uuid.UUID,
    body: NoteUpsertRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
) -> NoteOut:
    """SECURITY: ownership is enforced inside update_note (user_id + note_id filtered in the same
    Supabase update query) - a note_id that exists but belongs to a different user 404s exactly
    like one that doesn't exist at all, same 404-not-403 pattern as the conversation routes."""
    supabase_client = request.app.state.supabase_client
    note = update_note(supabase_client, current_user.user_id, note_id, body.title, body.content, body.tag)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return NoteOut(**note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def delete_note_route(
    note_id: uuid.UUID, request: Request, current_user: AuthUser = Depends(require_supabase_user)
) -> None:
    """SECURITY: same 404-not-403 ownership pattern as PUT above - see update_note_route."""
    supabase_client = request.app.state.supabase_client
    deleted = delete_note(supabase_client, current_user.user_id, note_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


@router.post("/ask")
@limiter.limit(LLM_ROUTE_RATE_LIMIT)
async def ask_about_passage(
    body: NotesAskRequest,
    request: Request,
    current_user: AuthUser = Depends(require_supabase_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Vở ghi Giai đoạn 2 - ask the AI about a passage the student selected in their notes. SSE, in
    the same event format as POST /api/chat/query: status -> answer_delta -> citations -> done, or
    an `error` event followed by a clean close. All the safety logic lives in
    notes_ask_service.stream_answer_about_passage; this route does auth, rate limiting, SSE
    transport, telemetry and storing the turn, mirroring api/chat.py's query_chat (see its
    docstring for why all I/O runs inside the generator and auth/limits stay outside it).

    The passage is NEVER stored or logged. The stored turn (source='notes') holds the question as
    typed, the answer and its citations; the telemetry lines hold the passage's LENGTH only."""
    qdrant_client = request.app.state.qdrant_client
    supabase_client = request.app.state.supabase_client

    start_request(current_user.user_id, source=SOURCE_NOTES, passage_chars=len(body.passage))

    conversation_id = body.conversation_id or uuid.uuid4()
    result = RagAnswer(
        answer="", citations=[], related_articles=[], suggested_followups=[],
        is_fallback=False, retrieved_chunks=[], used_academic_reference=False
    )

    async def event_stream() -> AsyncIterator[str]:
        outcome: str = "ok"
        failure: BaseException | None = None
        try:
            yield _sse_format("status", ChatStreamStatusEvent(message=STATUS_READING_QUESTION))

            # Earlier turns of THIS Vở ghi conversation only (source='notes'). A brand-new
            # conversation has none, so the read is skipped. A failed read degrades exactly as on
            # Chat: the answer goes ahead without history and the citations event says so.
            recent_turns: list[dict[str, str]] = []
            context_unavailable = False
            if body.conversation_id is not None:
                try:
                    recent_turns = await asyncio.to_thread(
                        get_recent_turns, supabase_client, current_user.user_id, conversation_id, SOURCE_NOTES
                    )
                except DataUnavailable:
                    context_unavailable = True
                    mark_context_unavailable()

            async for event_name, event_payload in stream_answer_about_passage(
                body.question, body.passage, conversation_id, settings, qdrant_client, result, recent_turns
            ):
                if event_name == "citations" and context_unavailable:
                    event_payload = event_payload.model_copy(update={"context_unavailable": True})
                yield _sse_format(event_name, event_payload)
        except (asyncio.CancelledError, GeneratorExit):
            outcome = "cancelled"
            raise
        except BaseException as error:  # noqa: BLE001 - same reasoning as api/chat.py's query_chat
            # The exception's message is not logged here beyond request_telemetry's truncated
            # copy, and nothing in this path puts the passage into an exception message.
            logger.exception("Notes ask request failed after the response started (conversation_id=%s)",
                             conversation_id)
            outcome, failure = "error", error
            yield _sse_format("error", ChatStreamErrorEvent(
                message="Xin lỗi, đã có lỗi xảy ra khi xử lý câu hỏi. Bạn vui lòng thử lại."
            ))
        finally:
            # The answer is buffered and sent in one piece, so an error before that point leaves
            # result.answer empty and nothing is stored - the student saw no answer either.
            if result.answer:
                set_history_saved(log_chat_query(
                    supabase_client, current_user.user_id, conversation_id, body.question,
                    body.question, result, source=SOURCE_NOTES
                ))
            finish_request(outcome, failure)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
