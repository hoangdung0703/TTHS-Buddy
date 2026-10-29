"""/api/trials - "Phiên tòa giả định" (design doc Mục 2.2, chặng 2 B1).

Same transport rules as api/notes.py and api/chat.py: auth and rate limits outside the stream,
`status`/`error` events, `_sse_format`, request telemetry with lengths and counts only. Two
differences, both on purpose:
- The cheap checks that decide the HTTP status (ownership 404, limits 429, state-machine 409) run
  BEFORE the stream starts, so the client gets a real status code instead of a 200 that carries
  an error event. They are a few small Supabase reads.
- Nothing is written until a whole AI turn has passed its guards. Each turn is persisted inside
  asyncio.shield, so a client that disconnects mid-write cannot leave half a turn behind; a turn
  still being generated when the client leaves is simply dropped, and "continue" redoes it.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.chat import _sse_format
from app.core import request_telemetry as telemetry
from app.core.config import Settings, get_settings
from app.core.data_access import DataUnavailable
from app.core.logging import get_logger
from app.core.rate_limit import DEFAULT_RATE_LIMIT, LLM_ROUTE_RATE_LIMIT, limiter
from app.core.security import require_supabase_user, verified_user_or_none
from app.models.auth import AuthUser
from app.models.chat import ChatStreamErrorEvent, ChatStreamStatusEvent
from app.models.trial import CaseOptions
from app.models.trial_api import (
    TrialClerkDraftOut,
    TrialConfigOut,
    TrialCreateRequest,
    TrialCrimeOut,
    TrialDetailResponse,
    TrialLimitsOut,
    TrialDoneEvent,
    TrialListResponse,
    TrialNotesOut,
    TrialNotesRequest,
    TrialRecordDraftRequest,
    TrialRecordResponse,
    TrialRemainingOut,
    TrialSessionEvent,
    TrialTurnRequest,
)
from app.services.trial_case_service import CaseGenerationFailed, create_case, load_pack_for_crime
from app.services.trial_clerk import (
    CLERK_SECTIONS,
    NOTES_MAX_CHARS,
    SECTION_HARD_MAX_CHARS,
    SECTION_MAX_CHARS,
    SECTION_MIN_CHARS,
    clean_notes,
    draft_of,
    notes_of,
    review_draft,
    with_draft,
    with_finalized,
    with_notes,
)
from app.services.trial_config import (
    ABANDON_AFTER_DAYS,
    CRIMES,
    DEFAULT_GLOBAL_DAILY_CASE_LIMIT,
    MAX_ACTIVE_SESSIONS,
    MAX_CASES_PER_DAY,
    get_crime,
)
from app.services.trial_metrics import TrialCallRecorder
from app.services.trial_record import build_record, render_record_text
from app.services.trial_record_summary import summarise_record
from app.services.trial_repository import SupabaseTrialRepository, TrialRepository, lock_deadline, utc_now
from app.services.trial_rule9 import extract_citations
from app.services.trial_session_service import (
    build_context,
    shape_of,
    state_fields,
    state_out,
    steps_view,
    student_case_view,
    summary_out,
    utterance_out,
    utterance_rows,
    verdict_json,
)
from app.services.trial_state_machine import (
    CLERK_ROLE,
    ENABLED_USER_ROLES,
    OBSERVER_ROLE,
    STEP_BY_NUMBER,
    TrialConflict,
    UserAction,
    awaiting,
    new_session,
)
from app.services.trial_turn_service import TrialContext, TrialGuardFailure, Utterance, apply_student_action, run_ai_turn

logger = get_logger(__name__)

def allowed_emails(settings: Settings) -> frozenset[str]:
    """TRIAL_ALLOWED_EMAILS as a set: comma-separated, blanks dropped, compared case-insensitively."""
    raw = getattr(settings, "trial_allowed_emails", "") or ""
    return frozenset(e.strip().casefold() for e in raw.split(",") if e.strip())


def _hidden() -> StarletteHTTPException:
    # Starlette's own HTTPException, not FastAPI's: the app's handler (core/middleware.py) only
    # catches the FastAPI subclass, so this one renders exactly like an unknown path -
    # {"detail": "Not Found"} - instead of the app's {"error": ...} envelope.
    return StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND)


def require_trial_enabled(request: Request, authorization: str | None = Header(default=None, alias="Authorization"),
                          settings: Settings = Depends(get_settings)) -> None:
    """Feature flag TRIAL_ENABLED plus the staged-rollout allowlist TRIAL_ALLOWED_EMAILS. Router-level,
    so it runs before the routes' own authentication: with the flag off, and while the allowlist is
    set for anyone not on it (anonymous, bad token, unlisted email), the answer is the same 404 as
    an unknown path, so the response never reveals that the feature exists. The email comes only
    from the verified JWT (verified once per request; the route reuses it) and is never logged."""
    if not getattr(settings, "trial_enabled", False):
        raise _hidden()
    allowed = allowed_emails(settings)
    if not allowed:
        return
    user = verified_user_or_none(request, authorization, settings)
    if user is None or (user.email or "").strip().casefold() not in allowed:
        raise _hidden()


router = APIRouter(prefix="/api/trials", tags=["trials"], dependencies=[Depends(require_trial_enabled)])

VIETNAM_TZ = timezone(timedelta(hours=7))
# Must match TrialCreateRequest.witness_count's bound.
MAX_WITNESSES = 2
# An AI turn takes seconds (spike: <= 15s for one call, two calls with a regeneration); a lock
# older than this belongs to a worker that died and is ignored.
GENERATION_LOCK_SECONDS = 180
# Circuit breaker: after this many consecutive guard pauses on one slot, "continue" is refused, so
# a slot the model keeps failing can never burn calls without bound (B4 2026-10-19: one slot was
# retried 62 times by a scripted client before it passed).
MAX_CONSECUTIVE_GUARD_PAUSES = 3
GUARD_PAUSE_TEXT = ("Hội đồng xét xử tạm nghỉ ít phút để kiểm tra lại nội dung theo đúng hồ sơ và quy định pháp "
                    "luật. Đề nghị bấm \"Tiếp tục\" để phiên tòa tiếp tục.")
CREATE_FAILED_TEXT = "Chưa dựng được hồ sơ vụ án hợp lệ. Bạn vui lòng thử lại."
RECORD_STATUS_TEXT = "Đang lập biên bản..."
TURN_FAILED_TEXT = "Xin lỗi, đã có lỗi xảy ra trong phiên tòa. Bạn vui lòng bấm \"Tiếp tục\" để thử lại."
USAGE_LOG_UNAVAILABLE_TEXT = ("Tạm thời chưa tạo được vụ án mới vì hệ thống không kiểm tra được hạn mức. Bạn vui "
                              "lòng thử lại sau; các phiên tòa đang dở vẫn tiếp tục được.")
GLOBAL_LIMIT_TEXT = ("Hôm nay hệ thống đã tạo đủ số vụ án mô phỏng cho phép. Bạn vui lòng quay lại vào ngày mai; "
                     "các phiên tòa đang dở vẫn tiếp tục được bình thường.")


def get_trial_repository(request: Request) -> TrialRepository:
    """Overridable in tests (app.dependency_overrides); production uses Supabase."""
    return SupabaseTrialRepository(request.app.state.supabase_client)


def _error(status_code: int, code: str, message: str, extra: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code,
                        content={"error": {"code": code, "message": message}, **(extra or {})})


def _conflict(code: str, session_id: str, ctx: TrialContext) -> JSONResponse:
    return _error(status.HTTP_409_CONFLICT, f"trial_{code}", "Trạng thái phiên tòa đã thay đổi hoặc thao tác không "
                  "hợp lệ ở bước hiện tại.", {"state": _state_of(session_id, ctx).model_dump(mode="json")})


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trial not found")


def _today_start_utc() -> datetime:
    local = datetime.now(VIETNAM_TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def global_daily_case_limit(settings: Settings) -> int:
    return getattr(settings, "trial_global_daily_case_limit", DEFAULT_GLOBAL_DAILY_CASE_LIMIT)


def _stale_cutoff() -> datetime:
    return utc_now() - timedelta(days=ABANDON_AFTER_DAYS)


def _state_of(session_id: str, ctx: TrialContext):
    return state_out(session_id, ctx.state, consecutive_guard_pauses(ctx) >= MAX_CONSECUTIVE_GUARD_PAUSES,
                     case=ctx.case)


def consecutive_guard_pauses(ctx: TrialContext) -> int:
    count = 0
    for u in reversed(ctx.transcript):
        if u.kind == "notice" and "guard_pause" in u.guard_flags:
            count += 1
        elif not (u.kind == "notice"):
            break
    return count


def _events_for(utterances: list[Utterance], ctx: TrialContext) -> list[str]:
    return [_sse_format("utterance", utterance_out(u, ctx.case)) for u in utterances]


async def _persist(repo: TrialRepository, user_id: str, session_id: str, ctx: TrialContext,
                   utterances: list[Utterance], expected_version: int) -> bool:
    """Utterances first, then the state guarded by the version it moved from. Shielded: once a turn
    passed its guards it is stored completely even if the client disconnects meanwhile."""
    def write() -> bool:
        repo.insert_utterances(utterance_rows(utterances, session_id, user_id))
        return repo.update_state(user_id, session_id, expected_version, state_fields(ctx))
    return await asyncio.shield(asyncio.to_thread(write))


def _log_calls(recorder: TrialCallRecorder) -> None:
    """Per-call cost and guard outcome: labels and counts only (violation labels name a guard and,
    for citations, a "Điều N <code>" label - never any text)."""
    if recorder.records:
        logger.info("TRIAL_CALLS %s", json.dumps([
            {"type": r.call_type, "slot": r.slot, "attempt": r.attempt, "latency": r.latency_seconds,
             "prompt": r.prompt_tokens, "output": r.output_tokens, "thinking": r.thinking_tokens,
             "cached": r.cached_tokens, "accepted": r.accepted, "violations": r.guard_violations[:8]}
            for r in recorder.records], ensure_ascii=False))


def _log_turn(ctx: TrialContext, produced: list[Utterance], action: str, student_chars: int) -> None:
    ai = [u for u in produced if not u.is_user]
    logger.info("TRIAL_TURN %s", json.dumps({
        "step": ctx.state.current_step, "action": action, "student_chars": student_chars,
        "ai_utterances": len(ai), "ai_chars": sum(len(u.text) for u in ai),
        "ai_citations": sum(len(extract_citations(u.text)) for u in ai),
        "calls": len(ctx.recorder.records),
        "prompt_tokens": sum(r.prompt_tokens for r in ctx.recorder.records),
        "guard_rejections": sum(not r.accepted for r in ctx.recorder.records),
    }))


async def _summarise_and_store(repo: TrialRepository, user_id: str, session_id: str, ctx: TrialContext) -> None:
    """Shielded so a client leaving during the call still gets the summary stored. Never raises."""
    ctx.record_summary = await summarise_record(ctx)
    try:
        stored = await asyncio.to_thread(repo.update_state, user_id, session_id, ctx.state.version,
                                         {"verdict_json": verdict_json(ctx)})
    except Exception:  # noqa: BLE001 - the record falls back to verbatim
        stored = False
    if not stored:
        logger.warning("Trial record summary not stored; the record stays verbatim")


async def run_ai_stream(repo: TrialRepository, user_id: str, session_id: str, ctx: TrialContext,
                        first_events: list[str]) -> AsyncIterator[str]:
    """Runs every AI turn owed, persisting and emitting each one, until it is the student's turn.
    Releases the generation lock on every exit path - synchronously in `finally`, because a
    cancelled stream cannot await anything there (same reason notes.py stores synchronously)."""
    outcome, failure = "ok", None
    try:
        for event in first_events:
            yield event
        while ctx.state.status == "active" and awaiting(ctx.state) == "ai":
            yield _sse_format("status", ChatStreamStatusEvent(
                message=f"{STEP_BY_NUMBER[ctx.state.current_step].title}..."))
            before = ctx.state.version
            try:
                with telemetry.stage("ai_turn"):
                    produced = await run_ai_turn(ctx)
            except TrialGuardFailure as pause:
                telemetry.set_answer_flags(guard_tripped=f"trial:{pause.slot}")
                notice = ctx.add("CHU_TOA", GUARD_PAUSE_TEXT, kind="notice", flags=["guard_pause"])
                await asyncio.shield(asyncio.to_thread(
                    repo.insert_utterances, utterance_rows([notice], session_id, user_id)))
                yield _sse_format("utterance", utterance_out(notice, ctx.case))
                break
            if not await _persist(repo, user_id, session_id, ctx, produced, before):
                logger.warning("Trial state write lost its version race (session hash only in telemetry)")
                yield _sse_format("error", ChatStreamErrorEvent(message=TURN_FAILED_TEXT))
                return
            _log_turn(ctx, produced, "ai", 0)
            for event in _events_for(produced, ctx):
                yield event
        if ctx.state.status == "completed" and ctx.record_summary is None and ctx.state.user_role != CLERK_ROLE:
            # The session is already stored as completed; the summary only improves the biên bản.
            # A Thư ký session has none: the student writes IV.2 and IV.3 (decision 7).
            yield _sse_format("status", ChatStreamStatusEvent(message=RECORD_STATUS_TEXT))
            with telemetry.stage("record_summary"):
                await asyncio.shield(_summarise_and_store(repo, user_id, session_id, ctx))
        yield _sse_format("state", _state_of(session_id, ctx))
        yield _sse_format("done", TrialDoneEvent())
    except (asyncio.CancelledError, GeneratorExit):
        outcome = "cancelled"
        raise
    except BaseException as error:  # noqa: BLE001 - same reasoning as api/chat.py's query_chat
        logger.exception("Trial stream failed after the response started")
        outcome, failure = "error", error
        yield _sse_format("error", ChatStreamErrorEvent(message=TURN_FAILED_TEXT))
    finally:
        try:
            repo.release_lock(user_id, session_id)
        except Exception:  # noqa: BLE001 - an expired lock frees itself after GENERATION_LOCK_SECONDS
            logger.warning("Trial lock release failed; it expires on its own")
        _log_calls(ctx.recorder)
        telemetry.finish_request(outcome, failure)


@router.get("", response_model=TrialListResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def list_trials(request: Request, current_user: AuthUser = Depends(require_supabase_user),
                      repo: TrialRepository = Depends(get_trial_repository)) -> TrialListResponse:
    user_id = current_user.user_id
    await asyncio.to_thread(repo.abandon_stale, user_id, _stale_cutoff())
    rows = await asyncio.to_thread(repo.list_sessions, user_id)
    usage_available = True
    try:
        cases_today = await asyncio.to_thread(repo.count_usage_since, user_id, _today_start_utc())
    except DataUnavailable:
        # Fail closed (migration 0014 missing or Supabase down): no quota left, and say why, so the
        # client does not report "5 cases used"; POST answers 503.
        logger.warning("Trial usage log unreadable; reporting no remaining cases")
        cases_today, usage_available = MAX_CASES_PER_DAY, False
    active = sum(1 for r in rows if r["status"] == "active")
    config = TrialConfigOut(
        crimes=[TrialCrimeOut(crime_key=c.key, crime_name=c.crime_name, dieu=c.dieu, allowed_khoan=list(c.allowed_khoan))
                for c in CRIMES.values()],
        user_roles=sorted(ENABLED_USER_ROLES),
        limits=TrialLimitsOut(max_cases_per_day=MAX_CASES_PER_DAY, max_active_sessions=MAX_ACTIVE_SESSIONS,
                              max_witnesses=MAX_WITNESSES, abandon_after_days=ABANDON_AFTER_DAYS),
        remaining=TrialRemainingOut(cases_today=max(0, MAX_CASES_PER_DAY - cases_today),
                                    active_sessions=max(0, MAX_ACTIVE_SESSIONS - active),
                                    usage_available=usage_available),
    )
    return TrialListResponse(sessions=[summary_out(r) for r in rows], config=config)


@router.head("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def probe_trials(request: Request, current_user: AuthUser = Depends(require_supabase_user)) -> Response:
    """Feature probe for the frontend: 204 when TRIAL_ENABLED (the router dependency answers 404
    otherwise). Unlike GET it runs no stale-session cleanup and no limit counting."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("")
