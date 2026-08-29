"""2026-08-30 maintenance: resync the golden snapshot for the 2 documents whose raw_documents/
copy was swapped for a genuine text-layer source this round (see requirements.md ingestion log -
"Case study: scanned-copy regression blocker").

"Nghi dinh 250_ND-CP.pdf" and "Thong tu lien tich 01_2026 VKSND - BCA - BQP.pdf" had been
temporarily replaced by a textless scanned copy (0 chars/page, forcing every page through Gemini
Vision OCR and producing non-deterministic, occasionally structurally-corrupted re-parses). Both
have now been replaced by a clean text-layer copy from the official source. A content-level
comparison (whitespace-normalized diff, every key checked, zero exceptions) confirmed the new
file's parse is legally IDENTICAL to the currently-upserted golden data - the only differences
are cosmetic line-wrap position, an artifact of the new file's different pagination, not of any
wording change. Two genuine pre-existing title-truncation bugs were also found and fixed as part
of this (Dieu 30, Dieu 37 of the TTLT - see KNOWN_NON_KHOAN_TITLE_CONTINUATIONS).

This script re-parses just these 2 documents and republishes their full chunk set (chunks.json +
Qdrant) so that a byte-for-byte regression_check_legal_text.py run is clean going forward -
without this, every future regression run would show ~145 false-positive "mismatches" purely from
comparing the old file's line-wraps against the new file's, forever.

Point IDs are unaffected (deterministic by dieu_number/khoan_number, both unchanged) - this is a
same-key overwrite for every point, not an add/remove.

Usage:
    python -m ingestion.resync_source_file_swap --dry-run
    python -m ingestion.resync_source_file_swap
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Any

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.document_registry import DOCUMENT_REGISTRY
from ingestion.embedding_client import MAX_TEXTS_PER_BATCH, INTER_BATCH_DELAY_SECONDS, embed_batch
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.parse_law import parse_document
from ingestion.vector_store import chunk_to_point, create_qdrant_client, ensure_collection, upsert_points

logger = get_logger(__name__)

RESYNCED_FILENAMES = (
    "Nghị định 250_NĐ-CP.pdf",
    "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf",
)


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Parse and diff only, write/upsert nothing.")
    args = parser.parse_args()

    configs_by_name = {c.filename: c for c in DOCUMENT_REGISTRY}
    fresh_chunks: list[dict[str, Any]] = []
    for filename in RESYNCED_FILENAMES:
        chunks, stats = parse_document(configs_by_name[filename])
        fresh_chunks.extend(chunks)
        logger.info("%s -> %d chunks (%d pages needed OCR fallback)",
                    filename, len(chunks), stats.pages_needing_fallback)

    all_chunks = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    untouched = [c for c in all_chunks if c["source_document"] not in RESYNCED_FILENAMES]
    replaced_count = sum(1 for c in all_chunks if c["source_document"] in RESYNCED_FILENAMES)

    print(f"Replacing {replaced_count} old chunks with {len(fresh_chunks)} freshly-parsed chunks "
          f"for: {', '.join(RESYNCED_FILENAMES)}")
    quality_counts: dict[str, int] = {}
    for c in fresh_chunks:
        quality_counts[c["extraction_quality"]] = quality_counts.get(c["extraction_quality"], 0) + 1
    print(f"Fresh chunk extraction_quality breakdown: {quality_counts}")

    if args.dry_run:
        print("--dry-run: not writing chunks.json, not touching Qdrant.")
        return

    merged = untouched + fresh_chunks
    CHUNKS_OUTPUT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(merged)} total chunks to {CHUNKS_OUTPUT_PATH}")

    client = create_qdrant_client()
    ensure_collection(client)
    settings = get_ingestion_settings()

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
    print(f"\nEmbedded and upserted: {succeeded} | skipped (unusable): {skipped} | failed: {len(failed_chunks)}")
    if failed_chunks:
        failed_ids = [(c["source_document"], c.get("dieu_number")) for c in failed_chunks]
        print(f"  failed chunk identifiers: {failed_ids}")
    print(f"Total points now in Qdrant collection '{settings.qdrant_collection}': {collection_info.points_count}")


if __name__ == "__main__":
    main()
