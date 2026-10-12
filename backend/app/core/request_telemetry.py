"""Structured per-request server logging for the chat path.

Why this exists: `log_chat_query` only runs AFTER the SSE stream finishes, so a request that hung,
errored, or had its connection dropped left no trace anywhere - the exact failures worth
investigating were the ones that produced no evidence. This module emits TWO log lines per
request, one when it starts and one when it ends (successfully or not), so a missing end line is
itself the signal that something broke.

Deliberately log-only: no DB write, no schema change, no migration. Render's log stream is the
consumer.

NEVER logs question or answer text. The user is identified by a truncated SHA-256 of their id, so
rows can be correlated within the logs without carrying an identifier back to a person.

Timings are collected through a ContextVar rather than threaded through every signature.
`asyncio.to_thread` propagates the current context, and the ContextVar holds one mutable
RequestTelemetry object, so stages timed inside a worker thread (Qdrant calls, the sync Gemini
re-rank) mutate the same object the request handler will later emit. One consequence worth
knowing: under `-w 2` each Gunicorn/Uvicorn worker is its own process, so
`seconds_since_process_start` and `first_request_after_boot` are per-worker, not per-service - a
service that just woke up produces one first_request_after_boot=true line per worker that gets
traffic, not exactly one overall.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.core.logging import get_logger

logger = get_logger(__name__)

# Monotonic, so it is immune to wall-clock adjustments; set when this module is first imported,
# which for the API process is during app startup.
_PROCESS_START = time.monotonic()
_requests_seen = 0

START_EVENT = "chat_request_start"
END_EVENT = "chat_request_end"


def _hash_user(user_id: str) -> str:
    """Truncated SHA-256. Enough to group a user's requests together in the logs, not enough to
    recover the id - and stable across requests and across workers, unlike a per-request salt."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


@dataclass
class RequestTelemetry:
    request_id: str
    user_hash: str
    seconds_since_process_start: float
    first_request_after_boot: bool
    started_monotonic: float
    # Stage name -> seconds. Several stages can repeat (one retrieval per sub-question on the
    # multi-part path), so repeats accumulate and a count is kept alongside.
    stage_seconds: dict[str, float] = field(default_factory=dict)
    stage_counts: dict[str, int] = field(default_factory=dict)
    # "stream" | "buffer" | "buffer_multipart" | "buffer_anonymization" | "short_circuit:<intent>"
    path: str | None = None
    # The model that actually produced the answer, which is not always the one first attempted.
    answering_model: str | None = None
    fallback_reasons: list[str] = field(default_factory=list)
    time_to_first_token: float | None = None
    is_fallback_answer: bool | None = None
    guard_tripped: str | None = None

    def elapsed(self) -> float:
        return time.monotonic() - self.started_monotonic


_current: contextvars.ContextVar[RequestTelemetry | None] = contextvars.ContextVar(
    "request_telemetry", default=None
)


def current() -> RequestTelemetry | None:
    return _current.get()


def start_request(user_id: str) -> RequestTelemetry:
    """Emits the START line and binds the telemetry object to the current context.

    Called as early in the handler as possible - after auth and rate limiting (a rejected request
    is not a chat request), before any I/O - so that a request which later hangs or is cut off
    still leaves this line behind."""
    global _requests_seen
    _requests_seen += 1
    telemetry = RequestTelemetry(
        request_id=uuid.uuid4().hex[:16],
        user_hash=_hash_user(user_id),
        seconds_since_process_start=round(time.monotonic() - _PROCESS_START, 2),
        first_request_after_boot=_requests_seen == 1,
        started_monotonic=time.monotonic(),
    )
    _current.set(telemetry)
    logger.info("%s %s", START_EVENT, json.dumps({
        "request_id": telemetry.request_id,
        "user": telemetry.user_hash,
        "seconds_since_process_start": telemetry.seconds_since_process_start,
        "first_request_after_boot": telemetry.first_request_after_boot,
    }, ensure_ascii=False))
    return telemetry


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Times a named stage into the request's telemetry. A no-op when nothing is bound (the
    evaluation scripts call into rag_service directly, with no request around them), so
    instrumentation never depends on being inside a request."""
    telemetry = _current.get()
    if telemetry is None:
        yield
        return
    started = time.monotonic()
    try:
        yield
    finally:
        taken = time.monotonic() - started
        telemetry.stage_seconds[name] = round(telemetry.stage_seconds.get(name, 0.0) + taken, 3)
        telemetry.stage_counts[name] = telemetry.stage_counts.get(name, 0) + 1


def set_path(path: str) -> None:
    """The route actually taken. Callers derive this from the SAME expression that decides
    buffering (rag_service's buffer_for_rule9_risk), never from chat_query_logs'
    used_academic_reference column - that column is zeroed on fallback answers and so disagrees
    with the real path (see requirements.md, 2026-10-12)."""
    if (telemetry := _current.get()) is not None:
        telemetry.path = path


def set_answering_model(model: str) -> None:
    if (telemetry := _current.get()) is not None and telemetry.answering_model is None:
        telemetry.answering_model = model


def add_fallback_reason(reason: str) -> None:
    if (telemetry := _current.get()) is not None:
        telemetry.fallback_reasons.append(reason)


def mark_first_token() -> None:
    if (telemetry := _current.get()) is not None and telemetry.time_to_first_token is None:
        telemetry.time_to_first_token = round(telemetry.elapsed(), 3)


def set_answer_flags(is_fallback: bool | None = None, guard_tripped: str | None = None) -> None:
    if (telemetry := _current.get()) is None:
        return
    if is_fallback is not None:
        telemetry.is_fallback_answer = is_fallback
    if guard_tripped is not None:
        telemetry.guard_tripped = guard_tripped


def finish_request(outcome: str, error: BaseException | None = None) -> None:
    """Emits the END line. `outcome` is "ok", "client_disconnected", or "error".

    Only the exception TYPE and a truncated message are logged - an exception string can quote the
    payload that caused it, which on this path could include the student's question."""
    telemetry = _current.get()
    if telemetry is None:
        return
    payload: dict[str, Any] = {
        "request_id": telemetry.request_id,
        "user": telemetry.user_hash,
        "outcome": outcome,
        "path": telemetry.path,
        "total_seconds": round(telemetry.elapsed(), 3),
        "time_to_first_token": telemetry.time_to_first_token,
        "answering_model": telemetry.answering_model,
        "fallback_reasons": telemetry.fallback_reasons or None,
        "is_fallback_answer": telemetry.is_fallback_answer,
        "guard_tripped": telemetry.guard_tripped,
        "stages": telemetry.stage_seconds or None,
        "stage_counts": {k: v for k, v in telemetry.stage_counts.items() if v > 1} or None,
        "seconds_since_process_start": telemetry.seconds_since_process_start,
        "first_request_after_boot": telemetry.first_request_after_boot,
    }
    if error is not None:
        payload["error_type"] = type(error).__name__
        payload["error"] = str(error)[:200]
    logger.info("%s %s", END_EVENT, json.dumps(
        {k: v for k, v in payload.items() if v is not None}, ensure_ascii=False))
