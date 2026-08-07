"""Gemini REST client for the RAG query path: embeds the user's question and generates the
grounded answer. Uses the REST API directly (same pattern as ingestion/embedding_client.py and
ingestion/ocr_fallback.py) rather than the SDK, and reuses the same retry-on-5xx/429 approach.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EMBED_CONTENT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
GENERATE_CONTENT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
STREAM_GENERATE_CONTENT_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
)

QUERY_EMBEDDING_TASK_TYPE = "RETRIEVAL_QUERY"
OUTPUT_DIMENSIONALITY = 768  # must match the collection vector size and ingestion's embedding output
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_TRANSIENT_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5.0


def _post_with_retry(url: str, api_key: str, body: dict) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, MAX_TRANSIENT_RETRIES + 1):
        try:
            response = httpx.post(url, params={"key": api_key}, json=body, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code >= 500 or response.status_code == 429:
                raise httpx.HTTPStatusError(
                    f"Retryable HTTP {response.status_code}: {response.text[:200]}",
                    request=response.request, response=response
                )
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            last_error = error
            logger.warning("Gemini request failed (attempt %d/%d): %s", attempt, MAX_TRANSIENT_RETRIES, error)
            if attempt < MAX_TRANSIENT_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    assert last_error is not None
    raise last_error


def embed_query(text: str, settings: Settings) -> list[float]:
    url = EMBED_CONTENT_URL_TEMPLATE.format(model=settings.gemini_embedding_model)
    body = {
        "model": f"models/{settings.gemini_embedding_model}",
        "content": {"parts": [{"text": text}]},
        "taskType": QUERY_EMBEDDING_TASK_TYPE,
        "outputDimensionality": OUTPUT_DIMENSIONALITY
    }
    response = _post_with_retry(url, settings.google_api_key, body)
    return response.json()["embedding"]["values"]


def generate_answer(system_prompt: str, user_prompt: str, settings: Settings, response_json: bool = False) -> str:
    url = GENERATE_CONTENT_URL_TEMPLATE.format(model=settings.gemini_chat_model)
    generation_config: dict[str, object] = {"temperature": 0.1}
    if response_json:
        # Used by essay_service.py's grading call - structured output means we can classify
        # each rubric point by array position instead of fuzzy-matching LLM-reproduced text
        # against the rubric strings.
        generation_config["responseMimeType"] = "application/json"

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": generation_config
    }
    response = _post_with_retry(url, settings.google_api_key, body)
    data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini generateContent returned no candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        finish_reason = candidates[0].get("finishReason")
        raise RuntimeError(f"Gemini generateContent returned no content (finishReason={finish_reason})")

    return parts[0].get("text", "").strip()


async def stream_generate_answer(
    system_prompt: str, user_prompt: str, settings: Settings, model: str | None = None,
    fallback_model: str | None = None, first_token_timeout: float | None = None
) -> AsyncIterator[str]:
    """Async generator yielding answer text deltas as they arrive from Gemini's SSE streaming
    endpoint (?alt=sse) - used only for the final answer generation in the chat SSE path
    (Phase 4 Extension), where the caller needs to forward partial text to the client as it's
    generated. Every other Gemini call in this service stays on the plain (non-streaming)
    generate_answer above, matching the rest of the codebase's sync httpx usage - only this one
    call genuinely needs to hold a connection open and yield incrementally.

    `model` lets the caller override settings.gemini_chat_model - used by rag_service.py to route
    long/tình huống questions to settings.resolved_complex_chat_model (see requirements.md "Tăng
    impact LLM cho câu hỏi dài/phức tạp") without touching every other caller's default model.

    `fallback_model` + `first_token_timeout` implement that feature's fallback step: preview-tier
    models (e.g. gemini-3.1-pro-preview) return transient 503 "high demand" noticeably more often
    than the GA flash-lite default AND have highly variable latency (5s-68s observed in manual
    testing) - so `model` gets exactly ONE attempt, and a 503/429/transport failure OR
    `first_token_timeout` elapsing with zero tokens yielded switches immediately to
    `fallback_model` (no backoff sleep - the fallback IS the recovery, sleeping first would only
    add to the latency this exists to cap). The LAST model in the attempt chain (fallback_model if
    given, otherwise model itself) keeps the original retry-with-backoff behavior
    (MAX_TRANSIENT_RETRIES attempts) - so a caller with no fallback_model (every call site except
    the long-question path) sees unchanged behavior. Once any answer text has actually been
    yielded to the caller, neither a same-model retry nor a fallback is attempted - either would
    duplicate already-sent tokens - so failures past that point simply propagate.
    """
    primary_model = model or settings.gemini_chat_model
    models_to_try = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models_to_try.append(fallback_model)

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }

    last_error: Exception | None = None
    for model_index, current_model in enumerate(models_to_try):
        is_last_model_in_chain = model_index == len(models_to_try) - 1
        max_attempts = MAX_TRANSIENT_RETRIES if is_last_model_in_chain else 1
        url = STREAM_GENERATE_CONTENT_URL_TEMPLATE.format(model=current_model)

        for attempt in range(1, max_attempts + 1):
            yielded_any = False
            # Deadline is absolute (set once per attempt, before opening the connection) and
            # covers BOTH connect+headers AND the subsequent wait for the first real text chunk -
            # NOT just the latter. TTFB (time to response headers) was observed to be the dominant
            # slow part of gemini-3.1-pro-preview (14-20s before headers even arrive on some
            # calls), so a deadline that only starts once headers are already in hand would miss
            # exactly the delay this fallback exists to bound. A per-line timeout re-armed on every
            # SSE line was tried first and rejected - non-text lines (keep-alives, empty candidate
            # chunks) kept resetting it, letting total wait run far past the intended cap.
            first_token_deadline = time.monotonic() + first_token_timeout if first_token_timeout else None

            def _remaining() -> float:
                assert first_token_deadline is not None
                remaining = first_token_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"No token received within {first_token_timeout}s")
                return remaining

            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                    stream_cm = client.stream(
                        "POST", url, params={"key": settings.google_api_key, "alt": "sse"}, json=body
                    )
                    response = (
                        await asyncio.wait_for(stream_cm.__aenter__(), timeout=_remaining())
                        if first_token_deadline is not None else await stream_cm.__aenter__()
                    )
                    try:
                        if response.status_code >= 400:
                            error_body = await response.aread()
                            raise httpx.HTTPStatusError(
                                f"Gemini streamGenerateContent failed with HTTP {response.status_code}: "
                                f"{error_body[:500]!r}",
                                request=response.request, response=response
                            )

                        line_iter = response.aiter_lines()
                        while True:
                            try:
                                if first_token_deadline is not None and not yielded_any:
                                    line = await asyncio.wait_for(line_iter.__anext__(), timeout=_remaining())
                                else:
                                    line = await line_iter.__anext__()
                            except StopAsyncIteration:
                                break

                            if not line.startswith("data:"):
                                continue
                            payload = line[len("data:"):].strip()
                            if not payload or payload == "[DONE]":
                                continue

                            chunk = json.loads(payload)
                            candidates = chunk.get("candidates", [])
                            if not candidates:
                                continue
                            for part in candidates[0].get("content", {}).get("parts", []):
                                text = part.get("text")
                                if text:
                                    yielded_any = True
                                    yield text
                    finally:
                        await stream_cm.__aexit__(None, None, None)
                return
            except (httpx.TransportError, httpx.HTTPStatusError, TimeoutError, asyncio.TimeoutError) as error:
                if yielded_any:
                    raise

                # asyncio.wait_for raises asyncio.TimeoutError, which IS builtins.TimeoutError on
                # Python 3.11+ (this project targets 3.14) - the isinstance check below covers both
                # names as the same type; kept explicit in the except clause for readability.
                is_retryable_status = isinstance(error, httpx.HTTPStatusError) and (
                    error.response.status_code >= 500 or error.response.status_code == 429
                )
                is_transport_error = isinstance(error, httpx.TransportError)
                is_first_token_timeout = isinstance(error, TimeoutError)
                if not (is_retryable_status or is_transport_error or is_first_token_timeout):
                    raise

                last_error = error
                if is_first_token_timeout:
                    logger.warning(
                        "Gemini streamGenerateContent on %s: no token within %ss (attempt %d/%d)",
                        current_model, first_token_timeout, attempt, max_attempts
                    )
                else:
                    logger.warning(
                        "Gemini streamGenerateContent on %s failed before any tokens yielded "
                        "(attempt %d/%d): %s",
                        current_model, attempt, max_attempts, error
                    )
                if attempt < max_attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                # else: exhausted retries for this model - outer loop moves to the next model in
                # models_to_try (the fallback), or raises below if this was the last one.

    assert last_error is not None
    raise last_error
