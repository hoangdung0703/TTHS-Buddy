"""Full-text lookup for one Dieu, for the citation-pill "read full article" feature (see
requirements.md "Feature nhỏ - Xem toàn văn Điều luật từ citation pill").
"""
from __future__ import annotations

import re
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

_KHOAN_SORT_PATTERN = re.compile(r"(\d+)([a-z]*)")

# Line-start markers for a Khoan ("1. ", "2. "...) and a Diem ("a) ", "b) "..., including "đ)"
# which sits between "d)" and "e)" in Vietnamese alphabetical order). Anchored to a bare digit/
# letter at the start of the (already-stripped) line so we don't misfire on in-sentence
# references like "khoản 3 và khoản 4 Điều 353" or "Điều 4." that only coincidentally contain a
# similar token.
_KHOAN_LINE_PATTERN = re.compile(r"^(\d{1,3})\.\s+\S")
_DIEM_LINE_PATTERN = re.compile(r"^(đ|[a-z])\)\s*\S")

# PDF text extraction leaves a bare page-number line in the middle of a Khoan/Diem wherever the
# source PDF paginated mid-list (e.g. Dieu 61: "...tranh luận tại phiên tòa;" / "34" / "k) Nói
# lời sau cùng..."). Drop lines that are *only* digits, and defensively strip a page number that
# ended up glued directly in front of a Diem marker on the same line.
_STANDALONE_PAGE_NUMBER_LINE = re.compile(r"^\d{1,4}$")
_PAGE_NUMBER_BEFORE_DIEM = re.compile(r"^\d{1,4}\s+(?=(?:đ|[a-z])\)\s)")


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


def _format_full_text_for_display(full_text: str) -> str:
    """Reshape an assembled Dieu's text into Markdown for ArticleModal, without touching the
    underlying chunk_text (that stays as-is for RAG/embedding). PDF extraction produced one
    physical line per wrapped sentence but no paragraph/indent markers, so a whole Dieu currently
    reads as a wall of text; this turns each Khoan into a numbered list item and each Diem inside
    it into an indented sub-item, and drops stray page-number lines along the way."""
    blocks: list[dict[str, str]] = []
    for raw_line in full_text.split("\n"):
        line = raw_line.strip()
        if not line or _STANDALONE_PAGE_NUMBER_LINE.match(line):
            continue
        line = _PAGE_NUMBER_BEFORE_DIEM.sub("", line)

        if _KHOAN_LINE_PATTERN.match(line):
            blocks.append({"type": "khoan", "text": line})
        elif _DIEM_LINE_PATTERN.match(line) and blocks:
            blocks.append({"type": "diem", "text": line})
        elif not blocks:
            blocks.append({"type": "title", "text": line})
        elif blocks[-1]["type"] == "title":
            blocks.append({"type": "plain", "text": line})
        else:
            blocks[-1]["text"] += " " + line

    parts: list[str] = []
    for block in blocks:
        if block["type"] == "diem":
            parts.append(f"   - {block['text']}")
            continue
        if parts:
            parts.append("")
        parts.append(block["text"])
    return "\n".join(parts).strip()


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
    full_text = _format_full_text_for_display(_assemble_full_text(dieu_number, dieu_title, chunks))

    return {
        "dieu_number": dieu_number,
        "dieu_title": dieu_title,
        "law_version": law_version,
        "source_document": chunks[0]["source_document"],
        "full_text": full_text,
    }
