"""RAG orchestration for POST /api/chat/query.

Retrieval is tiered by source_type, per requirements.md mục 4 ("Phân biệt rõ nguồn pháp lý
chính thức và nguồn tham khảo học thuật"): legal_text is the mandatory source for anything
that states a legal rule, and academic_reference is a secondary, analytical-only source. The
two are queried unconditionally and independently every time (see requirements.md "BUG PHÁT
HIỆN SAU" note - the old either/or short-circuit skipped academic_reference whenever legal_text
happened to score above threshold, even when that score came from incidental keyword overlap
rather than an answer to the question), each thresholded and labeled on its own, and academic
content never appears in the `citations` field (which is legal-citation-shaped only).
"""
from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.chat import (
    ChatStreamAnswerDeltaEvent,
    ChatStreamCitationsEvent,
    ChatStreamDoneEvent,
    ChatStreamSuggestedFollowupsEvent,
    Citation,
    RelatedArticle,
    SuggestedFollowup,
)
from app.prompts.rag_prompts import (
    build_system_prompt,
    build_user_prompt,
    format_academic_context_block,
    format_legal_context_block,
)
from app.services.chat_suggestions_service import build_suggested_question
from app.services.gemini_client import embed_query, stream_generate_answer

logger = get_logger(__name__)

# A student typing a question uses standard Vietnamese diacritics (unlike the OCR'd source
# PDFs in ingestion/chunking.py, which needed tolerance for font-glitched "Dieu" spellings) -
# so a plain case-insensitive match on the correctly-accented word is sufficient here.
DIEU_NUMBER_PATTERN = re.compile(r"điều\s+(\d+[a-z]?)", re.IGNORECASE)

# Several ingested legal_text documents number their own Dieu starting from 1 (BLTTHS, BLHS,
# Nghi dinh 250, 2 Thong tu lien tich all have a "Dieu 13" or similar), so an exact dieu_number
# match without a document filter would return every one of them as if they were all equally
# relevant to a question naming a single law - a real bug found via end-to-end browser testing
# (asking about "Dieu 13 Bo luat To tung hinh su" also surfaced Nghi dinh 250's and Thong tu lien
# tich 05's unrelated Dieu 13). Ordered most-specific-first so "Thong tu lien tich 01" is checked
# before a hypothetical looser prefix match, though the two TTLT numbers ("01"/"05") don't
# actually collide with each other here.
LAW_NAME_TO_SOURCE_DOCUMENT: list[tuple[re.Pattern[str], str]] = [
    # "tths" (not "bltths") is the match target on purpose: it matches both the standalone
    # abbreviation "TTHS" (as students commonly write "Bo luat TTHS"/"Luat TTHS") AND "BLTTHS" (a
    # substring of it) with one alternative. The previous pattern here was "blths" (5 letters,
    # missing a "t") - a typo that silently never matched EITHER real spelling ("BLTTHS" is 6
    # letters, "blths" is not a substring of it) - confirmed by direct regex testing before this
    # fix; this is what caused source_document detection to fail for a real reported question
    # ("Bo luat TTHS gom bao nhieu chuong, bao nhieu dieu?" - see requirements.md Phase 3
    # Extension) even though the code "looked" like it should have matched.
    (re.compile(r"bộ luật tố tụng hình sự|tths", re.IGNORECASE), "Bộ luật TTHS.pdf"),
    (re.compile(r"bộ luật hình sự|blhs", re.IGNORECASE), "Văn bản hợp nhất BLHS 2015.pdf"),
    (re.compile(r"nghị định\s*250", re.IGNORECASE), "Nghị định 250_NĐ-CP.pdf"),
    (re.compile(r"thông tư liên tịch\s*05", re.IGNORECASE), "Thông tư liên tịch 05.pdf"),
    (re.compile(r"thông tư liên tịch\s*01", re.IGNORECASE), "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf"),
]

ANALYTICAL_INTENT_KEYWORDS = (
    "tại sao", "vì sao", "ý nghĩa", "phân tích", "giải thích", "bản chất",
    "so sánh", "đánh giá", "quan điểm", "vai trò"
)