@limiter.limit(LLM_ROUTE_RATE_LIMIT)
async def create_trial(body: TrialCreateRequest, request: Request,
                       current_user: AuthUser = Depends(require_supabase_user),
                       settings: Settings = Depends(get_settings),
                       repo: TrialRepository = Depends(get_trial_repository)):
    if body.crime_key not in CRIMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown crime_key")
    user_id = current_user.user_id
    await asyncio.to_thread(repo.abandon_stale, user_id, _stale_cutoff())
    # Both daily limits count the usage log (migration 0014), never the case rows a user can delete.
    # Unreadable log = no case: fail closed instead of creating without a limit.
    try:
        used_today = await asyncio.to_thread(repo.count_usage_since, user_id, _today_start_utc())
        used_today_all = await asyncio.to_thread(repo.count_all_usage_since, _today_start_utc())
    except DataUnavailable:
        logger.error("Trial usage log unreadable (is migration 0014 run?); case creation refused")
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "trial_usage_log_unavailable", USAGE_LOG_UNAVAILABLE_TEXT)
    if used_today >= MAX_CASES_PER_DAY:
        return _error(status.HTTP_429_TOO_MANY_REQUESTS, "trial_daily_case_limit",
                      f"Mỗi ngày chỉ tạo được tối đa {MAX_CASES_PER_DAY} vụ án.")
    if await asyncio.to_thread(repo.count_active_sessions, user_id) >= MAX_ACTIVE_SESSIONS:
        return _error(status.HTTP_429_TOO_MANY_REQUESTS, "trial_active_session_limit",
                      f"Chỉ được có tối đa {MAX_ACTIVE_SESSIONS} phiên tòa đang dở dang.")
    # System-wide cost cap, checked last so a user's own limits are reported first. Only creation
    # is refused: sessions already running keep playing (their turns never come through here).
    if used_today_all >= global_daily_case_limit(settings):
        logger.warning("Trial global daily case limit reached")
        return _error(status.HTTP_429_TOO_MANY_REQUESTS, "trial_global_daily_limit", GLOBAL_LIMIT_TEXT)

    telemetry.start_request(user_id, source="trial")
    telemetry.set_path("trial_create")
    qdrant_client = request.app.state.qdrant_client
    options = CaseOptions(**body.model_dump())
    recorder = TrialCallRecorder()

    async def event_stream() -> AsyncIterator[str]:
        outcome, failure = "ok", None
        try:
            yield _sse_format("status", ChatStreamStatusEvent(message="Đang chuẩn bị hồ sơ pháp lý của vụ án..."))
            pack = await load_pack_for_crime(get_crime(body.crime_key), settings, qdrant_client)
            yield _sse_format("status", ChatStreamStatusEvent(message="Đang dựng hồ sơ vụ án giả định..."))
            with telemetry.stage("case_generation"):
                creation = await create_case(options, settings, qdrant_client, recorder, pack=pack)
            ctx = TrialContext(case=creation.case, pack=creation.pack,
                               state=new_session(body.user_role, shape_of(creation.case)), settings=settings,
                               recorder=recorder)
            while awaiting(ctx.state) == "ai":  # step 1 is a template: no LLM call
                await run_ai_turn(ctx)

            def write() -> str:
                case_id = repo.insert_case({
                    "user_id": user_id, "crime_key": body.crime_key,
                    "case_schema_version": creation.case.schema_version,
                    "case_json": creation.case.model_dump(mode="json"), "case_hash": creation.case_hash,
                    "legal_pack": creation.pack.to_payloads(), "generation_model": settings.gemini_chat_model,
                    "generation_attempts": creation.attempts,
                })
                try:
                    session_id = repo.insert_session({"user_id": user_id, "case_id": case_id,
                                                      "user_role": body.user_role, **state_fields(ctx)})
                    repo.insert_utterances(utterance_rows(ctx.transcript, session_id, user_id))
                    # Last: only a creation that is fully stored counts against the limits.
                    repo.log_case_created(user_id)
                except Exception:
                    repo.delete_case(user_id, case_id)  # no orphan case without its usage row
                    raise
                return session_id

            session_id = await asyncio.shield(asyncio.to_thread(write))
            yield _sse_format("session", TrialSessionEvent(session_id=session_id, title=creation.case.draft.title))
            for event in _events_for(ctx.transcript, ctx):
                yield event
            yield _sse_format("state", _state_of(session_id, ctx))
            yield _sse_format("done", TrialDoneEvent())
            logger.info("TRIAL_CREATE %s", json.dumps({"crime": body.crime_key, "attempts": creation.attempts,
                                                       "calls": len(recorder.records)}))
        except CaseGenerationFailed as error:
            telemetry.set_answer_flags(guard_tripped="trial:case_validation")
            outcome, failure = "error", error
            yield _sse_format("error", ChatStreamErrorEvent(message=CREATE_FAILED_TEXT))
        except (asyncio.CancelledError, GeneratorExit):
            outcome = "cancelled"
            raise
        except BaseException as error:  # noqa: BLE001
            logger.exception("Trial creation failed after the response started")
            outcome, failure = "error", error
            yield _sse_format("error", ChatStreamErrorEvent(message=CREATE_FAILED_TEXT))
        finally:
            _log_calls(recorder)
            telemetry.finish_request(outcome, failure)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _load(repo: TrialRepository, user_id: str, session_id: uuid.UUID, settings: Settings,
                recorder: TrialCallRecorder) -> tuple[dict, TrialContext]:
    await asyncio.to_thread(repo.abandon_stale, user_id, _stale_cutoff())
    session = await asyncio.to_thread(repo.get_session, user_id, str(session_id))
    if session is None:
        raise _not_found()
    case = await asyncio.to_thread(repo.get_case, user_id, session["case_id"])
    if case is None:
        raise _not_found()
    rows = await asyncio.to_thread(repo.list_utterances, user_id, str(session_id))
    return session, build_context(case, session, rows, settings, recorder)


