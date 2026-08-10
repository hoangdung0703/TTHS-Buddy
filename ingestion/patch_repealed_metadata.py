"""One-off backfill: pushes is_repealed/has_repealed_clause metadata (already written into
ingestion/chunks.json by the mục C audit) onto the matching, already-embedded Qdrant points via
set_payload - no re-embedding needed since chunk_text is unchanged, only new metadata fields are
added. Safe to re-run (idempotent: same point IDs, same payload values every time).

Usage:
    python -m ingestion.patch_repealed_metadata
"""
from __future__ import annotations

import json

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.vector_store import FILTERABLE_BOOL_PAYLOAD_FIELDS, build_point_id, create_qdrant_client
from qdrant_client.models import PayloadSchemaType

logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    settings = get_ingestion_settings()
    client = create_qdrant_client()

    for field_name in FILTERABLE_BOOL_PAYLOAD_FIELDS:
        client.create_payload_index(settings.qdrant_collection, field_name=field_name,
                                     field_schema=PayloadSchemaType.BOOL)

    chunks = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    patched = 0
    for chunk in chunks:
        if not (chunk.get("is_repealed") or chunk.get("has_repealed_clause")):
            continue
        payload = {
            "is_repealed": chunk.get("is_repealed", False),
            "repealed_note": chunk.get("repealed_note"),
            "has_repealed_clause": chunk.get("has_repealed_clause", False),
            "repealed_clause_note": chunk.get("repealed_clause_note"),
        }
        client.set_payload(collection_name=settings.qdrant_collection, payload=payload,
                            points=[build_point_id(chunk)])
        logger.info("Patched %s Dieu %s: %s", chunk["source_document"], chunk.get("dieu_number"), payload)
        patched += 1

    print(f"Patched {patched} Qdrant points with repealed metadata.")


if __name__ == "__main__":
    main()