# Phase 3 Extension: a question like "Bo luat TTHS gom bao nhieu chuong, bao nhieu dieu?" has no
# single chunk that answers it - it's a structural/counting question about the WHOLE document,
# not a lookup of one provision - so no amount of retrieval tuning fixes it (grounding correctly
# refuses since nothing retrieved actually answers it). Handled as a separate short-circuit intent
# instead: detect it, then count directly against Qdrant (distinct chuong_number/dieu_number for
# the named document) rather than asking the LLM to infer a count from retrieved context (an LLM
# counting from a handful of retrieved chunks would either miscount or fabricate a total).
AGGREGATE_QUERY_PATTERN = re.compile(
    r"(bao nhiêu|tổng số|có mấy|gồm mấy)\s+(chương|điều|khoản)", re.IGNORECASE
)

AGGREGATE_SCROLL_PAGE_SIZE = 1000

# A chuong's chunks are scattered across however many Khoan-split pieces its Dieu happen to need
# (see ingestion/chunking.py LONG_DIEU_CHAR_THRESHOLD) - the largest real chuong in the corpus
# (BLHS Chuong XVIII) has 114 chunks, so this is set well above that to guarantee one scroll call
# sees every chunk of any chuong without needing pagination.
SUGGESTED_FOLLOWUP_CHUONG_SCROLL_LIMIT = 200

LEGAL_SEMANTIC_TOP_K = 5
LEGAL_PRIMARY_COUNT = 3
LEGAL_RELATED_COUNT = 2
ACADEMIC_TOP_K = 3
LEGAL_SCORE_THRESHOLD = 0.5
ACADEMIC_SCORE_THRESHOLD = 0.5

# requirements.md "Cải thiện retrieval cho câu hỏi vận dụng/tình huống dài" Bước 1: a long,
# multi-fact tình huống question dilutes the embedding towards surface procedural details
# repeated in the question text, pushing the Dieu that actually holds the core legal principle
# out of a small top-k even when it still clears LEGAL_SCORE_THRESHOLD. Widening the semantic
# pool (not the score threshold, not academic_reference, not exact-match) gives that Dieu more
# room to surface without loosening precision for the short/medium questions that already work -
# threshold picked from the 3 real diagnostic questions (106/159/572 chars): only the 572-char
# tình huống question should cross it, vandung-q7 (159) and vandung-q26 (106) must not.
LONG_QUESTION_CHAR_THRESHOLD = 250
LEGAL_SEMANTIC_TOP_K_LONG = 25
LEGAL_PRIMARY_COUNT_LONG = 8

# requirements.md "Tăng impact LLM..." fallback step: settings.resolved_complex_chat_model
# (preview-tier, high latency variance - 5s-68s observed) gets this long to produce a first token
# before stream_generate_answer gives up and falls back to the fast/reliable gemini_chat_model -
# picked from the middle of the requested 15-20s range, low enough to cap worst-case latency,
# high enough not to abandon a pro-preview response that was already about to arrive.
LONG_QUESTION_FIRST_TOKEN_TIMEOUT_SECONDS = 18.0

# An academic_reference passage that spans multiple paragraphs (ingestion/chunking.py splits
# academic_reference by paragraph, not by whole subsection - see requirements.md Phase 3) gets
# fragmented into several consecutive chunk_index values, only some of which score high enough
# to land in the top-k semantic hits: the paragraph that states the topic/opens the passage
# scores highest (densest keyword overlap with a broad question), while later paragraphs that
# narrate specific facts (dates, law names) within the SAME passage often score noticeably lower
# and fall out of a small top-k - confirmed by direct reproduction on "lich su phat trien phap
# luat TTHS": the corpus has the full 1975-1988 and 1989-nay periods (chunk_index 23-30 of
# "Giao trinh Luat To tung hinh su"), but ACADEMIC_TOP_K=3 only ever surfaced the opening chunks
# (20-21) - even raising top-k to 20 never surfaced chunk_index 27/29 (they don't score high
# enough on pure semantic similarity despite being textually contiguous with what did score
# high). Bounded window expansion around each real anchor's chunk_index fixes this in a way pure
# top-k tuning structurally cannot, since it goes by document position (guaranteed complete) not
# by semantic score (gappy).
#
# Biased forward-heavy (BACKWARD=2, FORWARD=10) rather than a symmetric window: both reproduced
# cases (this one and "phuong phap dieu chinh" from the same chapter) show the top-scoring anchor
# landing at or near the START of the relevant passage, not its middle/end - the opening sentence
# of a subsection is exactly what's keyword-dense enough to rank highest. A symmetric window
# would waste half its budget re-fetching content already adjacent to the anchor's own opening
# paragraph instead of reaching the continuation that's actually missing.
ACADEMIC_EXPANSION_BACKWARD = 2
ACADEMIC_EXPANSION_FORWARD = 10
# Hard cap on total EXTRA chunks (beyond the original anchors) added across every anchor combined
# - bounds worst-case context growth regardless of how many anchors or how wide the window is.
# ~933 chars/chunk average (see requirements.md) x 12 = ~11k extra chars (~2.8k tokens): enough to
# fully cover one fragmented passage (the reproduced case needs 9 chunks forward of its anchor)
# without letting expansion balloon on every query.
ACADEMIC_EXPANSION_MAX_EXTRA = 12

