"""Per-page PDF text extraction: text-layer first, OCR fallback (via ocr_fallback.py)
when the text-layer is empty or garbage. Also provides column-aware text-layer extraction
for academic_reference PDFs that use a 2-column journal layout, so reading order does not
get interleaved between columns.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pdfplumber

from ingestion.logging_utils import get_logger
from ingestion.ocr_fallback import ocr_page_with_fallback
from ingestion.text_quality import is_text_garbage

logger = get_logger(__name__)

LINE_BUCKET_POINTS = 3

# Plain PDF text extraction has no blank lines between paragraphs (that's a visual gap, not
# a text element) - so paragraph boundaries have to be inferred from the first-line indent
# that Vietnamese legal/academic documents conventionally use ("thut dau dong"). A line whose
# first word starts this much further right than the column's flush-left margin is treated
# as the start of a new paragraph, and a blank line is inserted before it.
PARAGRAPH_INDENT_THRESHOLD_POINTS = 8


@dataclass
class PageExtraction:
    page_index: int
    text: str
    extraction_method: str  # "text_layer" | "ocr_fallback" | "text_layer_fallback_after_ocr_blocked"
    extraction_quality: str  # "ok" | "degraded" | "unusable"


@dataclass
class OcrStats:
    pages_needing_fallback: int = 0
    ocr_success: int = 0
    recitation_blocked: int = 0
    other_ocr_failure: int = 0
    total_prompt_tokens: int = 0
    total_candidates_tokens: int = 0
    blocked_pages: list[tuple[str, int]] = field(default_factory=list)


def _group_into_lines(words: list[dict]) -> list[list[dict]]:
    buckets: dict[int, list[dict]] = {}
    for word in words:
        bucket = round(word["top"] / LINE_BUCKET_POINTS)
        buckets.setdefault(bucket, []).append(word)
    return [sorted(buckets[bucket], key=lambda w: w["x0"]) for bucket in sorted(buckets.keys())]


def _lines_to_paragraph_text(lines: list[list[dict]]) -> str:
    """Joins pre-grouped lines into text, inserting a blank line wherever the first-line-indent
    heuristic detects a new paragraph (plain PDF extraction has no blank lines to begin with -
    that's a visual gap, not a text element - so indentation is the only usable signal)."""
    if not lines:
        return ""

    line_infos = [(line[0]["x0"], " ".join(w["text"] for w in line)) for line in lines]
    margin_x0 = min(x0 for x0, _ in line_infos)

    output_lines: list[str] = []
    for i, (x0, text) in enumerate(line_infos):
        if i > 0 and (x0 - margin_x0) > PARAGRAPH_INDENT_THRESHOLD_POINTS:
            output_lines.append("")
        output_lines.append(text)

    return "\n".join(output_lines)


MIDPOINT_MARGIN_POINTS = 10
MIN_LINES_PER_COLUMN = 5

# In a justified 2-column layout, rows are often vertically aligned across the gutter, so a
# single top-position bucket can contain words from BOTH columns' lines at once - that looks
# identical to one genuine full-width line unless the gap between them is examined. A real
# inter-word gap is a few points; the empty gutter between columns is much wider.
MIN_COLUMN_GUTTER_GAP_POINTS = 15


def _split_line_at_column_gutter(line: list[dict], mid_x: float) -> list[list[dict]]:
    """If a line-bucket's words have an unusually wide gap that straddles the page midpoint,
    it is really two column lines that happen to sit at the same height - split there. A
    genuinely continuous full-width line (title, centered heading) has normal word spacing
    all the way across and is returned unchanged."""
    if len(line) < 2:
        return [line]

    best_gap = 0.0
    best_index = -1
    for i in range(len(line) - 1):
        gap = line[i + 1]["x0"] - line[i]["x1"]
        gap_crosses_mid = line[i]["x1"] < mid_x + MIDPOINT_MARGIN_POINTS and line[i + 1]["x0"] > mid_x - MIDPOINT_MARGIN_POINTS
        if gap > best_gap and gap_crosses_mid:
            best_gap = gap
            best_index = i

    if best_index == -1 or best_gap < MIN_COLUMN_GUTTER_GAP_POINTS:
        return [line]

    return [line[:best_index + 1], line[best_index + 1:]]


def extract_text_column_aware(page: "pdfplumber.page.Page") -> str:
    """Reconstructs page text word-by-word (rather than pdfplumber's default extract_text) so
    paragraph breaks can be inferred from indentation. Classifies each LINE independently as
    full-width (title/abstract/footer - common above/below a 2-column body) or column-confined,
    since academic papers routinely mix both regions on the same page: an earlier version that
    made one split-or-not decision for the whole page cut full-width lines in half and
    reassembled the halves far apart. Full-width lines are emitted in place; a contiguous run
    of column-confined lines is read left-column-in-full then right-column, instead of
    pdfplumber's default top-to-bottom order which interleaves the two columns mid-sentence."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return page.extract_text() or ""

    mid_x = page.width / 2
    raw_lines = _group_into_lines(words)
    lines = [split_line for line in raw_lines for split_line in _split_line_at_column_gutter(line, mid_x)]

    segments: list[str] = []
    left_run: list[list[dict]] = []
    right_run: list[list[dict]] = []

    def flush_column_run() -> None:
        if len(left_run) < MIN_LINES_PER_COLUMN or len(right_run) < MIN_LINES_PER_COLUMN:
            # Not enough of a run to be a real column - treat as ordinary top-to-bottom lines.
            combined = sorted(left_run + right_run, key=lambda line: line[0]["top"])
            segments.append(_lines_to_paragraph_text(combined))
        else:
            segments.append(_lines_to_paragraph_text(left_run) + "\n\n" + _lines_to_paragraph_text(right_run))
        left_run.clear()
        right_run.clear()

    for line in lines:
        min_x0 = min(w["x0"] for w in line)
        max_x1 = max(w["x1"] for w in line)
        spans_midpoint = min_x0 < mid_x - MIDPOINT_MARGIN_POINTS and max_x1 > mid_x + MIDPOINT_MARGIN_POINTS

        if spans_midpoint:
            if left_run or right_run:
                flush_column_run()
            segments.append(_lines_to_paragraph_text([line]))
            continue

        is_left = max_x1 <= mid_x + MIDPOINT_MARGIN_POINTS
        (left_run if is_left else right_run).append(line)

    if left_run or right_run:
        flush_column_run()

    return "\n\n".join(segment for segment in segments if segment)


def _resolve_page_with_ocr_fallback(
    pdf_path: str, page_index: int, raw_text: str, source_document: str, stats: OcrStats
) -> PageExtraction:
    stats.pages_needing_fallback += 1
    logger.warning(
        "Text-layer extraction failed/garbage for %s page %d - trying OCR fallback",
        source_document, page_index + 1
    )

    try:
        result = ocr_page_with_fallback(pdf_path, page_index)
    except Exception:
        logger.exception("OCR fallback raised an unexpected error for %s page %d - falling back to text-layer",
                          source_document, page_index + 1)
        stats.other_ocr_failure += 1
        quality = "unusable" if is_text_garbage(raw_text) else "degraded"
        return PageExtraction(page_index, raw_text, "text_layer_fallback_after_ocr_blocked", quality)

    stats.total_prompt_tokens += result.prompt_token_count
    stats.total_candidates_tokens += result.candidates_token_count

    if result.finish_reason == "STOP" and result.text is not None and not is_text_garbage(result.text):
        stats.ocr_success += 1
        return PageExtraction(page_index, result.text, "ocr_fallback", "ok")

    if result.finish_reason == "RECITATION":
        stats.recitation_blocked += 1
        stats.blocked_pages.append((source_document, page_index + 1))
        logger.warning("OCR blocked by RECITATION filter for %s page %d - falling back to text-layer",
                        source_document, page_index + 1)
    else:
        stats.other_ocr_failure += 1
        logger.warning("OCR fallback failed (finish_reason=%s) for %s page %d - falling back to text-layer",
                        result.finish_reason, source_document, page_index + 1)

    quality = "unusable" if is_text_garbage(raw_text) else "degraded"
    return PageExtraction(page_index, raw_text, "text_layer_fallback_after_ocr_blocked", quality)


def extract_pages(pdf_path: str, source_document: str, column_aware: bool, stats: OcrStats) -> list[PageExtraction]:
    pages: list[PageExtraction] = []

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page_index in range(page_count):
            page = pdf.pages[page_index]
            raw_text = (extract_text_column_aware(page) if column_aware else page.extract_text()) or ""

            if is_text_garbage(raw_text):
                pages.append(_resolve_page_with_ocr_fallback(pdf_path, page_index, raw_text, source_document, stats))
            else:
                pages.append(PageExtraction(page_index, raw_text, "text_layer", "ok"))

    logger.info("Extracted %d pages from %s (%d needed OCR fallback)",
                page_count, source_document, stats.pages_needing_fallback)
    return pages
