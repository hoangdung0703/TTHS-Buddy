"""Gemini embedding REST client (per requirements.md tech stack: embeddings go through the
REST API, not an SDK). Uses batchEmbedContents for throughput, with the same retry-on-5xx/429
pattern already proven out in ocr_fallback.py.
"""
from __future__ import annotations

import time

import httpx

from ingestion.config import get_ingestion_settings
from ingestion.logging_utils import get_logger

logger = get_logger(__name__)

BATCH_EMBED_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
)
EMBEDDING_TASK_TYPE = "RETRIEVAL_DOCUMENT"
OUTPUT_DIMENSIONALITY = 768  # matches DEFAULT_VECTOR_SIZE in backend/app/core/config.py
MAX_TEXTS_PER_BATCH = 50
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_TRANSIENT_RETRIES = 5
RETRY_BACKOFF_SECONDS = 10.0
INTER_BATCH_DELAY_SECONDS = 2.0


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
            logger.warning("Gemini embedding request failed (attempt %d/%d): %s",
                            attempt, MAX_TRANSIENT_RETRIES, error)
            if attempt < MAX_TRANSIENT_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    assert last_error is not None
    raise last_error


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embeds up to MAX_TEXTS_PER_BATCH texts in a single request. Caller is responsible for
    chunking longer lists (see embed_texts)."""
    settings = get_ingestion_settings()
    url = BATCH_EMBED_URL_TEMPLATE.format(model=settings.gemini_embedding_model)

    body = {
        "requests": [
            {
                "model": f"models/{settings.gemini_embedding_model}",
                "content": {"parts": [{"text": text}]},
                "taskType": EMBEDDING_TASK_TYPE,
                "outputDimensionality": OUTPUT_DIMENSIONALITY
            }
            for text in texts
        ]
    }

    response = _post_with_retry(url, settings.google_api_key, body)
    data = response.json()
    return [embedding["values"] for embedding in data["embeddings"]]
