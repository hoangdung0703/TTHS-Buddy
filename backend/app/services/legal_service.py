"""Full-text lookup for one Dieu, for the citation-pill "read full article" feature (see
requirements.md "Feature nhỏ - Xem toàn văn Điều luật từ citation pill").
"""
from __future__ import annotations

import re
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

_KHOAN_SORT_PATTERN = re.compile(r"(\d+)([a-z]*)")


def _khoan_sort_key(khoan_number: str | None) -> tuple[int, int, str]:
    """None sorts first (the intro paragraph of a Khoan-split Dieu, or the whole body of a
    single-chunk Dieu - either way it belongs before any numbered Khoan)."""
    if khoan_number is None:
        return (0, 0, "")
    match = _KHOAN_SORT_PATTERN.match(khoan_number)
    if not match:
        return (1, 0, khoan_number)
    return (1, int(match.group(1)), match.group(2))


def _assemble_full_text(dieu_number: str, dieu_title: str | None, chunks: list[dict[str, Any]]) -> str:
    """Each Khoan-split chunk's chunk_text repeats the "Dieu X. Title" header line (see
    ingestion/chunking.py _split_dieu_into_khoan) - strip that duplicate prefix from every
    segment after the first so the reassembled article reads as one continuous text instead of
    repeating its own title once per Khoan."""
    header_line = f"Điều {dieu_number}. {dieu_title}" if dieu_title else f"Điều {dieu_number}."

    if len(chunks) == 1:
        return chunks[0]["chunk_text"]

    bodies: list[str] = []
    for chunk in chunks:
        text = chunk["chunk_text"]
        if text.startswith(header_line):
            text = text[len(header_line):].lstrip("\n")
        bodies.append(text)

    return header_line + "\n\n" + "\n\n".join(bodies)


def get_dieu_full_text(client: QdrantClient, collection: str, dieu_number: str,
                        law_version: str) -> dict[str, Any] | None:
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
            FieldCondition(key="dieu_number", match=MatchValue(value=dieu_number)),
            FieldCondition(key="law_version", match=MatchValue(value=law_version)),
        ]),
        limit=20,
        with_payload=True,
    )
    if not points:
        return None

    chunks = sorted((p.payload for p in points), key=lambda payload: _khoan_sort_key(payload.get("khoan_number")))
    dieu_title = chunks[0].get("dieu_title")
    full_text = _assemble_full_text(dieu_number, dieu_title, chunks)

    return {
        "dieu_number": dieu_number,
        "dieu_title": dieu_title,
        "law_version": law_version,
        "source_document": chunks[0]["source_document"],
        "full_text": full_text,
    }
