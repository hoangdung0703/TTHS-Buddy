"""Phase 3 Extension - Buoc 3: re-parse the 4 legal_text documents confirmed (see
requirements.md) to have real Chuong/Muc structure, merge the refreshed chunks back into
ingestion/chunks.json, and push chuong_number/chuong_title/muc_number/muc_title into the
already-upserted Qdrant points via a payload-only update (no re-embedding: chunk_text for
these documents is unchanged - verified by ingestion/regression_check_legal_text.py - so the
existing vectors are still correct and re-embedding would only cost API calls for nothing).

Usage:
    python -m ingestion.reparse_chuong_muc          # updates chunks.json + Qdrant payload
    python -m ingestion.reparse_chuong_muc --dry-run  # parses + diffs only, touches nothing
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.document_registry import DOCUMENT_REGISTRY
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.parse_law import parse_document
from ingestion.vector_store import build_point_id, create_qdrant_client, ensure_collection

logger = get_logger(__name__)

# Confirmed by direct inspection of extracted text (see requirements.md Phase 3 Extension):
# these 4 legal_text documents have real Chuong headings. "Thong tu lien tich 01_2026" is
# deliberately excluded - confirmed to have NO Chuong/Muc structure at all (flat Dieu list).
TARGET_FILENAMES = (
    "Bộ luật TTHS.pdf",
    "Văn bản hợp nhất BLHS 2015.pdf",
    "Nghị định 250_NĐ-CP.pdf",
    "Thông tư liên tịch 05.pdf",
)

PAYLOAD_UPDATE_BATCH_SIZE = 100


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Parse and diff only, write/upsert nothing.")
    args = parser.parse_args()

    configs_by_name = {c.filename: c for c in DOCUMENT_REGISTRY}
    fresh_chunks: list[dict[str, Any]] = []
    for filename in TARGET_FILENAMES:
        config = configs_by_name[filename]
        chunks, stats = parse_document(config)
        fresh_chunks.extend(chunks)
        logger.info("%s -> %d chunks (%d needed OCR fallback)", filename, len(chunks), stats.pages_needing_fallback)

    all_chunks = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    untouched = [c for c in all_chunks if c["source_document"] not in TARGET_FILENAMES]
    replaced_count = len(all_chunks) - len(untouched)

    print(f"\nChunks being replaced in chunks.json: {replaced_count} -> {len(fresh_chunks)} fresh")
    with_chuong = sum(1 for c in fresh_chunks if c["chuong_number"] is not None)
    with_muc = sum(1 for c in fresh_chunks if c["muc_number"] is not None)
    print(f"Fresh chunks with chuong_number set: {with_chuong}/{len(fresh_chunks)}")
    print(f"Fresh chunks with muc_number set: {with_muc}/{len(fresh_chunks)}")

    if args.dry_run:
        print("\n--dry-run: not writing chunks.json, not touching Qdrant.")
        return

    merged = untouched + fresh_chunks
    CHUNKS_OUTPUT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(merged)} total chunks to {CHUNKS_OUTPUT_PATH}")

    client = create_qdrant_client()
    ensure_collection(client)  # (re)creates payload indexes, including the new chuong_number one
    collection = get_ingestion_settings().qdrant_collection

    embeddable = [c for c in fresh_chunks if c["extraction_quality"] != "unusable"]
    skipped = len(fresh_chunks) - len(embeddable)
    updated = 0
    for start in range(0, len(embeddable), PAYLOAD_UPDATE_BATCH_SIZE):
        batch = embeddable[start:start + PAYLOAD_UPDATE_BATCH_SIZE]
        point_ids = [build_point_id(c) for c in batch]
        # One set_payload call per chunk since each has a different chuong/muc value - Qdrant's
        # set_payload applies the same payload dict to every point in `points`, so a single
        # batched call can't be used here without grouping by identical (chuong, muc) value first,
        # which isn't worth the complexity for a one-off metadata backfill of ~1300 chunks.
        for point_id, chunk in zip(point_ids, batch):
            client.set_payload(
                collection_name=collection,
                payload={
                    "chuong_number": chunk["chuong_number"],
                    "chuong_title": chunk["chuong_title"],
                    "muc_number": chunk["muc_number"],
                    "muc_title": chunk["muc_title"],
                },
                points=[point_id]
            )
        updated += len(batch)
        logger.info("Payload-updated %d/%d points", updated, len(embeddable))

    print(f"\nUpdated Chuong/Muc payload on {updated} Qdrant points "
          f"({skipped} skipped - extraction_quality=unusable, never embedded in the first place).")
    print("No re-embedding performed - chunk_text for these documents is unchanged, "
          "existing vectors remain valid.")


if __name__ == "__main__":
    main()
