"""One-off fix for the "next Chuong/Muc heading bleeds into the preceding Dieu's chunk_text"
bug (see requirements.md bug report, discovered via Dieu 108 BLTTHS - its chunk_text ended with
"...vu an.\nChuong VII\n58\nBIEN PHAP NGAN CHAN, BIEN PHAP CUONG CHE\nMuc I\nBIEN PHAP NGAN
CHAN"). Root cause: chunk_legal_text's body-end computation only looked at the position of the
NEXT "Dieu N." match, never at the chuong_events/muc_events _find_chuong_muc_events() already
computes for chuong_number/muc_number metadata - fixed in chunk_legal_text (see chunking.py) to
also clip body end at the earliest Chuong/Muc heading found between one Dieu and the next.
Regression-tested by ingestion/test_dieu_chuong_muc_boundary.py.

A full re-parse of all 6 legal_text documents + diff against the committed chunks.json (see
ingestion/regression_check_legal_text.py for the diffing approach) confirmed exactly 99 Dieu
change - all of them losing ONLY trailing bled heading/footnote text (fresh chunk_text is a
strict prefix of the golden chunk_text for 97/99; the remaining 2 - Dieu 454 BLTTHS and Dieu 91
BLHS - additionally stop being Khoan-split now that their body correctly drops back under
LONG_DIEU_CHAR_THRESHOLD once the bled text is removed, so their several khoan-numbered points
collapse into a single unsplit point). chuong_number/chuong_title/muc_number/muc_title metadata
is byte-identical before/after for all 99 - this fix only reshapes chunk_text/khoan_number.

Re-embeds and re-upserts only the chunks whose chunk_text actually changed (point IDs are
deterministic from source_document/law_version/dieu_number/khoan_number - unchanged dieu_number
means same-shape updates simply overwrite the existing point). For the 2 Dieu that stopped being
Khoan-split, the old per-Khoan points have no successor with the same ID and are explicitly
deleted so they don't linger as stale duplicates in Qdrant.

Usage:
    python -m ingestion.fix_chuong_muc_boundary_bleed              # writes chunks.json + Qdrant
    python -m ingestion.fix_chuong_muc_boundary_bleed --dry-run    # parses + diffs only
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.document_registry import DOCUMENT_REGISTRY
from ingestion.embedding_client import embed_batch
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.parse_law import parse_document
from ingestion.regression_check_legal_text import KNOWN_MANUAL_TESSERACT_PATCHES
from ingestion.vector_store import build_point_id, chunk_to_point, create_qdrant_client, upsert_points

logger = get_logger(__name__)


def _key(chunk: dict[str, Any]) -> tuple[str, str, str | None]:
    return (chunk["source_document"], chunk["dieu_number"], chunk["khoan_number"])


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Parse and diff only, write/upsert nothing.")
    args = parser.parse_args()

    legal_configs = [c for c in DOCUMENT_REGISTRY if c.source_type == "legal_text"]
    fresh_legal: list[dict[str, Any]] = []
    for config in legal_configs:
        chunks, stats = parse_document(config)
        fresh_legal.extend(chunks)
        logger.info("%s -> %d chunks (%d needed OCR fallback)", config.filename, len(chunks), stats.pages_needing_fallback)

    all_chunks: list[dict[str, Any]] = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    golden_legal = [c for c in all_chunks if c["source_type"] == "legal_text"]
    non_legal = [c for c in all_chunks if c["source_type"] != "legal_text"]

    golden_by_key = {_key(c): c for c in golden_legal}
    fresh_by_key = {_key(c): c for c in fresh_legal}

    # This key's golden chunk_text is a hand-spliced Tesseract OCR recovery (see
    # regression_check_legal_text.py) that a plain re-parse can never reproduce - it always
    # "differs" from a fresh parse, but that's expected and unrelated to the Chuong/Muc bleed fix
    # here. Keep the golden (Tesseract-recovered) version untouched: drop it from fresh_legal
    # before merging into chunks.json, and never treat it as changed/new/stale.
    for source_document, dieu_number, khoan_number in KNOWN_MANUAL_TESSERACT_PATCHES:
        key = (source_document, dieu_number, khoan_number)
        if key in fresh_by_key:
            fresh_legal = [c for c in fresh_legal if _key(c) != key] + [golden_by_key[key]]
            fresh_by_key[key] = golden_by_key[key]

    changed_keys = [
        k for k in (golden_by_key.keys() & fresh_by_key.keys())
        if golden_by_key[k]["chunk_text"] != fresh_by_key[k]["chunk_text"]
    ]
    new_keys = sorted(fresh_by_key.keys() - golden_by_key.keys())
    stale_keys = sorted(
        k for k in (golden_by_key.keys() - fresh_by_key.keys())
        if k not in KNOWN_MANUAL_TESSERACT_PATCHES
    )

    changed_dieu = sorted({(k[0], k[1]) for k in changed_keys} | {(k[0], k[1]) for k in new_keys})

    print(f"Golden legal_text chunks: {len(golden_legal)}   Fresh legal_text chunks: {len(fresh_legal)}")
    print(f"Chunks with changed chunk_text (same key, overwrite in place): {len(changed_keys)}")
    print(f"New keys (shape changed, e.g. no-longer-Khoan-split): {len(new_keys)} -> {new_keys}")
    print(f"Stale keys (no successor - old Khoan points to delete): {len(stale_keys)} -> {stale_keys}")
    print(f"Total distinct Dieu affected: {len(changed_dieu)}")

    if args.dry_run:
        print("\n--dry-run: not writing chunks.json, not touching Qdrant.")
        return

    merged = non_legal + fresh_legal
    CHUNKS_OUTPUT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(merged)} total chunks to {CHUNKS_OUTPUT_PATH}")

    to_embed_keys = changed_keys + new_keys
    to_embed_chunks = [fresh_by_key[k] for k in to_embed_keys]
    embeddable = [c for c in to_embed_chunks if c["extraction_quality"] != "unusable"]
    skipped = len(to_embed_chunks) - len(embeddable)

    client = create_qdrant_client()
    settings = get_ingestion_settings()

    if stale_keys:
        stale_point_ids = [build_point_id(golden_by_key[k]) for k in stale_keys]
        client.delete(collection_name=settings.qdrant_collection, points_selector=stale_point_ids)
        print(f"Deleted {len(stale_point_ids)} stale Qdrant points (old Khoan-split entries with no successor)")

    texts = [c["chunk_text"] for c in embeddable]
    vectors = embed_batch(texts)
    points = [chunk_to_point(c, v) for c, v in zip(embeddable, vectors)]
    upsert_points(client, points)

    collection_info = client.get_collection(settings.qdrant_collection)
    print(f"Re-embedded + upserted {len(points)} points ({skipped} skipped - extraction_quality=unusable).")
    print(f"Qdrant collection '{settings.qdrant_collection}' now has {collection_info.points_count} points total.")


if __name__ == "__main__":
    main()
