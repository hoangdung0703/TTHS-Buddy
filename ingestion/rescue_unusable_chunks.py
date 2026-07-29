"""One-off recovery pass: re-OCRs, via local Tesseract, exactly the pages that ended up
extraction_quality "unusable" after the Gemini Vision batch (RECITATION block or other
failure) - see requirements.md Phase 3 "Tang fallback thu 2" note. Does NOT touch pages that
already succeeded, to avoid re-spending Gemini Vision cost.

Writes a separate staging file (does not overwrite chunks.json) so results can be reviewed
before deciding which recovered chunks to keep.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingestion.chunking import chunk_academic_reference, chunk_legal_text
from ingestion.config import CHUNKS_OUTPUT_PATH, RAW_DOCUMENTS_DIR
from ingestion.document_registry import get_document_config
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.pdf_extraction import PageExtraction
from ingestion.tesseract_fallback import ocr_page_with_tesseract

logger = get_logger(__name__)

RESCUE_STAGING_PATH = CHUNKS_OUTPUT_PATH.parent / "chunks_tesseract_rescue.json"

GIAO_TRINH_FILENAME = "Giáo trình Luật Tố tụng hình sự -đã nén.pdf"
TT01_FILENAME = "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf"

# Exact page numbers (1-indexed) that were RECITATION-blocked or otherwise failed during the
# Gemini Vision batch, recovered from that run's log - see the OCR summary reported after the
# original batch. Re-deriving this from chunks.json alone isn't possible since chunk
# boundaries don't carry a page reference; these lists are the authoritative record.
GIAO_TRINH_PROBLEM_PAGES: list[int] = [
    5, 12, 24, 28, 40, 41, 48, 52, 60, 61, 63, 66, 67, 68, 72, 74, 75, 76, 77, 78, 81, 84, 86,
    87, 90, 91, 93, 94, 98, 99, 100, 102, 105, 108, 109, 117, 125, 126, 127, 129, 131, 134, 138,
    140, 141, 142, 143, 144, 145, 151, 152, 156, 157, 161, 163, 166, 167, 168, 169, 171, 173,
    174, 175, 176, 177, 178, 179, 180, 181, 187, 188, 191, 192, 195, 200, 201, 204, 205, 206,
    207, 208, 209, 210, 211, 213, 214, 216, 217, 219, 220, 234, 235, 236, 237, 239, 242, 243,
    244, 245, 247, 249, 250, 254, 257, 258, 259, 261, 262, 264, 266, 271, 272, 273, 279, 282,
    285, 288, 290, 291, 293, 294, 295, 296, 297, 300, 303, 306, 307, 308, 309, 310, 311, 315,
    318, 319, 320, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 335, 337, 340, 341, 342,
    346, 347, 348, 349, 351, 356, 359, 361, 362, 363, 365, 367, 368, 371, 373, 374, 375, 378,
    379, 381, 384, 388, 389, 393, 397, 398, 400, 402, 403, 406, 415, 417, 418, 420, 433, 434,
    435, 439, 445, 446, 454, 456, 460, 461, 465, 466, 469, 470, 471, 479, 481, 482, 483, 484,
    485, 486, 487, 488, 489, 490, 491, 492, 493, 494, 495, 496, 497, 498, 499, 500, 501, 502,
    503, 504, 505, 506, 507, 508, 509, 510, 511, 512, 513, 514, 515, 516, 517, 518, 519, 520,
    521, 522, 523, 524, 525, 526, 527, 528, 529, 530, 531, 532, 533, 534, 535, 536, 537, 538,
    539, 540, 541, 542, 543, 544, 545, 546, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556,
    557, 558, 559, 560, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570, 571, 572, 573, 574,
    575, 576
]
TT01_PROBLEM_PAGES: list[int] = [37]

# Keeps rescue chunk_index values from colliding with the original paragraph-based numbering
# (0..N) so the (source_document, chunk_index) idempotent-upsert key stays unique.
RESCUE_CHUNK_INDEX_OFFSET = 100_000


def rescue_document(filename: str, problem_pages: list[int]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    config = get_document_config(filename)
    pdf_path = RAW_DOCUMENTS_DIR / filename
    new_chunks: list[dict[str, Any]] = []
    quality_counts = {"ok": 0, "degraded": 0, "unusable": 0}

    for page_number in problem_pages:
        result = ocr_page_with_tesseract(str(pdf_path), page_number)
        quality_counts[result.quality] += 1
        logger.info("%s page %d -> tesseract quality=%s (%d chars)",
                    filename, page_number, result.quality, len(result.text))

        if result.quality == "unusable":
            continue

        page = PageExtraction(page_number - 1, result.text, "tesseract_fallback", result.quality)
        if config.source_type == "legal_text":
            assert config.law_version is not None
            chunks = chunk_legal_text([page], filename, config.law_version)
        else:
            chunks = chunk_academic_reference([page], filename)

        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = RESCUE_CHUNK_INDEX_OFFSET + page_number * 100 + i
            new_chunks.append(chunk)

    return new_chunks, quality_counts


def main() -> None:
    configure_logging()

    gt_new, gt_stats = rescue_document(GIAO_TRINH_FILENAME, GIAO_TRINH_PROBLEM_PAGES)
    tt01_new, tt01_stats = rescue_document(TT01_FILENAME, TT01_PROBLEM_PAGES)

    staging = {
        "giao_trinh": {"stats": gt_stats, "chunks": gt_new},
        "tt01": {"stats": tt01_stats, "chunks": tt01_new}
    }
    RESCUE_STAGING_PATH.write_text(json.dumps(staging, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("Tesseract rescue summary (staged, chunks.json NOT modified yet)")
    print("=" * 80)
    print(f"\n{GIAO_TRINH_FILENAME} ({len(GIAO_TRINH_PROBLEM_PAGES)} problem pages):")
    print(f"  ok:       {gt_stats['ok']}")
    print(f"  degraded: {gt_stats['degraded']}")
    print(f"  unusable: {gt_stats['unusable']}")
    print(f"\n{TT01_FILENAME} ({len(TT01_PROBLEM_PAGES)} problem pages):")
    print(f"  ok:       {tt01_stats['ok']}")
    print(f"  degraded: {tt01_stats['degraded']}")
    print(f"  unusable: {tt01_stats['unusable']}")
    print(f"\nStaged results written to {RESCUE_STAGING_PATH}")


if __name__ == "__main__":
    main()
