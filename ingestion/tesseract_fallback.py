"""Second-tier OCR fallback using local Tesseract, applied only to pages that ended up
extraction_quality "unusable" after the Gemini Vision pass (RECITATION block or other
failure). Tesseract has no content/copyright policy, so it can read pages Gemini refuses -
but its Vietnamese diacritic accuracy is weaker, so results still need the same garbage
heuristic, at two thresholds, to classify ok vs degraded vs still-unusable.

This is a deliberate, targeted exception to the "no new OCR library" rule (see
requirements.md Phase 3 notes) - Tesseract is not used anywhere else in the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytesseract
from PIL import Image

from ingestion.ocr_fallback import crop_left_half_if_mirrored, render_page_image
from ingestion.text_quality import VIETNAMESE_DIACRITIC_CHARS

TESSERACT_LANG = "vie"

# Same metric as text_quality.is_text_garbage (diacritic ratio among letters), but split into
# two thresholds here since Tesseract's failure mode is graded rather than binary: below the
# lower bound the output is unreadable noise; between the two it reads but with enough
# mis-recognized diacritics to flag as "degraded"; above the upper bound it is comparable to
# clean Vietnamese prose.
UNUSABLE_DIACRITIC_RATIO = 0.05
OK_DIACRITIC_RATIO = 0.12
MIN_LENGTH_FOR_QUALITY_CHECK = 80


def _diacritic_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for char in letters if char in VIETNAMESE_DIACRITIC_CHARS) / len(letters)


@dataclass
class TesseractPageResult:
    page_number: int  # 1-indexed, matches how pages are reported elsewhere in this pipeline
    text: str
    quality: str  # "ok" | "degraded" | "unusable"


def ocr_page_with_tesseract(pdf_path: str, page_number: int) -> TesseractPageResult:
    """page_number is 1-indexed."""
    image = render_page_image(pdf_path, page_number - 1)
    image = crop_left_half_if_mirrored(image)
    text = pytesseract.image_to_string(image, lang=TESSERACT_LANG)

    stripped = text.strip()
    if len(stripped) < MIN_LENGTH_FOR_QUALITY_CHECK:
        ratio = _diacritic_ratio(stripped)
        quality = "unusable" if ratio < UNUSABLE_DIACRITIC_RATIO else "degraded"
        return TesseractPageResult(page_number, stripped, quality)

    ratio = _diacritic_ratio(stripped)
    if ratio < UNUSABLE_DIACRITIC_RATIO:
        quality = "unusable"
    elif ratio < OK_DIACRITIC_RATIO:
        quality = "degraded"
    else:
        quality = "ok"

    return TesseractPageResult(page_number, stripped, quality)