# Phase 6: how many "next question" chips to surface after an answer, and how many neighbor
# candidates to fetch before filtering out self/already-cited Dieu (fetch a buffer since some
# of the nearest neighbors are typically other Khoan of Dieu already in citations/related).
SUGGESTED_FOLLOWUP_COUNT = 3
SUGGESTED_FOLLOWUP_FETCH_LIMIT = 8

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
    suggested_followups: list[SuggestedFollowup]
    is_fallback: bool
    retrieved_chunks: list[RetrievedChunk]
    used_academic_reference: bool


@dataclass
class RetrievalResult:
    """Output of the retrieval phase, ahead of - and independent from - generation. Split out
    from the old single-shot answer_question (Phase 4) so the SSE path (Phase 4 Extension) can
    emit the "citations" event as soon as this is ready, without waiting for the model to start
    generating."""
    context_blocks: list[str]
    legal_primary: list[RetrievedChunk]
    legal_related: list[RetrievedChunk]
    all_retrieved: list[RetrievedChunk]
    used_academic_reference: bool


def detect_dieu_number(question: str) -> str | None:
    match = DIEU_NUMBER_PATTERN.search(question)
    return match.group(1) if match else None


def detect_source_document(question: str) -> str | None:
    """Returns the source_document the question names explicitly (e.g. "Bo luat To tung hinh
    su", "Nghi dinh 250"), or None if it doesn't name one - callers should fall back to
    unscoped retrieval in that case rather than guessing."""
    for pattern, source_document in LAW_NAME_TO_SOURCE_DOCUMENT:
        if pattern.search(question):
            return source_document
    return None


def is_analytical_question(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in ANALYTICAL_INTENT_KEYWORDS)


def is_aggregate_structure_question(question: str) -> bool:
    return bool(AGGREGATE_QUERY_PATTERN.search(question))


def _dieu_sort_key(dieu_number: str) -> tuple[int, str]:
    match = re.match(r"(\d+)([a-z]*)", dieu_number)
    if not match:
        return (0, dieu_number)
    return (int(match.group(1)), match.group(2))


def count_chuong_and_dieu(client: QdrantClient, collection: str,
                          source_document: str) -> tuple[int, int, str | None]:
    """Counts distinct chuong_number and dieu_number for one legal_text document by scrolling
    every one of its chunks - not a similarity search, since an aggregate/structural question has
    no single "most relevant" chunk to rank against. law_version is read off whichever chunk
    happens to be seen first (every chunk of one document carries the same law_version)."""
    chuong_numbers: set[str] = set()
    dieu_numbers: set[str] = set()
    law_version: str | None = None
    scroll_filter = Filter(must=[
        FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
        FieldCondition(key="source_document", match=MatchValue(value=source_document)),
    ])

    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=AGGREGATE_SCROLL_PAGE_SIZE,
            offset=offset,
            with_payload=["chuong_number", "dieu_number", "law_version"],
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            if payload.get("chuong_number"):
                chuong_numbers.add(payload["chuong_number"])
            if payload.get("dieu_number"):
                dieu_numbers.add(payload["dieu_number"])
            if law_version is None and payload.get("law_version"):
                law_version = payload["law_version"]
        if offset is None:
            break

    return len(chuong_numbers), len(dieu_numbers), law_version


