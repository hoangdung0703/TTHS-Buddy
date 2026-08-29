"""2026-08-29 batch: ingest the 10 genuinely-new legal_text documents supplied this round (12
raw PDFs total - 1 confirmed duplicate of the already-ingested TTLT 01/2026, 1 candidate
replacement for "Bo luat TTHS.pdf" held back pending a separate content-diff review, see
requirements.md ingestion log for the full accounting).

Follows the same merge-into-chunks.json pattern as ingest_batch2.py: only the 10 new documents
are parsed (no OCR/API cost wasted re-parsing the untouched existing documents), their fresh
chunks replace/extend chunks.json, and only those fresh chunks are embedded and upserted -
everything else in Qdrant is left untouched.

Usage:
    python -m ingestion.ingest_batch3 --dry-run   # parse + report only, touches nothing
    python -m ingestion.ingest_batch3             # writes chunks.json + Qdrant
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Any

from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.document_registry import DOCUMENT_REGISTRY
from ingestion.embedding_client import MAX_TEXTS_PER_BATCH, INTER_BATCH_DELAY_SECONDS, embed_batch
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.parse_law import parse_document
from ingestion.vector_store import chunk_to_point, create_qdrant_client, ensure_collection, upsert_points

logger = get_logger(__name__)

NEW_FILENAMES = (
    "Quyết định 06_QĐ-VKSTC.pdf",
    "Nghị quyết 05_2017_NQ-HĐTP.pdf",
    "Quyết định 505_QĐ-VKSTC.pdf",
    "Thông tư liên tịch 04_2025 BCA - VKSNDTC - TANDTC.pdf",
    "Thông tư liên tịch 02_2017 VKSNDTC - TANDTC - BCA - BQP.pdf",
    "Thông tư 02_2018_TT-TANDTC.pdf",
    "Thông tư liên tịch 03_2018 BCA - VKSNDTC - TANDTC - BQP.pdf",
    "Thông tư liên tịch 08_2025 VKSNDTC - TANDTC - BCA - BTP - BYT.pdf",
    "Thông tư liên tịch 02_2018 BCA - VKSNDTC - TANDTC - BQP.pdf",
    "Thông tư liên tịch 29_2025 BTP - BCA - BQP - BTC - TANDTC - VKSNDTC.pdf",
)


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Parse and diff only, write/upsert nothing.")
    args = parser.parse_args()

    configs_by_name = {c.filename: c for c in DOCUMENT_REGISTRY}
    fresh_chunks: list[dict[str, Any]] = []
    per_file_counts: list[tuple[str, int, int]] = []  # filename, chunk_count, ocr_fallback_pages

    for filename in NEW_FILENAMES:
        config = configs_by_name[filename]
        chunks, stats = parse_document(config)
        fresh_chunks.extend(chunks)
        per_file_counts.append((filename, len(chunks), stats.pages_needing_fallback))
        logger.info("%s -> %d chunks (%d pages needed OCR fallback)",
                    filename, len(chunks), stats.pages_needing_fallback)

    all_chunks = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    untouched = [c for c in all_chunks if c["source_document"] not in NEW_FILENAMES]
    already_present_count = sum(1 for c in all_chunks if c["source_document"] in NEW_FILENAMES)

    print("\n" + "=" * 80)
    print("Parse summary")
    print("=" * 80)
    for filename, count, ocr_pages in per_file_counts:
        print(f"  {filename}: {count} chunks ({ocr_pages} pages needed OCR fallback)")
    if already_present_count:
        print(f"NOTE: {already_present_count} pre-existing chunks for the new filenames were found "
              f"in chunks.json and will be replaced (re-run idempotency).")
    print(f"\nchunks.json: {len(all_chunks)} -> {len(untouched) + len(fresh_chunks)} total "
          f"({len(untouched)} untouched + {len(fresh_chunks)} fresh)")

    quality_counts: dict[str, int] = {}
    for c in fresh_chunks:
        quality_counts[c["extraction_quality"]] = quality_counts.get(c["extraction_quality"], 0) + 1
    print(f"\nFresh chunk extraction_quality breakdown: {quality_counts}")

    if args.dry_run:
        print("\n--dry-run: not writing chunks.json, not touching Qdrant.")
        return

    merged = untouched + fresh_chunks
    CHUNKS_OUTPUT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(merged)} total chunks to {CHUNKS_OUTPUT_PATH}")

    client = create_qdrant_client()
    ensure_collection(client)
    settings = get_ingestion_settings()

    # Clear any points for the new filenames first, in case this is a re-run after a partial
    # failure - upsert alone would overwrite same-content points (deterministic IDs) but
    # wouldn't remove points for chunks that no longer exist after a chunking-logic change.
    for filename in NEW_FILENAMES:
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="source_document", match=MatchValue(value=filename))])
            )
        )

    embeddable = [c for c in fresh_chunks if c["extraction_quality"] != "unusable"]
    skipped = len(fresh_chunks) - len(embeddable)

    succeeded = 0
    failed_chunks: list[dict[str, Any]] = []
    batches = [embeddable[i:i + MAX_TEXTS_PER_BATCH] for i in range(0, len(embeddable), MAX_TEXTS_PER_BATCH)]
    for batch_index, batch in enumerate(batches, start=1):
        texts = [c["chunk_text"] for c in batch]
        try:
            vectors = embed_batch(texts)
            points = [chunk_to_point(c, v) for c, v in zip(batch, vectors)]
            upsert_points(client, points)
            succeeded += len(points)
            logger.info("Batch %d/%d: embedded + upserted %d chunks (%d/%d total)",
                        batch_index, len(batches), len(points), succeeded, len(embeddable))
        except Exception:
            logger.exception("Batch %d/%d failed - skipping these %d chunks", batch_index, len(batches), len(batch))
            failed_chunks.extend(batch)
        if batch_index < len(batches):
            time.sleep(INTER_BATCH_DELAY_SECONDS)

    collection_info = client.get_collection(settings.qdrant_collection)
    print("\n" + "=" * 80)
    print("Embed + upsert summary")
    print("=" * 80)
    print(f"Fresh chunks embedded and upserted: {succeeded}")
    print(f"Fresh chunks skipped (extraction_quality=unusable): {skipped}")
    print(f"Fresh chunks that failed to embed: {len(failed_chunks)}")
    if failed_chunks:
        failed_ids = [(c["source_document"], c.get("dieu_number") or c.get("chunk_index")) for c in failed_chunks]
        print(f"  failed chunk identifiers: {failed_ids}")
    print(f"Total points now in Qdrant collection '{settings.qdrant_collection}': {collection_info.points_count}")


if __name__ == "__main__":
    main()
