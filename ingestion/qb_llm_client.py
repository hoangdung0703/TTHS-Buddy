"""Minimal Gemini generateContent REST client for text-only prompts, used by
parse_question_bank.py to normalize essay key-point bullets. Same REST-not-SDK pattern and
retry logic as ocr_fallback.py / embedding_client.py, kept as its own module since it's a plain
text prompt (no image payload) unlike ocr_fallback.py's vision call.
"""
from __future__ import annotations

import time

import httpx

from ingestion.config import get_ingestion_settings
from ingestion.logging_utils import get_logger

logger = get_logger(__name__)

GENERATE_CONTENT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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
            logger.warning("Gemini generateContent request failed (attempt %d/%d): %s",
                            attempt, MAX_TRANSIENT_RETRIES, error)
            if attempt < MAX_TRANSIENT_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    assert last_error is not None
    raise last_error


def generate_text(system_prompt: str, user_prompt: str) -> str:
    settings = get_ingestion_settings()
    url = GENERATE_CONTENT_URL_TEMPLATE.format(model=settings.gemini_chat_model)
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.0}
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