def build_aggregate_structure_answer(source_document: str, law_version: str | None,
                                      chuong_count: int, dieu_count: int) -> str:
    display_name = law_version or source_document.removesuffix(".pdf")
    if chuong_count > 0:
        body = f"Theo dữ liệu đã được nạp vào hệ thống, {display_name} gồm {chuong_count} chương và {dieu_count} điều."
    else:
        body = (
            f"Theo dữ liệu đã được nạp vào hệ thống, {display_name} không được chia thành các "
            f"chương và gồm {dieu_count} điều."
        )
    note = (
        " Lưu ý: đây là số liệu đếm trực tiếp từ dữ liệu văn bản đã được nạp vào hệ thống (ingest), "
        "không phải trích dẫn từ một Điều/Khoản cụ thể, và có thể lệch nếu văn bản đã có sửa đổi, "
        "bổ sung sau thời điểm dữ liệu được nạp."
    )
    return body + note


def _retrieve_legal_exact(client: QdrantClient, collection: str, dieu_number: str,
                           source_document: str | None) -> list[RetrievedChunk]:
    must_conditions = [
        FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
        FieldCondition(key="dieu_number", match=MatchValue(value=dieu_number)),
    ]
    if source_document:
        must_conditions.append(FieldCondition(key="source_document", match=MatchValue(value=source_document)))

    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=must_conditions),
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


