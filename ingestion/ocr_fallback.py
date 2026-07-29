"""Gemini Vision OCR fallback for PDF pages where text-layer extraction failed or is
garbage (scanned-image pages, or broken font CMaps). Uses the REST API directly per
requirements.md tech stack (embeddings/chat both go through REST, not the SDK) - reuses
GOOGLE_API_KEY / GEMINI_CHAT_MODEL already required for Phase 4, no new dependency added.
"""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass

import httpx
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from ingestion.config import get_ingestion_settings
from ingestion.logging_utils import get_logger

logger = get_logger(__name__)

GEMINI_GENERATE_CONTENT_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

OCR_PROMPT = (
    "You are an OCR engine. Read the Vietnamese legal/academic text visible in this scanned "
    "document image and output it verbatim as plain text, preserving paragraph breaks. "
    "This is for a private research corpus, not for redistribution. Output only the "
    "transcribed text."
)

RENDER_SCALE = 2.0
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_TRANSIENT_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5.0

# Pearson correlation between the left/right halves (downsampled grayscale) above this is
# treated as a "2-up" print layout where both halves repeat the same content - see
# requirements.md Phase 3 notes. Mean-abs-diff alone was tried first but produces false
# positives on sparse/mostly-blank pages (e.g. a near-empty single-column signature page
# scored as "similar" purely because both halves are mostly white). Correlation is far more
# discriminative: real mirrored pages measured 0.59-0.67, genuinely distinct pages (both
# sparse and dense) measured 0.20-0.22.
MIRROR_CORRELATION_THRESHOLD = 0.45


@dataclass
class OcrResult:
    text: str | None
    finish_reason: str | None
    prompt_token_count: int
    candidates_token_count: int


def render_page_image(pdf_path: str, page_index: int, scale: float = RENDER_SCALE) -> Image.Image:
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        return bitmap.to_pil()
    finally:
        pdf.close()


def crop_left_half_if_mirrored(image: Image.Image) -> Image.Image:
    width, height = image.size
    left = image.crop((0, 0, width // 2, height))
    right = image.crop((width // 2, 0, width, height))

    left_arr = np.asarray(left.resize((150, 150)).convert("L"), dtype=np.float32).flatten()
    right_arr = np.asarray(right.resize((150, 150)).convert("L"), dtype=np.float32).flatten()

    if left_arr.std() == 0 or right_arr.std() == 0:
        return image

    correlation = float(np.corrcoef(left_arr, right_arr)[0, 1])
    if correlation > MIRROR_CORRELATION_THRESHOLD:
        return left
    return image


def _post_with_retry(url: str, api_key: str, body: dict) -> httpx.Response:
    """Retries transient network/5xx failures with backoff. Does not retry 4xx (including
    the RECITATION-carrying 200 responses, which are handled separately by the caller)."""
    last_error: Exception | None = None
    for attempt in range(1, MAX_TRANSIENT_RETRIES + 1):
        try:
            response = httpx.post(url, params={"key": api_key}, json=body, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code >= 500:
                raise httpx.HTTPStatusError("Server error", request=response.request, response=response)
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            last_error = error
            logger.warning("Gemini Vision request failed (attempt %d/%d): %s",
                            attempt, MAX_TRANSIENT_RETRIES, error)
            if attempt < MAX_TRANSIENT_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    assert last_error is not None
    raise last_error


def ocr_image_via_gemini(image: Image.Image) -> OcrResult:
    settings = get_ingestion_settings()
    url = GEMINI_GENERATE_CONTENT_URL_TEMPLATE.format(model=settings.gemini_chat_model)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    body = {
        "contents": [
            {
                "parts": [
                    {"text": OCR_PROMPT},
                    {"inline_data": {"mime_type": "image/png", "data": image_b64}}
                ]
            }
        ],
        "generationConfig": {"temperature": 0.0}
    }

    response = _post_with_retry(url, settings.google_api_key, body)
    data = response.json()

    usage = data.get("usageMetadata", {})
    prompt_tokens = usage.get("promptTokenCount", 0)
    candidates_tokens = usage.get("candidatesTokenCount", 0)

    candidates = data.get("candidates", [])
    if not candidates:
        return OcrResult(text=None, finish_reason="NO_CANDIDATES", prompt_token_count=prompt_tokens,
                          candidates_token_count=candidates_tokens)

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    parts = candidate.get("content", {}).get("parts", [])

    if not parts:
        # RECITATION (or another hard content block) - Gemini's safety filter refuses to
        # reproduce text that matches indexed/published sources verbatim. Per requirements.md
        # decision: do not retry with different prompts/temperature, this is a hard block.
        return OcrResult(text=None, finish_reason=finish_reason, prompt_token_count=prompt_tokens,
                          candidates_token_count=candidates_tokens)

    return OcrResult(text=parts[0].get("text", ""), finish_reason=finish_reason,
                      prompt_token_count=prompt_tokens, candidates_token_count=candidates_tokens)


def ocr_page_with_fallback(pdf_path: str, page_index: int) -> OcrResult:
    image = render_page_image(pdf_path, page_index)
    image = crop_left_half_if_mirrored(image)
    return ocr_image_via_gemini(image)
