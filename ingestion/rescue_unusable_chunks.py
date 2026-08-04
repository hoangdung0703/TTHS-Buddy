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

TT01_FILENAME = "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf"
TOA_AN_FILENAME = "Luật tổ chức toà án nhân dân.pdf"

# Exact page numbers (1-indexed) that were RECITATION-blocked or otherwise failed during the
# Gemini Vision batch, recovered from that run's log - see the OCR summary reported after the
# original batch. Re-deriving this from chunks.json alone isn't possible since chunk
# boundaries don't carry a page reference; these lists are the authoritative record.
#
# The "Giao trinh -da nen.pdf" entry that used to live here (251 problem pages) was removed
# when that document was retired and replaced wholesale by a cleanly-extracting re-scan
# (Phase 5a/5b v2 Buoc A - see requirements.md) - its chunks (and the Qdrant points for them)
# no longer exist, so there is nothing left to rescue.
TT01_PROBLEM_PAGES: list[int] = [37]
TOA_AN_PROBLEM_PAGES: list[int] = [62]

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

    tt01_new, tt01_stats = rescue_document(TT01_FILENAME, TT01_PROBLEM_PAGES)
    toa_an_new, toa_an_stats = rescue_document(TOA_AN_FILENAME, TOA_AN_PROBLEM_PAGES)

    staging = {
        "tt01": {"stats": tt01_stats, "chunks": tt01_new},
        "toa_an": {"stats": toa_an_stats, "chunks": toa_an_new}
    }
    RESCUE_STAGING_PATH.write_text(json.dumps(staging, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("Tesseract rescue summary (staged, chunks.json NOT modified yet)")
    print("=" * 80)
    print(f"\n{TT01_FILENAME} ({len(TT01_PROBLEM_PAGES)} problem pages):")
    print(f"  ok:       {tt01_stats['ok']}")
    print(f"  degraded: {tt01_stats['degraded']}")
    print(f"  unusable: {tt01_stats['unusable']}")
    print(f"\n{TOA_AN_FILENAME} ({len(TOA_AN_PROBLEM_PAGES)} problem pages):")
    print(f"  ok:       {toa_an_stats['ok']}")
    print(f"  degraded: {toa_an_stats['degraded']}")
    print(f"  unusable: {toa_an_stats['unusable']}")
    print(f"\nStaged results written to {RESCUE_STAGING_PATH}")


if __name__ == "__main__":
    main()
