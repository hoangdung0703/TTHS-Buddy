"""CLI entry point for Phase 3 ingestion: embeds chunks.json via the Gemini embedding API
and upserts them into Qdrant with full metadata. Re-runnable: point IDs are deterministic
(see vector_store.build_point_id), so re-running after chunks.json changes overwrites the
same points instead of duplicating them.

Processes one batch (embed -> upsert) at a time rather than embedding everything before
upserting anything, so a failure partway through a large run still leaves prior batches
safely persisted in Qdrant instead of losing all progress.

Usage:
    python -m ingestion.embed_and_upsert
    python -m ingestion.embed_and_upsert --chunks-path ingestion/chunks.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from ingestion.config import CHUNKS_OUTPUT_PATH, get_ingestion_settings
from ingestion.embedding_client import INTER_BATCH_DELAY_SECONDS, MAX_TEXTS_PER_BATCH, embed_batch
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.vector_store import chunk_to_point, create_qdrant_client, ensure_collection, upsert_points

logger = get_logger(__name__)


def load_embeddable_chunks(chunks_path: Path) -> tuple[list[dict[str, Any]], int]:
    all_chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    embeddable = [chunk for chunk in all_chunks if chunk["extraction_quality"] != "unusable"]
    skipped = len(all_chunks) - len(embeddable)
    return embeddable, skipped


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Embed chunks.json and upsert into Qdrant.")
    parser.add_argument("--chunks-path", type=Path, default=CHUNKS_OUTPUT_PATH)
    args = parser.parse_args()

    chunks, skipped_unusable = load_embeddable_chunks(args.chunks_path)
    logger.info("Loaded %d embeddable chunks (%d unusable skipped) from %s",
                len(chunks), skipped_unusable, args.chunks_path)

    client = create_qdrant_client()
    ensure_collection(client)

    chunk_batches = [chunks[i:i + MAX_TEXTS_PER_BATCH] for i in range(0, len(chunks), MAX_TEXTS_PER_BATCH)]

    total_chars = sum(len(chunk["chunk_text"]) for chunk in chunks)
    succeeded = 0
    failed_chunks: list[dict[str, Any]] = []

    for batch_index, chunk_batch in enumerate(chunk_batches, start=1):
        texts = [chunk["chunk_text"] for chunk in chunk_batch]
        try:
            vectors = embed_batch(texts)
            points = [chunk_to_point(chunk, vector) for chunk, vector in zip(chunk_batch, vectors)]
            upsert_points(client, points)
            succeeded += len(points)
            logger.info("Batch %d/%d: embedded + upserted %d chunks (%d/%d total)",
                        batch_index, len(chunk_batches), len(points), succeeded, len(chunks))
        except Exception:
            logger.exception("Batch %d/%d failed - skipping these %d chunks, continuing with the rest",
                              batch_index, len(chunk_batches), len(chunk_batch))
            failed_chunks.extend(chunk_batch)

        if batch_index < len(chunk_batches):
            time.sleep(INTER_BATCH_DELAY_SECONDS)

    settings = get_ingestion_settings()
    collection_info = client.get_collection(settings.qdrant_collection)

    print("\n" + "=" * 80)
    print("Embed + upsert summary")
    print("=" * 80)
    print(f"Chunks embedded and upserted this run: {succeeded}")
    print(f"Chunks skipped (extraction_quality=unusable): {skipped_unusable}")
    print(f"Chunks that failed to embed after retries: {len(failed_chunks)}")
    if failed_chunks:
        failed_ids = [(c["source_document"], c.get("dieu_number") or c.get("chunk_index")) for c in failed_chunks]
        print(f"  failed chunk identifiers: {failed_ids[:20]}{' ...' if len(failed_ids) > 20 else ''}")
    print(f"Total characters embedded: {total_chars}")
    print(f"Total points now in Qdrant collection '{settings.qdrant_collection}': {collection_info.points_count}")
    print("Gemini embedding API does not return token usage in its response, so exact token "
          "count/cost isn't available here - check the Google AI Studio / Cloud Billing console.")


if __name__ == "__main__":
    main()
