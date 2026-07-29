"""Gemini REST client for the RAG query path: embeds the user's question and generates the
grounded answer. Uses the REST API directly (same pattern as ingestion/embedding_client.py and
ingestion/ocr_fallback.py) rather than the SDK, and reuses the same retry-on-5xx/429 approach.
"""
from __future__ import annotations

import time

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EMBED_CONTENT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
GENERATE_CONTENT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

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


def generate_answer(system_prompt: str, user_prompt: str, settings: Settings) -> str:
    url = GENERATE_CONTENT_URL_TEMPLATE.format(model=settings.gemini_chat_model)
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1}
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
