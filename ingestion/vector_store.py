"""Qdrant adapter for ingestion: collection setup and idempotent point upserts.

Point IDs are deterministic UUIDs derived from each chunk's natural key (Qdrant point IDs
must be an unsigned int or a UUID, not an arbitrary string). Re-running ingestion on updated
source documents therefore overwrites the same points instead of duplicating them - per
requirements.md: idempotent by dieu_number + law_version for legal_text, by
source_document + chunk_index for academic_reference.
"""
from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from ingestion.config import get_ingestion_settings
from ingestion.logging_utils import get_logger

logger = get_logger(__name__)

VECTOR_SIZE = 768  # must match embedding_client.OUTPUT_DIMENSIONALITY and backend/app/core/config.py
POINT_ID_NAMESPACE = uuid.UUID("c9f1c1c0-2b8a-4a3e-9b1e-1f6f6a2c5d40")
UPSERT_BATCH_SIZE = 100

# Every payload field the backend filters on (rag_service.py) needs a keyword index, or Qdrant
# rejects the filtered query with a 400 - discovered incrementally as each new filter was added
# (source_type/dieu_number in Phase 4, source_document in Phase 6), so collected here and
# (re)created on every ensure_collection call rather than left as one-off manual commands.
FILTERABLE_PAYLOAD_FIELDS = ("source_type", "dieu_number", "source_document")


def create_qdrant_client() -> QdrantClient:
    settings = get_ingestion_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, check_compatibility=False)


def _ensure_payload_indexes(client: QdrantClient, collection: str) -> None:
    for field_name in FILTERABLE_PAYLOAD_FIELDS:
        client.create_payload_index(collection, field_name=field_name, field_schema=PayloadSchemaType.KEYWORD)


def ensure_collection(client: QdrantClient) -> None:
    settings = get_ingestion_settings()
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        )
        logger.info("Created Qdrant collection %s", settings.qdrant_collection)

    _ensure_payload_indexes(client, settings.qdrant_collection)


def build_point_id(chunk: dict[str, Any]) -> str:
    if chunk["source_type"] == "legal_text":
        natural_key = "|".join([
            "legal_text", chunk["source_document"], str(chunk["law_version"]),
            str(chunk["dieu_number"]), str(chunk["khoan_number"])
        ])
    else:
        natural_key = "|".join(["academic_reference", chunk["source_document"], str(chunk["chunk_index"])])

    return str(uuid.uuid5(POINT_ID_NAMESPACE, natural_key))


def chunk_to_point(chunk: dict[str, Any], vector: list[float]) -> PointStruct:
    payload = {
        "source_type": chunk["source_type"],
        "source_document": chunk["source_document"],
        "law_version": chunk["law_version"],
        "dieu_number": chunk["dieu_number"],
        "dieu_title": chunk["dieu_title"],
        "khoan_number": chunk["khoan_number"],
        "chunk_index": chunk["chunk_index"],
        "section_heading": chunk["section_heading"],
        "chunk_text": chunk["chunk_text"],
        "extraction_method": chunk["extraction_method"],
        "extraction_quality": chunk["extraction_quality"]
    }
    return PointStruct(id=build_point_id(chunk), vector=vector, payload=payload)


def upsert_points(client: QdrantClient, points: list[PointStruct]) -> None:
    settings = get_ingestion_settings()
    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        batch = points[start:start + UPSERT_BATCH_SIZE]
        client.upsert(collection_name=settings.qdrant_collection, points=batch)
        logger.info("Upserted %d/%d points", min(start + UPSERT_BATCH_SIZE, len(points)), len(points))
