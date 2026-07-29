"""CLI entry point for Phase 3 ingestion parsing.

Usage:
    python -m ingestion.parse_law --file "Bo luat TTHS.pdf"          # single-file test mode
    python -m ingestion.parse_law --all                              # full batch, all 12 files
    python -m ingestion.parse_law --all --output ingestion/chunks.json

Dispatches each document to the legal_text or academic_reference chunking strategy based
on ingestion/document_registry.py, running the OCR fallback pipeline (pdf_extraction.py)
per page as needed. Writes one unified JSON array regardless of source_type.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ingestion.chunking import chunk_academic_reference, chunk_legal_text
from ingestion.config import CHUNKS_OUTPUT_PATH, RAW_DOCUMENTS_DIR
from ingestion.document_registry import DOCUMENT_REGISTRY, DocumentConfig
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.pdf_extraction import OcrStats, extract_pages

logger = get_logger(__name__)


def parse_document(config: DocumentConfig) -> tuple[list[dict[str, Any]], OcrStats]:
    pdf_path = RAW_DOCUMENTS_DIR / config.filename
    if not pdf_path.exists():
        raise FileNotFoundError(f"Raw document not found: {pdf_path}")

    stats = OcrStats()
    column_aware = config.source_type == "academic_reference"
    pages = extract_pages(str(pdf_path), config.filename, column_aware, stats)

    if config.source_type == "legal_text":
        assert config.law_version is not None
        chunks = chunk_legal_text(pages, config.filename, config.law_version)
    else:
        chunks = chunk_academic_reference(pages, config.filename)

    return chunks, stats


def print_stats_summary(per_file_stats: list[tuple[str, OcrStats]]) -> None:
    total = OcrStats()
    print("\n" + "=" * 80)
    print("OCR fallback summary")
    print("=" * 80)
    for filename, stats in per_file_stats:
        if stats.pages_needing_fallback == 0:
            continue
        print(f"\n{filename}")
        print(f"  pages needing fallback: {stats.pages_needing_fallback}")
        print(f"  OCR success:            {stats.ocr_success}")
        print(f"  RECITATION blocked:     {stats.recitation_blocked}")
        print(f"  other OCR failure:      {stats.other_ocr_failure}")
        if stats.blocked_pages:
            page_numbers = ", ".join(str(p) for _, p in stats.blocked_pages)
            print(f"  blocked page numbers:   {page_numbers}")

        total.pages_needing_fallback += stats.pages_needing_fallback
        total.ocr_success += stats.ocr_success
        total.recitation_blocked += stats.recitation_blocked
        total.other_ocr_failure += stats.other_ocr_failure
        total.total_prompt_tokens += stats.total_prompt_tokens
        total.total_candidates_tokens += stats.total_candidates_tokens

    print("\n" + "-" * 80)
    print(f"TOTAL pages needing fallback: {total.pages_needing_fallback}")
    print(f"TOTAL OCR success:            {total.ocr_success}")
    print(f"TOTAL RECITATION blocked:     {total.recitation_blocked}")
    print(f"TOTAL other OCR failure:      {total.other_ocr_failure}")
    print(f"TOTAL Gemini Vision tokens:   {total.total_prompt_tokens + total.total_candidates_tokens} "
          f"(prompt={total.total_prompt_tokens}, output={total.total_candidates_tokens})")
    print("Check the Google AI Studio / Cloud Billing console for the exact dollar cost - "
          "per-token pricing is not hardcoded here since it can change.")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Parse raw law/academic PDFs into RAG chunks.")
    parser.add_argument("--file", action="append", help="Process a single file by name (repeatable).")
    parser.add_argument("--all", action="store_true", help="Process all files in document_registry.py.")
    parser.add_argument("--output", type=Path, default=CHUNKS_OUTPUT_PATH, help="Output JSON path.")
    args = parser.parse_args()

    if not args.file and not args.all:
        parser.error("Specify --file <name> (repeatable) or --all")

    if args.all:
        configs = DOCUMENT_REGISTRY
    else:
        by_name = {c.filename: c for c in DOCUMENT_REGISTRY}
        configs = []
        for name in args.file:
            if name not in by_name:
                logger.error("Unknown file (not in document_registry.py): %s", name)
                sys.exit(1)
            configs.append(by_name[name])

    all_chunks: list[dict[str, Any]] = []
    per_file_stats: list[tuple[str, OcrStats]] = []

    for config in configs:
        logger.info("Processing %s (source_type=%s)", config.filename, config.source_type)
        chunks, stats = parse_document(config)
        logger.info("%s -> %d chunks", config.filename, len(chunks))
        all_chunks.extend(chunks)
        per_file_stats.append((config.filename, stats))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %d chunks total to %s", len(all_chunks), args.output)

    print_stats_summary(per_file_stats)


if __name__ == "__main__":
    main()
