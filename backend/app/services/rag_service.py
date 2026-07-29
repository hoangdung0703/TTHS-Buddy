"""RAG orchestration for POST /api/chat/query.

Retrieval is tiered by source_type, per requirements.md mục 4 ("Phân biệt rõ nguồn pháp lý
chính thức và nguồn tham khảo học thuật"): legal_text is the mandatory source for anything
that states a legal rule, and academic_reference is only pulled in as a secondary source when
legal_text alone is insufficient or the question is explicitly analytical. The two are never
merged into one ranked list - they are retrieved, thresholded and labeled separately, and
academic content never appears in the `citations` field (which is legal-citation-shaped only).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.chat import Citation, RelatedArticle
from app.prompts.rag_prompts import (
    RAG_SYSTEM_PROMPT,
    build_user_prompt,
    format_academic_context_block,
    format_legal_context_block,
)
from app.services.gemini_client import embed_query, generate_answer

logger = get_logger(__name__)

# A student typing a question uses standard Vietnamese diacritics (unlike the OCR'd source
# PDFs in ingestion/chunking.py, which needed tolerance for font-glitched "Dieu" spellings) -
# so a plain case-insensitive match on the correctly-accented word is sufficient here.
DIEU_NUMBER_PATTERN = re.compile(r"điều\s+(\d+[a-z]?)", re.IGNORECASE)

ANALYTICAL_INTENT_KEYWORDS = (
    "tại sao", "vì sao", "ý nghĩa", "phân tích", "giải thích", "bản chất",
    "so sánh", "đánh giá", "quan điểm", "vai trò"
)

LEGAL_SEMANTIC_TOP_K = 5
LEGAL_PRIMARY_COUNT = 3
LEGAL_RELATED_COUNT = 2
ACADEMIC_TOP_K = 3
LEGAL_SCORE_THRESHOLD = 0.5
ACADEMIC_SCORE_THRESHOLD = 0.5

FALLBACK_ANSWER = (
    "Xin lỗi, tôi không tìm thấy nội dung liên quan trong dữ liệu pháp luật hiện có để trả lời "
    "câu hỏi này."
)


@dataclass
class RetrievedChunk:
    point_id: str
    score: float | None
    is_exact_match: bool
    payload: dict[str, Any]


@dataclass
class RagAnswer:
    answer: str
    citations: list[Citation]
    related_articles: list[RelatedArticle]
    is_fallback: bool
    retrieved_chunks: list[RetrievedChunk]
    used_academic_reference: bool


def detect_dieu_number(question: str) -> str | None:
    match = DIEU_NUMBER_PATTERN.search(question)
    return match.group(1) if match else None


def is_analytical_question(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in ANALYTICAL_INTENT_KEYWORDS)


def _retrieve_legal_exact(client: QdrantClient, collection: str, dieu_number: str) -> list[RetrievedChunk]:
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
            FieldCondition(key="dieu_number", match=MatchValue(value=dieu_number)),
        ]),
        limit=10,
        with_payload=True,
    )
    return [RetrievedChunk(point_id=str(p.id), score=None, is_exact_match=True, payload=p.payload)
            for p in points]


def _retrieve_semantic(client: QdrantClient, collection: str, vector: list[float], source_type: str,
                        limit: int) -> list[RetrievedChunk]:
    result = client.query_points(
        collection_name=collection,
        query=vector,
        query_filter=Filter(must=[FieldCondition(key="source_type", match=MatchValue(value=source_type))]),
        limit=limit,
        with_payload=True,
    )
    return [RetrievedChunk(point_id=str(p.id), score=p.score, is_exact_match=False, payload=p.payload)
            for p in result.points]


def _dedup_by_point_id(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    deduped: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.point_id in seen:
            continue
        seen.add(chunk.point_id)
        deduped.append(chunk)
    return deduped


def _dedup_by_dieu_number(chunks: list[RetrievedChunk],
                           exclude_keys: set[tuple[str, str | None]]) -> list[RetrievedChunk]:
    seen: set[tuple[str, str | None]] = set(exclude_keys)
    deduped: list[RetrievedChunk] = []
    for chunk in chunks:
        key = (chunk.payload["dieu_number"], chunk.payload["law_version"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """A long Dieu is split into several Khoan chunks (see ingestion/chunking.py), which share
    the same dieu_number + law_version - dedup on that pair so the citations list doesn't show
    the same Dieu multiple times just because several of its Khoan were retrieved."""
    seen: set[tuple[str, str | None]] = set()
    citations: list[Citation] = []
    for chunk in chunks:
        key = (chunk.payload["dieu_number"], chunk.payload["law_version"])
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(dieu_number=chunk.payload["dieu_number"], dieu_title=chunk.payload["dieu_title"],
                                   law_version=chunk.payload["law_version"]))
    return citations


def _build_related_articles(chunks: list[RetrievedChunk]) -> list[RelatedArticle]:
    seen: set[tuple[str, str | None]] = set()
    related: list[RelatedArticle] = []
    for chunk in chunks:
        key = (chunk.payload["dieu_number"], chunk.payload["law_version"])
        if key in seen:
            continue
        seen.add(key)
        related.append(RelatedArticle(dieu_number=chunk.payload["dieu_number"], dieu_title=chunk.payload["dieu_title"]))
    return related


def _retrieve_legal(client: QdrantClient, collection: str, question: str,
                     vector: list[float]) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
    """Returns (primary_chunks, related_chunks). Exact Dieu-number matches (if the question names
    one) always take priority over semantic search results for the primary slots."""
    dieu_number = detect_dieu_number(question)
    exact_chunks = _retrieve_legal_exact(client, collection, dieu_number) if dieu_number else []
    semantic_chunks = _retrieve_semantic(client, collection, vector, "legal_text", LEGAL_SEMANTIC_TOP_K)

    merged = _dedup_by_point_id(exact_chunks + semantic_chunks)
    above_threshold = [c for c in merged if c.is_exact_match or (c.score or 0.0) >= LEGAL_SCORE_THRESHOLD]

    # Group by (dieu_number, law_version) rather than slicing the flat chunk list, so a long
    # Dieu split into several Khoan chunks (see ingestion/chunking.py) counts as ONE Dieu
    # towards LEGAL_PRIMARY_COUNT instead of eating multiple primary slots with itself.
    primary_keys_ordered: list[tuple[str, str | None]] = []
    for chunk in above_threshold:
        key = (chunk.payload["dieu_number"], chunk.payload["law_version"])
        if key not in primary_keys_ordered:
            primary_keys_ordered.append(key)
    primary_keys = set(primary_keys_ordered[:LEGAL_PRIMARY_COUNT])

    primary = [c for c in above_threshold
               if (c.payload["dieu_number"], c.payload["law_version"]) in primary_keys]
    remaining = [c for c in above_threshold
                 if (c.payload["dieu_number"], c.payload["law_version"]) not in primary_keys]
    related = _dedup_by_dieu_number(remaining, primary_keys)[:LEGAL_RELATED_COUNT]

    return primary, related


def _retrieve_academic(client: QdrantClient, collection: str, vector: list[float]) -> list[RetrievedChunk]:
    chunks = _retrieve_semantic(client, collection, vector, "academic_reference", ACADEMIC_TOP_K)
    return [c for c in chunks if (c.score or 0.0) >= ACADEMIC_SCORE_THRESHOLD]


def _is_fallback_answer(answer_text: str) -> bool:
    return "không tìm thấy nội dung liên quan" in answer_text.lower()


def answer_question(question: str, settings: Settings, qdrant_client: QdrantClient) -> RagAnswer:
    vector = embed_query(question, settings)

    legal_primary, legal_related = _retrieve_legal(qdrant_client, settings.qdrant_collection, question, vector)

    needs_academic = (
        is_analytical_question(question)
        or not legal_primary
        or max((c.score or 1.0) for c in legal_primary) < LEGAL_SCORE_THRESHOLD + 0.1
    )
    academic_chunks = _retrieve_academic(qdrant_client, settings.qdrant_collection, vector) if needs_academic else []

    context_blocks: list[str] = []
    for chunk in legal_primary:
        payload = chunk.payload
        context_blocks.append(format_legal_context_block(
            source_document=payload["source_document"], law_version=payload["law_version"],
            dieu_number=payload["dieu_number"], dieu_title=payload["dieu_title"],
            chunk_text=payload["chunk_text"]
        ))
    for chunk in academic_chunks:
        payload = chunk.payload
        context_blocks.append(format_academic_context_block(
            source_document=payload["source_document"], section_heading=payload["section_heading"],
            chunk_text=payload["chunk_text"]
        ))

    all_retrieved = legal_primary + legal_related + academic_chunks

    if not context_blocks:
        logger.info("No context passed threshold for question, returning fallback answer")
        return RagAnswer(
            answer=FALLBACK_ANSWER, citations=[], related_articles=[], is_fallback=True,
            retrieved_chunks=all_retrieved, used_academic_reference=False
        )

    user_prompt = build_user_prompt(question, context_blocks)
    answer_text = generate_answer(RAG_SYSTEM_PROMPT, user_prompt, settings)

    # The retrieval threshold is intentionally lenient (see LEGAL_SCORE_THRESHOLD), so
    # weakly-related chunks sometimes get passed as context even though none of them actually
    # answer the question (e.g. shared keywords like "hon nhan" without being on-topic). The
    # system prompt instructs the model to fall back explicitly in that case (rule 4) - when it
    # does, trust that signal and clear citations/related_articles too, so the response never
    # shows "sources" for an answer that admits it found nothing relevant.
    is_fallback = _is_fallback_answer(answer_text)
    citations = [] if is_fallback else _build_citations(legal_primary)
    related_articles = [] if is_fallback else _build_related_articles(legal_related)

    return RagAnswer(
        answer=answer_text, citations=citations, related_articles=related_articles, is_fallback=is_fallback,
        retrieved_chunks=all_retrieved, used_academic_reference=(not is_fallback) and bool(academic_chunks)
    )