@router.get("/{session_id}", response_model=TrialDetailResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_trial(session_id: uuid.UUID, request: Request, current_user: AuthUser = Depends(require_supabase_user),
                    settings: Settings = Depends(get_settings),
                    repo: TrialRepository = Depends(get_trial_repository)) -> TrialDetailResponse:
    session, ctx = await _load(repo, current_user.user_id, session_id, settings, TrialCallRecorder())
    case = ctx.case
    return TrialDetailResponse(
        state=_state_of(str(session_id), ctx), title=case.draft.title, crime_key=case.crime_key,
        user_role=session["user_role"], disclaimer=case.disclaimer, court=case.court.model_dump(),
        participants={pid: p.model_dump() for pid, p in case.participants.items()},
        case_file=student_case_view(case), steps=steps_view(),
        utterances=[utterance_out(u, case) for u in ctx.transcript],
    )


@router.post("/{session_id}/turn")
@limiter.limit(LLM_ROUTE_RATE_LIMIT)
async def trial_turn(session_id: uuid.UUID, body: TrialTurnRequest, request: Request,
                     current_user: AuthUser = Depends(require_supabase_user),
                     settings: Settings = Depends(get_settings),
                     repo: TrialRepository = Depends(get_trial_repository)):
    user_id, sid = current_user.user_id, str(session_id)
    session, ctx = await _load(repo, user_id, session_id, settings, TrialCallRecorder())
    stored_version = ctx.state.version
    if ctx.state.status != "active":
        return _conflict("not_active", sid, ctx)

    student_utterances: list[Utterance] = []
    if body.action == "continue":
        if (body.expected_version != stored_version or body.expected_step != ctx.state.current_step):
            return _conflict("version_mismatch", sid, ctx)
        if awaiting(ctx.state) != "ai":
            return _conflict("not_ai_turn", sid, ctx)
        if consecutive_guard_pauses(ctx) >= MAX_CONSECUTIVE_GUARD_PAUSES:
            return _conflict("guard_exhausted", sid, ctx)
        ctx.state = replace(ctx.state, version=stored_version + 1)  # so two parallel "continue" cannot both run
    else:
        try:
            student_utterances = apply_student_action(ctx, UserAction(
                kind=body.action, expected_step=body.expected_step, expected_version=body.expected_version,
                text=body.text, addressee=body.addressee, target_step=body.target_step))
        except TrialConflict as conflict:
            return _conflict(conflict.code, sid, ctx)

    needs_ai = ctx.state.status == "active" and awaiting(ctx.state) == "ai"
    claimed = await asyncio.to_thread(
        repo.claim_and_update, user_id, sid, stored_version, state_fields(ctx),
        lock_deadline(GENERATION_LOCK_SECONDS) if needs_ai else None)
    if not claimed:
        return _conflict("busy", sid, ctx)
    if student_utterances:
        await asyncio.to_thread(repo.insert_utterances, utterance_rows(student_utterances, sid, user_id))

    telemetry.start_request(user_id, source="trial")
    telemetry.set_path("trial_buffer")
    _log_turn(ctx, student_utterances, body.action, len(body.text or ""))
    first = _events_for(student_utterances, ctx)
    return StreamingResponse(run_ai_stream(repo, user_id, sid, ctx, first), media_type="text/event-stream")


@router.post("/{session_id}/abandon")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def abandon_trial(session_id: uuid.UUID, request: Request,
                        current_user: AuthUser = Depends(require_supabase_user),
                        settings: Settings = Depends(get_settings),
                        repo: TrialRepository = Depends(get_trial_repository)):
    session, ctx = await _load(repo, current_user.user_id, session_id, settings, TrialCallRecorder())
    if ctx.state.status == "active":
        await asyncio.to_thread(repo.set_status, current_user.user_id, str(session_id), "abandoned")
        ctx.state = replace(ctx.state, status="abandoned")
    return _state_of(str(session_id), ctx)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def delete_trial(session_id: uuid.UUID, request: Request,
                       current_user: AuthUser = Depends(require_supabase_user),
                       repo: TrialRepository = Depends(get_trial_repository)) -> Response:
    if not await asyncio.to_thread(repo.delete_session, current_user.user_id, str(session_id)):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{session_id}/record", response_model=TrialRecordResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def trial_record(session_id: uuid.UUID, request: Request,
                       current_user: AuthUser = Depends(require_supabase_user),
                       settings: Settings = Depends(get_settings),
                       repo: TrialRepository = Depends(get_trial_repository)):
    session, ctx = await _load(repo, current_user.user_id, session_id, settings, TrialCallRecorder())
    if ctx.state.status != "completed":
        return _conflict("not_completed", str(session_id), ctx)
    return _record_response(session_id, session, ctx)