def _same_chuong_followups(client: QdrantClient, collection: str, top_chunk: RetrievedChunk,
                            seen_keys: set[tuple[str, str | None]]) -> list[SuggestedFollowup]:
    """Now that chuong_number is real ingested metadata (Phase 3 Extension - see
    requirements.md), an exact Qdrant filter on it is strictly more precise than vector
    similarity for "other Dieu in the same chapter" - similarity can surface a topically related
    Dieu from a different chuong (the old accepted-limitation), while this can't, by
    construction. Ordered by NUMERIC PROXIMITY to the cited Dieu (not plain ascending order) -
    a large chuong (e.g. BLHS Chuong XVIII has 70 Dieu) would otherwise always surface its first
    few Dieu regardless of which one was actually cited, instead of the functionally-related
    neighbors right around it (Vietnamese legal drafting groups a role's Dieu consecutively, e.g.
    Tham phan/Tham tra vien/Thu ky Toa an sit right next to each other - see the Dieu 45 test)."""
    chuong_number = top_chunk.payload.get("chuong_number")
    if not chuong_number:
        return []

    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
            FieldCondition(key="source_document", match=MatchValue(value=top_chunk.payload["source_document"])),
            FieldCondition(key="chuong_number", match=MatchValue(value=chuong_number)),
        ]),
        limit=SUGGESTED_FOLLOWUP_CHUONG_SCROLL_LIMIT,
        with_payload=True,
    )

    top_dieu_number, _ = _dieu_sort_key(top_chunk.payload["dieu_number"])

    def proximity_key(point) -> tuple[int, tuple[int, str]]:  # noqa: ANN001 - qdrant ScoredPoint/Record
        dieu_key = _dieu_sort_key(point.payload["dieu_number"])
        return (abs(dieu_key[0] - top_dieu_number), dieu_key)

    followups: list[SuggestedFollowup] = []
    for point in sorted(points, key=proximity_key):
        key = (point.payload["dieu_number"], point.payload["law_version"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        followups.append(SuggestedFollowup(
            dieu_number=point.payload["dieu_number"],
            suggested_question=build_suggested_question(point.payload["dieu_title"] or ""),
        ))
        if len(followups) == SUGGESTED_FOLLOWUP_COUNT:
            break

    return followups


def _vector_similarity_followups(client: QdrantClient, collection: str, top_chunk: RetrievedChunk,
                                  seen_keys: set[tuple[str, str | None]],
                                  remaining_count: int) -> list[SuggestedFollowup]:
    """Fallback for when the same-chuong filter can't fill all slots (e.g. this Dieu's chuong has
    too few other Dieu, or the document has no Chuong structure at all - see requirements.md).
    Reuses the just-cited chunk's own stored vector (no re-embedding)."""
    records = client.retrieve(collection_name=collection, ids=[top_chunk.point_id], with_vectors=True)
    if not records or records[0].vector is None:
        return []

    result = client.query_points(
        collection_name=collection,
        query=records[0].vector,
        query_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
            FieldCondition(key="source_document", match=MatchValue(value=top_chunk.payload["source_document"])),
        ]),
        limit=SUGGESTED_FOLLOWUP_FETCH_LIMIT,
        with_payload=True,
    )

    followups: list[SuggestedFollowup] = []
    for point in result.points:
        if str(point.id) == top_chunk.point_id:
            continue
        key = (point.payload["dieu_number"], point.payload["law_version"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        followups.append(SuggestedFollowup(
            dieu_number=point.payload["dieu_number"],
            suggested_question=build_suggested_question(point.payload["dieu_title"] or ""),
        ))
        if len(followups) == remaining_count:
            break

    return followups


def _build_suggested_followups(client: QdrantClient, collection: str, top_chunk: RetrievedChunk,
                                cited_dieu_numbers: set[tuple[str, str | None]]) -> list[SuggestedFollowup]:
    seen_keys = set(cited_dieu_numbers)
    seen_keys.add((top_chunk.payload["dieu_number"], top_chunk.payload["law_version"]))

    followups = _same_chuong_followups(client, collection, top_chunk, seen_keys)

    if len(followups) < SUGGESTED_FOLLOWUP_COUNT:
        followups += _vector_similarity_followups(
            client, collection, top_chunk, seen_keys, SUGGESTED_FOLLOWUP_COUNT - len(followups)
        )

    return followups


def _retrieve_legal(client: QdrantClient, collection: str, question: str,
                     vector: list[float]) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
    """Returns (primary_chunks, related_chunks). Exact Dieu-number matches (if the question names
    one) always take priority over semantic search results for the primary slots.

    Long/tình huống questions (see LONG_QUESTION_CHAR_THRESHOLD) widen both the semantic pool and
    the number of primary slots - a wider pool alone would still cap the correct Dieu out at
    LEGAL_PRIMARY_COUNT=3 if 3 more-surface-similar Dieu already rank above it, which is exactly
    the failure mode this fix targets. Exact-match and academic_reference retrieval are
    untouched - only the legal_text semantic branch is affected.
    """
    dieu_number = detect_dieu_number(question)
    source_document = detect_source_document(question) if dieu_number else None
    exact_chunks = _retrieve_legal_exact(client, collection, dieu_number, source_document) if dieu_number else []

    is_long_question = len(question) > LONG_QUESTION_CHAR_THRESHOLD
    semantic_top_k = LEGAL_SEMANTIC_TOP_K_LONG if is_long_question else LEGAL_SEMANTIC_TOP_K
    primary_count = LEGAL_PRIMARY_COUNT_LONG if is_long_question else LEGAL_PRIMARY_COUNT
    semantic_chunks = _retrieve_semantic(client, collection, vector, "legal_text", semantic_top_k)

    merged = _dedup_by_point_id(exact_chunks + semantic_chunks)
    above_threshold = [c for c in merged if c.is_exact_match or (c.score or 0.0) >= LEGAL_SCORE_THRESHOLD]

    # Group by (dieu_number, law_version) rather than slicing the flat chunk list, so a long
    # Dieu split into several Khoan chunks (see ingestion/chunking.py) counts as ONE Dieu
    # towards primary_count instead of eating multiple primary slots with itself.
    primary_keys_ordered: list[tuple[str, str | None]] = []
    for chunk in above_threshold:
        key = (chunk.payload["dieu_number"], chunk.payload["law_version"])
        if key not in primary_keys_ordered:
            primary_keys_ordered.append(key)
    primary_keys = set(primary_keys_ordered[:primary_count])

    primary = [c for c in above_threshold
               if (c.payload["dieu_number"], c.payload["law_version"]) in primary_keys]
    remaining = [c for c in above_threshold
                 if (c.payload["dieu_number"], c.payload["law_version"]) not in primary_keys]
    related = _dedup_by_dieu_number(remaining, primary_keys)[:LEGAL_RELATED_COUNT]

    return primary, related


def _expand_academic_neighbors(client: QdrantClient, collection: str,
                                anchors: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """For each anchor academic_reference chunk, pulls in nearby chunk_index neighbors from the
    SAME source_document (see ACADEMIC_EXPANSION_* constants for why forward-biased and bounded)
    to fill in a paragraph-fragmented passage a small top-k would otherwise only partially
    surface. An anchor with an isolated chunk_index (nothing else nearby in the corpus - e.g. a
    stray bibliography-entry chunk far from any real passage) simply yields no neighbors, so this
    never manufactures context that isn't already position-adjacent to a real semantic hit."""
    seen_keys = {(a.payload["source_document"], a.payload["chunk_index"]) for a in anchors}
    extra: list[RetrievedChunk] = []

    for anchor in anchors:
        chunk_index = anchor.payload.get("chunk_index")
        if chunk_index is None:
            continue

        points, _ = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="source_type", match=MatchValue(value="academic_reference")),
                FieldCondition(key="source_document", match=MatchValue(value=anchor.payload["source_document"])),
                FieldCondition(key="chunk_index", range=Range(
                    gte=chunk_index - ACADEMIC_EXPANSION_BACKWARD, lte=chunk_index + ACADEMIC_EXPANSION_FORWARD
                )),
            ]),
            limit=ACADEMIC_EXPANSION_BACKWARD + ACADEMIC_EXPANSION_FORWARD + 1,
            with_payload=True,
        )
        for point in points:
            key = (point.payload["source_document"], point.payload["chunk_index"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            extra.append(RetrievedChunk(point_id=str(point.id), score=None, is_exact_match=False,
                                         payload=point.payload))
            if len(extra) == ACADEMIC_EXPANSION_MAX_EXTRA:
                return extra

    return extra


def _retrieve_academic(client: QdrantClient, collection: str, vector: list[float]) -> list[RetrievedChunk]:
    chunks = _retrieve_semantic(client, collection, vector, "academic_reference", ACADEMIC_TOP_K)
    anchors = [c for c in chunks if (c.score or 0.0) >= ACADEMIC_SCORE_THRESHOLD]
    if not anchors:
        return anchors

    neighbors = _expand_academic_neighbors(client, collection, anchors)
    combined = anchors + neighbors
    combined.sort(key=lambda c: (c.payload["source_document"], c.payload["chunk_index"]))
    return combined


def _is_fallback_answer(answer_text: str) -> bool:
    return "không tìm thấy nội dung liên quan" in answer_text.lower()


def _extract_cited_dieu_numbers(answer_text: str) -> set[str]:
    """RAG_SYSTEM_PROMPT rule 2 requires the model to name a legal_text citation as "Theo Dieu
    [so] [ten van ban]..." - reusing DIEU_NUMBER_PATTERN (built for detecting a Dieu number in
    the student's question) against the generated answer instead lets us tell which retrieved
    legal_primary chunks were actually used vs merely retrieved."""
    return {match.group(1) for match in DIEU_NUMBER_PATTERN.finditer(answer_text)}


async def retrieve_context(question: str, settings: Settings, qdrant_client: QdrantClient) -> RetrievalResult:
    # embed_query calls Gemini synchronously (httpx.post, not AsyncClient) - offloaded to a
    # thread for the same reason the sync QdrantClient calls just below are: without this it
    # blocks the single event loop for every other in-flight request during the round-trip.
    vector = await asyncio.to_thread(embed_query, question, settings)

    # legal_text and academic_reference answer different kinds of questions (a legal rule vs a
    # concept/theory explanation) - a high legal_text score is not evidence academic_reference is
    # unneeded, since it can come from incidental keyword overlap with a Dieu that doesn't
    # actually answer the question (e.g. "phuong phap dieu chinh cua LTTHS" matching "Dieu 1.
    # Pham vi dieu chinh" on the word "dieu chinh" alone - see requirements.md). So both are
    # always queried, concurrently via asyncio.to_thread since qdrant_client is a sync client.
    (legal_primary, legal_related), academic_chunks = await asyncio.gather(
        asyncio.to_thread(_retrieve_legal, qdrant_client, settings.qdrant_collection, question, vector),
        asyncio.to_thread(_retrieve_academic, qdrant_client, settings.qdrant_collection, vector),
    )

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

    return RetrievalResult(
        context_blocks=context_blocks, legal_primary=legal_primary, legal_related=legal_related,
        all_retrieved=legal_primary + legal_related + academic_chunks, used_academic_reference=bool(academic_chunks)
    )


async def stream_answer_question(
    question: str, conversation_id: uuid.UUID, settings: Settings, qdrant_client: QdrantClient, result: RagAnswer,
    recent_turns: list[dict[str, str]] | None = None, is_out_of_scope: bool = False
) -> AsyncIterator[tuple[str, ChatStreamCitationsEvent | ChatStreamAnswerDeltaEvent |
                          ChatStreamSuggestedFollowupsEvent | ChatStreamDoneEvent]]:
    """Streaming counterpart of the old answer_question (Phase 4 Extension - see
    requirements.md). Yields (event_name, payload) tuples in the order: answer_delta (one or
    more) -> citations -> suggested_followups -> done - except for the two early-return cases
    below (aggregate-structure and no-context-blocks), which have a deterministic, already-final
    answer up front and so emit citations (always empty in both cases) before their single
    answer_delta.

    `result` is mutated in place with the final answer/citations/is_fallback/etc as a side
    effect, for the caller to log to chat_query_logs after the stream ends - kept OUT of the
    yielded events on purpose, since is_fallback/used_academic_reference/retrieved_chunks are
    intentionally not part of the public API response (see requirements.md Phase 9: those two
    fields are read only from chat_query_logs via the service role, never exposed to the client).

    Citations are trustworthy only once both (a) we know the answer isn't a refusal disguised as
    "context was found" (generation can still refuse even when retrieval passed threshold), and
    (b) we know which of the retrieved legal_text chunks the model actually used - retrieval
    threshold is intentionally lenient, and since the either/or short-circuit between legal_text
    and academic_reference was removed (see requirements.md "BUG PHÁT HIỆN SAU"), legal_primary
    can contain a Dieu that scored high purely from incidental keyword overlap (e.g. "Dieu 1.
    Pham vi dieu chinh" matching a question about "phuong phap dieu chinh") that the model
    correctly ignored in favor of academic_reference. Both require the complete answer text, so
    citations are computed after the stream ends rather than guessed from retrieval alone -
    forwarding every token to the client immediately keeps the perceived response latency the
    same as before; only the citations badge is delayed until the answer it describes exists.

    `is_out_of_scope` (requirements.md muc E - query_understanding_service.rewrite_question's own
    classification, computed by the caller BEFORE this function runs) short-circuits straight to
    the refusal answer, same shape as the no-context-blocks case below, WITHOUT calling retrieval
    or generation at all - a question already classified as unrelated to Luat To tung Hinh su has
    nothing for either step to usefully do, and skipping both avoids the exact failure mode this
    fix targets: a malformed/off-topic query string reaching retrieval or the generation prompt.
    """
    if is_out_of_scope:
        result.answer = FALLBACK_ANSWER
        result.citations = []
        result.related_articles = []
        result.suggested_followups = []
        result.is_fallback = True
        result.used_academic_reference = False
        result.retrieved_chunks = []
        yield ("citations", ChatStreamCitationsEvent(
            citations=[], related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=FALLBACK_ANSWER))
        yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=[]))
        yield ("done", ChatStreamDoneEvent())
        return

    if is_aggregate_structure_question(question):
        source_document = detect_source_document(question)
        if source_document:
            chuong_count, dieu_count, law_version = count_chuong_and_dieu(
                qdrant_client, settings.qdrant_collection, source_document
            )
            if dieu_count > 0:
                answer_text = build_aggregate_structure_answer(source_document, law_version, chuong_count, dieu_count)
                result.answer = answer_text
                result.citations = []
                result.related_articles = []
                result.suggested_followups = []
                result.is_fallback = False
                result.used_academic_reference = False
                result.retrieved_chunks = []
                yield ("citations", ChatStreamCitationsEvent(
                    citations=[], related_articles=[], conversation_id=conversation_id, rewritten_question=question
                ))
                yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
                yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=[]))
                yield ("done", ChatStreamDoneEvent())
                return
            # dieu_count == 0: named document has no legal_text data under that name (unexpected -
            # e.g. a stale/mistyped source_document match) - fall through to normal retrieval
            # rather than surfacing a hard "0 dieu" answer that's more likely a bug than a fact.

    retrieval = await retrieve_context(question, settings, qdrant_client)
    result.retrieved_chunks = retrieval.all_retrieved

    if not retrieval.context_blocks:
        logger.info("No context passed threshold for question, returning fallback answer")
        result.answer = FALLBACK_ANSWER
        result.is_fallback = True
        result.used_academic_reference = False
        yield ("citations", ChatStreamCitationsEvent(
            citations=[], related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=FALLBACK_ANSWER))
        yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=[]))
        yield ("done", ChatStreamDoneEvent())
        return

    user_prompt = build_user_prompt(question, retrieval.context_blocks, recent_turns)

    # requirements.md "Tăng impact LLM cho câu hỏi dài/phức tạp": long/tình huống questions (same
    # threshold as Bước 1's retrieval widening, LONG_QUESTION_CHAR_THRESHOLD) get a stronger model
    # and an explicit chain-of-thought instruction for the final generation call only - retrieval
    # above is unaffected by this flag. fallback_model/first_token_timeout are only set for long
    # questions - if resolved_complex_chat_model is slow/unavailable, stream_generate_answer falls
    # back to gemini_chat_model (still with the CoT system_prompt) rather than making the student
    # wait indefinitely on a preview-tier model - see gemini_client.py's docstring for the exact
    # fallback contract.
    is_long_question = len(question) > LONG_QUESTION_CHAR_THRESHOLD
    system_prompt = build_system_prompt(is_long_question)
    generation_model = settings.resolved_complex_chat_model if is_long_question else settings.gemini_chat_model
    fallback_model = settings.gemini_chat_model if is_long_question else None
    first_token_timeout = LONG_QUESTION_FIRST_TOKEN_TIMEOUT_SECONDS if is_long_question else None

    answer_parts: list[str] = []
    async for text_chunk in stream_generate_answer(
        system_prompt, user_prompt, settings, model=generation_model,
        fallback_model=fallback_model, first_token_timeout=first_token_timeout
    ):
        answer_parts.append(text_chunk)
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=text_chunk))

    answer_text = "".join(answer_parts)
    # Same trust-the-model's-own-refusal reasoning as the old answer_question: the retrieval
    # threshold is intentionally lenient (see LEGAL_SCORE_THRESHOLD), so weakly-related chunks
    # sometimes get passed as context even though none of them actually answer the question -
    # when the model refuses anyway, clear citations/related_articles so the final logged/served
    # answer never shows "sources" for a response that admits it found nothing relevant.
    is_fallback = _is_fallback_answer(answer_text)

    # Restrict citations to the legal_primary chunks the model actually cited (per the system
    # prompt's rule 2, a legal_text citation always names its Dieu as "Theo Dieu [so]...") rather
    # than every chunk that merely passed retrieval threshold - see the module-level docstring's
    # "BUG PHAT HIEN SAU" reference for why a high-scoring legal_primary chunk isn't necessarily
    # one the model actually used.
    cited_dieu_numbers = _extract_cited_dieu_numbers(answer_text)
    actually_cited_primary = [c for c in retrieval.legal_primary if c.payload["dieu_number"] in cited_dieu_numbers]
    citations = [] if is_fallback else _build_citations(actually_cited_primary)
    related_articles = [] if is_fallback else _build_related_articles(retrieval.legal_related)

    yield ("citations", ChatStreamCitationsEvent(
        citations=citations, related_articles=related_articles,
        conversation_id=conversation_id, rewritten_question=question
    ))

    suggested_followups: list[SuggestedFollowup] = []
    if not is_fallback and actually_cited_primary:
        cited_keys = {(c.dieu_number, c.law_version) for c in citations}
        suggested_followups = _build_suggested_followups(
            qdrant_client, settings.qdrant_collection, actually_cited_primary[0], cited_keys
        )

    result.answer = answer_text
    result.citations = citations
    result.related_articles = related_articles
    result.suggested_followups = suggested_followups
    result.is_fallback = is_fallback
    result.used_academic_reference = (not is_fallback) and retrieval.used_academic_reference

    yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=suggested_followups))
    yield ("done", ChatStreamDoneEvent())
