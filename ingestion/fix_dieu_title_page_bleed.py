"""One-off fix for a page-number-bleed bug found in "Bộ luật TTHS.pdf" extraction (Phase 3):
6 Dieu that happen to start at the top of a PDF page got the previous page's footer page
number glued directly onto the end of the title line with no separator - the text-layer
extraction concatenates content across the page boundary without inserting one there.
Confirmed by direct inspection of chunks.json, not a hypothetical case:
  Dieu 7 ("...hình sự10"), 135 ("...hình sự66"), 233 ("...truy tố133"), 243 ("...bị can137"),
  268 ("...Tòa án144"), 382 ("...giám đốc thẩm186", affects all 5 Khoan chunks).
A chunks.json-wide scan (see requirements.md Phase 5a decision log) confirmed no other Dieu in
any of the 5 legal_text source documents has this pattern.

Fixes dieu_title and the corresponding first line of chunk_text, then re-embeds and re-upserts
only the affected points into Qdrant - point IDs are deterministic from
(source_document, law_version, dieu_number, khoan_number), which are all unchanged here, so
this overwrites the existing points in place instead of duplicating them. No full Phase 3
batch rerun needed.

Usage:
    python -m ingestion.fix_dieu_title_page_bleed
"""
from __future__ import annotations

from typing import Any

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.embedding_client import embed_batch
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.vector_store import chunk_to_point, create_qdrant_client, upsert_points
import json

logger = get_logger(__name__)

AFFECTED_SOURCE_DOCUMENT = "Bộ luật TTHS.pdf"

# dieu_number -> exact bled-in page-number suffix to strip (verified by inspection, not a
# blind trailing-digit strip, so this can't accidentally truncate a title that legitimately
# ends in a number).
PAGE_NUMBER_BLEED_SUFFIXES: dict[str, str] = {
    "7": "10",
    "135": "66",
    "233": "133",
    "243": "137",
    "268": "144",
    "382": "186",
}


def fix_chunk(chunk: dict[str, Any]) -> bool:
    if chunk["source_type"] != "legal_text" or chunk["source_document"] != AFFECTED_SOURCE_DOCUMENT:
        return False

    suffix = PAGE_NUMBER_BLEED_SUFFIXES.get(chunk["dieu_number"])
    if suffix is None:
        return False

    changed = False
    if chunk["dieu_title"] and chunk["dieu_title"].endswith(suffix):
        chunk["dieu_title"] = chunk["dieu_title"][:-len(suffix)]
        changed = True

    first_line, _, rest = chunk["chunk_text"].partition("\n")
    if first_line.endswith(suffix):
        chunk["chunk_text"] = first_line[:-len(suffix)] + "\n" + rest
        changed = True

    return changed


def main() -> None:
    configure_logging()
    chunks: list[dict[str, Any]] = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))

    fixed_chunks = [c for c in chunks if fix_chunk(c)]
    if not fixed_chunks:
        logger.warning("No chunks matched the known page-number-bleed pattern - nothing to fix")
        return

    logger.info("Fixed %d chunks: %s", len(fixed_chunks),
                [(c["dieu_number"], c["khoan_number"]) for c in fixed_chunks])

    CHUNKS_OUTPUT_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote corrected chunks.json")

    texts = [c["chunk_text"] for c in fixed_chunks]
    vectors = embed_batch(texts)
    points = [chunk_to_point(c, v) for c, v in zip(fixed_chunks, vectors)]

    client = create_qdrant_client()
    upsert_points(client, points)

    settings = get_ingestion_settings()
    collection_info = client.get_collection(settings.qdrant_collection)
    logger.info("Re-upserted %d points. Qdrant collection '%s' now has %d points total.",
                len(points), settings.qdrant_collection, collection_info.points_count)

    print("\nFixed dieu_title values:")
    for c in fixed_chunks:
        print(f"  Điều {c['dieu_number']} (Khoản {c['khoan_number']}): {c['dieu_title']!r}")


if __name__ == "__main__":
    main()