def _record_response(session_id: uuid.UUID, session: dict, ctx: TrialContext) -> TrialRecordResponse:
    """Built by code, no LLM call. A Thư ký session shows the student's own IV.2 / IV.3 (a draft
    until finalised) and carries the editable draft with its notices."""
    started, ended = _as_datetime(session.get("created_at")), _as_datetime(session.get("completed_at"))
    clerk = None
    if session["user_role"] == CLERK_ROLE:
        draft = draft_of(session.get("user_work"))
        record = build_record(ctx.case, ctx.transcript, started, ended, clerk=draft.sections(),
                              draft=not draft.finalized)
        clerk = _clerk_draft_out(ctx, session.get("user_work"))
    else:
        record = build_record(ctx.case, ctx.transcript, started, ended, summary=ctx.record_summary,
                              observer=session["user_role"] == OBSERVER_ROLE)
    return TrialRecordResponse(session_id=session_id, text=render_record_text(record), record=record, clerk=clerk)


# --- Thư ký (chặng R2, design doc Mục 11.3): notes and the biên bản draft --------------------------
# Not utterances: they never go through /turn, never change the state or its version, and are
# never put into a prompt or a log line (lengths and labels only).

def _clerk_draft_out(ctx: TrialContext, user_work: dict | None) -> TrialClerkDraftOut:
    draft = draft_of(user_work)
    return TrialClerkDraftOut(
        iv2=draft.iv2, iv3=draft.iv3, updated_at=_as_datetime(draft.updated_at), finalized=draft.finalized,
        finalized_at=_as_datetime(draft.finalized_at),
        notices=[n.as_dict() for n in review_draft(ctx.case, ctx.transcript, draft)],
        limits={"min": SECTION_MIN_CHARS, "max": SECTION_MAX_CHARS, "hard_max": SECTION_HARD_MAX_CHARS})


