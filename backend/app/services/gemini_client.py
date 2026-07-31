"""Gemini REST client for the RAG query path: embeds the user's question and generates the
grounded answer. Uses the REST API directly (same pattern as ingestion/embedding_client.py and
ingestion/ocr_fallback.py) rather than the SDK, and reuses the same retry-on-5xx/429 approach.
"""
from __future__ import annotations

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


async def stream_generate_answer(system_prompt: str, user_prompt: str, settings: Settings) -> AsyncIterator[str]:
    """Async generator yielding answer text deltas as they arrive from Gemini's SSE streaming
    endpoint (?alt=sse) - used only for the final answer generation in the chat SSE path
    (Phase 4 Extension), where the caller needs to forward partial text to the client as it's
    generated. Every other Gemini call in this service stays on the plain (non-streaming)
    generate_answer above, matching the rest of the codebase's sync httpx usage - only this one
    call genuinely needs to hold a connection open and yield incrementally.
    """
    url = STREAM_GENERATE_CONTENT_URL_TEMPLATE.format(model=settings.gemini_chat_model)
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        async with client.stream(
            "POST", url, params={"key": settings.google_api_key, "alt": "sse"}, json=body
        ) as response:
            if response.status_code >= 400:
                error_body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"Gemini streamGenerateContent failed with HTTP {response.status_code}: {error_body[:500]!r}",
                    request=response.request, response=response
                )

            async for line in response.aiter_lines():
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
                        yield text
