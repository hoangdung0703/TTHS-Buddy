"""Telling "there is no data" apart from "the data could not be read".

Until 2026-10-17 every Supabase read behind the sidebar history, the dashboard and the quiz pages
caught any exception, logged it, and returned an empty result - which the route then sent as a
perfectly normal 200. A student whose read failed saw an empty history, a dashboard of zeros, a
quiz page with every set "untouched", and the sentence "Không có chủ đề nào cần ôn lại" - all
indistinguishable from a brand-new account, and on 2026-10-10 (PGRST303) all of them at once. The
dashboard page already had an error state with a retry button; it could never be reached, because
the backend never said anything had gone wrong.

This module gives those reads one shared policy:

* `execute_with_retry` runs a query, and if it fails with a TRANSIENT error retries it exactly
  once after a short pause. Anything still failing becomes `DataUnavailable`.
* `DataUnavailable` is turned into an HTTP error by the handler in core/middleware.py: 503 when
  the failure was transient (worth retrying from the client), 500 when it was not (retrying the
  same request will fail the same way). Both go through a registered exception handler on
  purpose - see that handler for why this matters for CORS.

Only reads and idempotent writes (delete/update filtered by id) go through the retry. Inserts do
not: if an insert times out after the row was actually committed, sending it again would store a
second copy, so the two insert paths (log_chat_query, save_quiz_attempt) make one attempt and
report the outcome to their caller instead.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
from postgrest.exceptions import APIError

from app.core.logging import get_logger

logger = get_logger(__name__)

RETRY_BACKOFF_SECONDS = 0.3

# PostgREST error codes worth one more try. Everything else from PostgREST (PGRST1xx request
# errors, PGRST2xx schema-cache errors, the other PGRST3xx JWT errors) and every other Postgres
# SQLSTATE describes a request that will fail the same way again.
_TRANSIENT_POSTGREST_CODES = frozenset({
    "PGRST000",  # could not connect to the database (PostgREST answers 503)
    "PGRST001",  # could not connect due to an internal error (503)
    "PGRST002",  # could not connect while building the schema cache (503)
    "PGRST003",  # timed out acquiring a connection from the pool (504)
    "PGRST303",  # JWT claims validation failed - the 2026-10-10 incident; clock skew between
                 # Supabase's own services passes on its own, which is why it is in this set
    "57014",     # query_canceled: the statement hit its timeout
})


class DataUnavailable(Exception):
    """A Supabase read (or idempotent write) that failed and should be REPORTED to the client
    instead of being turned into an empty result.

    `transient` records whether the final failure was the kind that can pass on its own, which
    decides 503 vs 500. `what` is a short fixed description of the operation for the logs - never
    anything taken from the request."""

    def __init__(self, what: str, *, transient: bool) -> None:
        self.what = what
        self.transient = transient
        super().__init__(f"{what} ({'transient' if transient else 'non-transient'})")


def is_transient(error: BaseException) -> bool:
    # httpx.TransportError covers every way the HTTP exchange itself can fail: connect/read/write
    # timeouts, refused or reset connections, protocol errors.
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, APIError):
        code = error.code
        # postgrest falls back to the bare HTTP status as an int when the error body is not
        # PostgREST JSON - which is exactly what a gateway in front of it (Cloudflare 502/504)
        # produces.
        if isinstance(code, int):
            return code >= 500
        if isinstance(code, str):
            # Postgres SQLSTATE class 08 = connection exception.
            return code in _TRANSIENT_POSTGREST_CODES or code.startswith("08")
    return False


def _describe(error: BaseException) -> str:
    """Error class plus code only. PostgREST's message/details can echo filter values back, so they
    stay out of this line; logger.exception on the final failure keeps the full detail for
    debugging, as the code it replaces did."""
    code = getattr(error, "code", None)
    return f"{type(error).__name__}" + (f" {code}" if code is not None else "")


def execute_with_retry(build_query: Callable[[], Any], what: str) -> Any:
    """Executes the query that `build_query()` returns, retrying once on a transient failure.

    Takes a factory rather than a built query so each attempt gets a fresh builder.

    postgrest-py's own retry is switched OFF for these calls (`.retry(False)`), so that this is the
    only retry policy in play. Left on, it retries a GET that comes back 503/520 up to three more
    times with 1s/2s/4s sleeps - a student would wait ~7s before this function even saw the error,
    and ~15s once its own retry ran the whole sequence a second time.
    """
    for attempt in (1, 2):
        try:
            return build_query().retry(False).execute()
        except Exception as error:
            transient = is_transient(error)
            if transient and attempt == 1:
                logger.warning("%s failed (%s) - retrying once in %ss",
                               what, _describe(error), RETRY_BACKOFF_SECONDS)
                time.sleep(RETRY_BACKOFF_SECONDS)
                continue
            logger.exception("%s failed (%s, %s, attempt %d) - reporting to the client",
                             what, _describe(error), "transient" if transient else "non-transient",
                             attempt)
            raise DataUnavailable(what, transient=transient) from error
    raise AssertionError("unreachable")  # the loop always returns or raises