def _clerk_refusal(session: dict, ctx: TrialContext, session_id: str, *, completed: bool) -> JSONResponse | None:
    """409 unless this is a Thư ký session in a status that allows the action: notes while active
    or completed, the draft and finalising only once completed."""
    if session["user_role"] != CLERK_ROLE:
        return _conflict("not_clerk", session_id, ctx)
    if completed and ctx.state.status != "completed":
        return _conflict("not_completed", session_id, ctx)
    if ctx.state.status not in ("active", "completed"):
        return _conflict("not_active", session_id, ctx)
    return None


async def _save_user_work(repo: TrialRepository, user_id: str, session_id: str, work: dict) -> None:
    if not await asyncio.to_thread(repo.update_user_work, user_id, session_id, work):
        raise _not_found()   # deleted meanwhile


def _log_clerk(action: str, **counts) -> None:
    logger.info("TRIAL_CLERK %s", json.dumps({"action": action, **counts}))


@router.get("/{session_id}/notes", response_model=TrialNotesOut)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_trial_notes(session_id: uuid.UUID, request: Request,
                          current_user: AuthUser = Depends(require_supabase_user),
                          settings: Settings = Depends(get_settings),
                          repo: TrialRepository = Depends(get_trial_repository)):
    session, ctx = await _load(repo, current_user.user_id, session_id, settings, TrialCallRecorder())
    if session["user_role"] != CLERK_ROLE:
        return _conflict("not_clerk", str(session_id), ctx)
    notes, updated_at = notes_of(session.get("user_work"))
    return TrialNotesOut(notes=notes, updated_at=_as_datetime(updated_at), max_chars=NOTES_MAX_CHARS)


