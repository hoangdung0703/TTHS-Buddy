import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from app.core.security import require_supabase_user
from app.models.auth import AuthUser
from app.models.notes import NoteListResponse, NoteOut, NoteUpsertRequest
from app.services.notes_service import create_note, delete_note, list_notes, update_note

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