@router.put("/{session_id}/notes", response_model=TrialNotesOut)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def put_trial_notes(session_id: uuid.UUID, body: TrialNotesRequest, request: Request,
                          current_user: AuthUser = Depends(require_supabase_user),
                          settings: Settings = Depends(get_settings),
                          repo: TrialRepository = Depends(get_trial_repository)):
    user_id, sid = current_user.user_id, str(session_id)
    session, ctx = await _load(repo, user_id, session_id, settings, TrialCallRecorder())
    refusal = _clerk_refusal(session, ctx, sid, completed=False)
    if refusal is not None:
        return refusal
    notes = clean_notes(body.text)
    work = with_notes(session.get("user_work"), notes, utc_now())
    await _save_user_work(repo, user_id, sid, work)
    _log_clerk("notes", chars=len(notes))
    return TrialNotesOut(notes=notes, updated_at=_as_datetime(work["notes_updated_at"]), max_chars=NOTES_MAX_CHARS)


@router.put("/{session_id}/record/draft", response_model=TrialClerkDraftOut)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def put_record_draft(session_id: uuid.UUID, body: TrialRecordDraftRequest, request: Request,
                           current_user: AuthUser = Depends(require_supabase_user),
                           settings: Settings = Depends(get_settings),
                           repo: TrialRepository = Depends(get_trial_repository)):
    user_id, sid = current_user.user_id, str(session_id)
    session, ctx = await _load(repo, user_id, session_id, settings, TrialCallRecorder())
    refusal = _clerk_refusal(session, ctx, sid, completed=True)
    if refusal is not None:
        return refusal
    if draft_of(session.get("user_work")).finalized:
        return _conflict("record_finalized", sid, ctx)
    work = with_draft(session.get("user_work"), {"iv2": body.iv2, "iv3": body.iv3}, utc_now())
    await _save_user_work(repo, user_id, sid, work)
    out = _clerk_draft_out(ctx, work)
    _log_clerk("draft", chars={k: len(getattr(out, k)) for k in CLERK_SECTIONS},
               notices=sorted({f"{n.section}:{n.code}" for n in out.notices}))
    return out


@router.post("/{session_id}/record/finalize", response_model=TrialRecordResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def finalize_record(session_id: uuid.UUID, request: Request,
                          current_user: AuthUser = Depends(require_supabase_user),
                          settings: Settings = Depends(get_settings),
                          repo: TrialRepository = Depends(get_trial_repository)):
    """Finalises the stored draft. Notices never block it (decision 6); only an empty section does,
    since the record would then have no IV.2 or IV.3 at all. Idempotent: finalising again returns
    the same record."""
    user_id, sid = current_user.user_id, str(session_id)
    session, ctx = await _load(repo, user_id, session_id, settings, TrialCallRecorder())
    refusal = _clerk_refusal(session, ctx, sid, completed=True)
    if refusal is not None:
        return refusal
    draft = draft_of(session.get("user_work"))
    if not draft.finalized:
        if any(not text.strip() for text in draft.sections().values()):
            return _conflict("record_section_empty", sid, ctx)
        session["user_work"] = with_finalized(session.get("user_work"), utc_now())
        await _save_user_work(repo, user_id, sid, session["user_work"])
        _log_clerk("finalize", chars={k: len(v) for k, v in draft.sections().items()})
    return _record_response(session_id, session, ctx)


def _as_datetime(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
