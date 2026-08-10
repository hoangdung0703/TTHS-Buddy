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
import random
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

from app.core.config import Settings
from app.core.document_display_names import get_display_name
from app.core.logging import get_logger
from app.models.chat import (
    ChatStreamAnswerDeltaEvent,
    ChatStreamCitationsEvent,
    ChatStreamDoneEvent,
    ChatStreamGradingEvent,
    ChatStreamSuggestedFollowupsEvent,
    Citation,
    RelatedArticle,
    SuggestedFollowup,
)
from app.prompts.conversational_prompts import (
    EXPLAIN_SIMPLER_SYSTEM_PROMPT,
    GREETING_TEMPLATES,
    NO_PREVIOUS_ANSWER_FOR_EXPLAIN_MESSAGE,
    NO_PREVIOUS_ANSWER_MESSAGE,
    NO_SCENARIO_CONTEXT_MESSAGE,
    NO_SCENARIO_TO_GRADE_MESSAGE,
    SUMMARIZE_SYSTEM_PROMPT,
    build_explain_simpler_prompt,
    build_summarize_prompt,
)
from app.prompts.rag_prompts import (
    ANONYMIZATION_DISCLAIMER,
    ANONYMIZATION_LEAK_FALLBACK_ANSWER,
    RULE9_VIOLATION_FALLBACK_ANSWER,
    build_system_prompt,
    build_user_prompt,
    format_academic_context_block,
    format_legal_context_block,
)
from app.services.chat_suggestions_service import build_suggested_question
from app.services.gemini_client import embed_query, generate_answer, stream_generate_answer
from app.services.scenario_grading_service import grade_scenario_answer
from app.services.scenario_service import generate_scenario

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

# requirements.md "Cải thiện retrieval..." Bước 1 originally widened this pool ONLY for long/
# tình huống questions (len(question) > 250), on the theory that only a long, multi-fact question
# dilutes the embedding enough to push the correct Dieu out of a small top-k. A later real UAT
# case (short multi-turn question, ~190 chars, about a co-defendant discovered mid-trial) showed
# the same failure mode on a SHORT question too: the correct Dieu (280 - "Trả hồ sơ để điều tra bổ
# sung") scored 0.66 (above LEGAL_SCORE_THRESHOLD) but ranked #11, outside a top_k=5 pool - the
# "long question" proxy simply didn't cover this case. Measured empirically (real API, not just
# this one case) before generalizing: applying top_k=25/primary_count=8 to EVERY legal_text
# question (not just long ones) costs +0.058s mean retrieval latency (retrieval already runs
# concurrently with academic_reference and dominated by the embed call, not Qdrant's own top-k
# search cost) and, on the 29-question eval suite, citation exact_match_rate 95%->100% and
# mean_recall 95%->100%, with mean_precision only 77%->75% (2pp, within noise - LEGAL_SCORE_THRESHOLD
# still filters low-relevance chunks and primary_count still caps how many Dieu reach the final
# context/citations either way). No length-based proxy needed - always use the wider pool.
LEGAL_SEMANTIC_TOP_K = 25
LEGAL_PRIMARY_COUNT = 8

# requirements.md "Điều 280 vs Điều 170" investigation: with LEGAL_PRIMARY_COUNT=8 chosen purely by
# score-order distinct-Dieu rank, several near-duplicate administrative Dieu from the SAME source
# document (e.g. Thông tư liên tịch 01/2026's Điều 8/9/14/29, all about khởi tố bị can/nhập tách vụ
# án - topically adjacent to nearly every procedural question) can occupy most of the 8 slots ahead
# of the actually-relevant Dieu from a DIFFERENT document (real case: Điều 280 BLTTHS ranked #9
# distinct-Dieu, one slot past the cap, on ~10-20% of runs depending on minor Query Understanding
# rewrite variance) - confirmed via direct _retrieve_legal debugging: the correct Dieu was in the
# top-25 semantic pool but never reached legal_primary, and legal_related (where it landed instead)
# is NEVER fed into context_blocks/generation, so this was a retrieval-selection bug, not a
# generation "picked the wrong of two co-present Dieu" bug. 3 (not 4) is the smallest cap that
# empirically resolves the reproduced case - see _retrieve_legal for how it's applied.
MAX_PRIMARY_PER_SOURCE_DOCUMENT = 3
LEGAL_RELATED_COUNT = 2
ACADEMIC_TOP_K = 3
LEGAL_SCORE_THRESHOLD = 0.5
ACADEMIC_SCORE_THRESHOLD = 0.5

# Still used by stream_answer_question below (generation model/CoT addendum selection for long/
# tình huống questions) - retrieval pool width no longer depends on this (see above).
LONG_QUESTION_CHAR_THRESHOLD = 250

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
    # Hidden rubric for intent=request_scenario (requirements.md "Sinh tình huống minh họa" Lượt
    # 1) - never sent over SSE (see stream_answer_question's docstring), only logged to
    # chat_query_logs for Lượt 2 grading (not built yet). None for every other intent/branch.
    scenario_key_points: list[str] | None = None
    # requirements.md RAG_SYSTEM_PROMPT rule 9 grounding audit - log-only (see
    # _rule9_ungrounded_dieu_numbers's docstring for why this isn't a fail-closed guard). Never
    # sent over SSE, only logged to chat_query_logs for continuous monitoring. Empty list (not
    # None) when the check ran and found nothing; only None for branches that don't generate a
    # legal-content answer at all (greeting, summarize_previous, etc - same "not applicable" style
    # as scenario_key_points above).
    rule9_ungrounded_dieu_numbers: list[str] | None = None


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
    display_name = law_version or get_display_name(source_document)
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

    Semantic pool width (LEGAL_SEMANTIC_TOP_K/LEGAL_PRIMARY_COUNT) is the same for every
    question - see those constants' comment for why a length-based proxy for "does this question
    need a wider pool" was tried first and replaced. Exact-match and academic_reference retrieval
    are untouched - only the legal_text semantic branch is affected by pool width.
    """
    dieu_number = detect_dieu_number(question)
    source_document = detect_source_document(question) if dieu_number else None
    exact_chunks = _retrieve_legal_exact(client, collection, dieu_number, source_document) if dieu_number else []

    semantic_chunks = _retrieve_semantic(client, collection, vector, "legal_text", LEGAL_SEMANTIC_TOP_K)

    merged = _dedup_by_point_id(exact_chunks + semantic_chunks)
    above_threshold = [c for c in merged if c.is_exact_match or (c.score or 0.0) >= LEGAL_SCORE_THRESHOLD]

    # Group by (dieu_number, law_version) rather than slicing the flat chunk list, so a long
    # Dieu split into several Khoan chunks (see ingestion/chunking.py) counts as ONE Dieu
    # towards primary_count instead of eating multiple primary slots with itself.
    #
    # Diversity-aware selection (see MAX_PRIMARY_PER_SOURCE_DOCUMENT's comment): still walk
    # above_threshold in the SAME score order as before (a single source's own internal ranking
    # is untouched), but once a source_document has filled its per-source cap, further Dieu from
    # that SAME source are deferred rather than immediately consuming a primary slot - giving a
    # competitive Dieu from a DIFFERENT source room to be picked up first. Deferred keys backfill
    # any slots still empty after one full pass, so a question that genuinely has no competing
    # source in the pool (e.g. asking broadly about one specific Thông tư/Nghị định) still fills
    # up to LEGAL_PRIMARY_COUNT instead of being short-changed by a cap with nothing to trade off
    # against - the cap is a tie-breaker among competing sources, not a hard ceiling.
    primary_keys_ordered: list[tuple[str, str | None]] = []
    deferred_keys: list[tuple[str, str | None]] = []
    seen_keys: set[tuple[str, str | None]] = set()
    source_counts: dict[str, int] = {}
    for chunk in above_threshold:
        key = (chunk.payload["dieu_number"], chunk.payload["law_version"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        source_document = chunk.payload["source_document"]
        if (len(primary_keys_ordered) < LEGAL_PRIMARY_COUNT
                and source_counts.get(source_document, 0) < MAX_PRIMARY_PER_SOURCE_DOCUMENT):
            primary_keys_ordered.append(key)
            source_counts[source_document] = source_counts.get(source_document, 0) + 1
        else:
            deferred_keys.append(key)
    if len(primary_keys_ordered) < LEGAL_PRIMARY_COUNT:
        primary_keys_ordered.extend(deferred_keys[:LEGAL_PRIMARY_COUNT - len(primary_keys_ordered)])
    primary_keys = set(primary_keys_ordered[:LEGAL_PRIMARY_COUNT])

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


def _answer_leaks_real_name(answer_text: str, anonymized_names: list[str]) -> bool:
    """requirements.md muc C's absolute constraint (never repeat the real name, even indirectly)
    is enforced at two independent layers: RAG_ANONYMIZATION_ADDENDUM (instruction-level) and this
    check (code-level, fail-closed) - a plain case-insensitive substring match against every name
    query_understanding_service flagged as replaced is a blunt tool, but it's a reliable one for
    the concrete failure mode this guards against (the model recognizing and volunteering the real
    name/nickname despite being told not to), and false positives here only cost a safe generic
    fallback answer rather than ever letting a real name pass through."""
    lowered = answer_text.lower()
    return any(name.lower() in lowered for name in anonymized_names if name)


def _extract_cited_dieu_numbers(answer_text: str) -> set[str]:
    """RAG_SYSTEM_PROMPT rule 2 requires the model to name a legal_text citation as "Theo Dieu
    [so] [ten van ban]..." - reusing DIEU_NUMBER_PATTERN (built for detecting a Dieu number in
    the student's question) against the generated answer instead lets us tell which retrieved
    legal_primary chunks were actually used vs merely retrieved."""
    return {match.group(1) for match in DIEU_NUMBER_PATTERN.finditer(answer_text)}


def _rule9_allowed_dieu_numbers(legal_primary: list[RetrievedChunk]) -> set[str]:
    """RAG_SYSTEM_PROMPT rule 9's "danh sach so Dieu duoc phep neu" - the union of (a) each
    legal_primary chunk's own dieu_number (its block-title Dieu) and (b) any Dieu number
    appearing anywhere INSIDE that chunk's own retrieved text (a real legal_text Dieu routinely
    cross-references other Dieu numbers in its own body, e.g. Dieu 155 BLTTHS: "toi pham quy dinh
    tai khoan 1 cac dieu 134, 135, 136..." - quoting those back is legitimate, not the rule 9
    violation this exists to catch). Mirrors evaluation/run_evaluation.py's
    _compute_allowed_dieu_numbers exactly - see that function's docstring for how this
    distinction was found (2/3 first-pass "violations" during the eval script's own build were
    false positives from checking block-title Dieu alone)."""
    allowed: set[str] = set()
    for chunk in legal_primary:
        allowed.add(chunk.payload["dieu_number"])
        allowed.update(m.group(1) for m in DIEU_NUMBER_PATTERN.finditer(chunk.payload["chunk_text"]))
    return allowed


def _rule9_ungrounded_dieu_numbers(answer_text: str, legal_primary: list[RetrievedChunk]) -> list[str]:
    """Code-level audit for RAG_SYSTEM_PROMPT rule 9 (requirements.md investigation - confirmed
    via the official eval suite that the model occasionally leaks a Dieu number that only appears
    inside an academic_reference chunk's own text, e.g. citing "Dieu 298 BLTTHS" when only Dieu
    298's *mention inside an academic passage* was ever retrieved, never Dieu 298's own legal_text
    block). Used two ways in stream_answer_question: as a fail-closed pre-send check on the
    selective-buffer path (buffer_for_rule9_risk - 20/20 repeated violations measured even with a
    strengthened rule 9 prompt forced this from log-only to a real guard, see requirements.md), and
    as a log-only check (persisted via RagAnswer.rule9_ungrounded_dieu_numbers -> chat_query_logs)
    on the ordinary streamed path, where the answer has already reached the client by the time this
    runs and buffering ALL legal_question traffic isn't justified by the measured risk there."""
    mentioned = _extract_cited_dieu_numbers(answer_text)
    allowed = _rule9_allowed_dieu_numbers(legal_primary)
    return sorted(mentioned - allowed)


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


async def retrieve_context_for_subquestions(
    sub_questions: list[str], settings: Settings, qdrant_client: QdrantClient
) -> list[RetrievalResult]:
    """requirements.md "Viec 3" Buoc 2 (tach cau hoi nhieu chu de truoc khi retrieval) - calls
    retrieve_context() INDEPENDENTLY for each sub-question (its own embed_query call, its own
    top_k=25/primary_count=8/diversity-aware selection, completely unchanged from the single-
    question path) instead of embedding the whole multi-topic message as one vector. This is what
    mục A/B's investigation showed fixes the "embedding dilution" root cause: a Dieu that ranks #1
    when its own sub-question is embedded alone gets crowded out to rank in the hundreds when
    embedded together with 5 other unrelated sub-questions in the same vector (see requirements.md
    for the measured rank comparison). Concurrent via asyncio.gather, same pattern as the two
    concurrent calls inside retrieve_context itself - N sub-questions costs N embed+Qdrant round
    trips, but they overlap in wall-clock time rather than serializing.

    Buoc 1+2 ONLY (per requirements.md staging) - returns the list of independent RetrievalResult,
    one per sub-question, in the same order as `sub_questions`. Deliberately NOT wired into
    stream_answer_question yet: merging these into one generation call with per-part context
    labeling is Buoc 3, a separate, not-yet-built step so this increment stays independently
    reviewable/testable.
    """
    return list(await asyncio.gather(
        *(retrieve_context(sub_question, settings, qdrant_client) for sub_question in sub_questions)
    ))


async def stream_answer_question(
    question: str, conversation_id: uuid.UUID, settings: Settings, qdrant_client: QdrantClient, result: RagAnswer,
    recent_turns: list[dict[str, str]] | None = None, intent: str = "legal_question",
    last_turn: dict[str, Any] | None = None, needs_anonymization: bool = False,
    anonymized_names: list[str] | None = None
) -> AsyncIterator[tuple[str, ChatStreamCitationsEvent | ChatStreamAnswerDeltaEvent |
                          ChatStreamGradingEvent | ChatStreamSuggestedFollowupsEvent | ChatStreamDoneEvent]]:
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

    `intent` (query_understanding_service.rewrite_question's own classification, computed by the
    caller BEFORE this function runs - requirements.md muc E, extended by the "Mở rộng phân loại ý
    định Query Understanding" feature and again by "Sinh tình huống minh họa" Lượt 1/2 to 6 values)
    short-circuits 5 of its 6 possible values straight past retrieval/generation, all in this same
    shape (citations event -> single answer_delta -> empty suggested_followups -> done), except
    answer_evaluation which additionally emits a grading_result event between the two:
    - "out_of_scope": the refusal answer (unchanged behavior from muc E) - a question already
      classified as unrelated to Luat To tung Hinh su has nothing for retrieval/generation to
      usefully do, and skipping both avoids a malformed/off-topic query string reaching either.
    - "greeting": one of GREETING_TEMPLATES, picked at random - no LLM call at all, cheapest and
      fastest path possible, same short-circuit spirit as out_of_scope.
    - "summarize_previous": one lightweight LLM call constrained to `last_turn`'s own answer text
      (see SUMMARIZE_SYSTEM_PROMPT) - never touches retrieval, and reuses `last_turn`'s own
      citations verbatim (no recomputation) since the underlying legal content hasn't changed,
      only its presentation. `last_turn` is None when this is the first message of the
      conversation (nothing to summarize yet - see NO_PREVIOUS_ANSWER_MESSAGE).
    - "explain_simpler": same shape as summarize_previous (one lightweight LLM call constrained to
      `last_turn`'s own answer, reuses its citations verbatim, same None-first-turn guard) but a
      DIFFERENT prompt (EXPLAIN_SIMPLER_SYSTEM_PROMPT) optimized for easier-to-understand rather
      than shorter - split out as its own intent because summarize_previous's length-constrained
      prompt was mechanically shortening "tôi không hiểu, giải thích đơn giản hơn" requests instead
      of reducing jargon/adding examples (see requirements.md UAT investigation).
    - "request_scenario": one LLM call (scenario_service.generate_scenario) grounded ONLY in
      `recent_turns` (no retrieval - reuses whatever Điều luật was already discussed) that
      produces a visible fictional scenario AND a hidden key_points rubric. Only the scenario text
      goes into `result.answer`/the SSE stream; `result.scenario_key_points` carries the rubric
      for chat_log_service.log_chat_query to persist for Lượt 2 grading (not built yet) - it must
      never be sent to the client (same "logged, not served" precedent as is_fallback/
      retrieved_chunks above). Falls back to NO_SCENARIO_CONTEXT_MESSAGE when there's no prior
      conversation turn, or when generate_scenario itself reports nothing to illustrate.
    - "answer_evaluation": one LLM call (scenario_grading_service.grade_scenario_answer) grading
      `question` (the student's analysis) against `last_turn["scenario_key_points"]` - the hidden
      rubric request_scenario saved on the immediately preceding turn. Only reachable when that
      rubric actually exists: query_understanding_service.rewrite_question already hard-downgrades
      this intent to legal_question otherwise (see that module), so `last_turn` and its rubric are
      trusted here, with a defensive NO_SCENARIO_TO_GRADE_MESSAGE fallback if that invariant is
      ever violated. `result.answer` carries only the qualitative "feedback" sentence (no
      score/percentage - requirements.md's core philosophy for this whole feature line); the
      matched/missing points go out ONLY in the grading_result event, never persisted back to
      chat_query_logs (grading is terminal - nothing downstream needs to re-read it).
    Only "legal_question" (the default) falls through to the retrieval/generation pipeline below.

    `needs_anonymization`/`anonymized_names` (requirements.md muc C, only ever true alongside
    intent="legal_question" - query_understanding_service.rewrite_question already forces both to
    False/[] for every other intent) mean `question` here has already had every real name replaced
    by an A/B/C label before it ever reached retrieval. Generation for this case is BUFFERED rather
    than token-streamed to the client (unlike the normal legal_question path just below it) so the
    complete answer can be leak-checked against `anonymized_names` (_answer_leaks_real_name) and
    have ANONYMIZATION_DISCLAIMER appended in code - both BEFORE anything reaches the client -
    trading true streaming latency for the "never repeat the real name" guarantee on this
    intentionally rare path.

    RAG_SYSTEM_PROMPT rule 9 grounding audit (requirements.md): the same buffer-then-check trade-
    off is applied, on top of `needs_anonymization`, to any question whose retrieval used
    academic_reference (`buffer_for_rule9_risk` below) - measured via 20 repeated runs of a known
    eval-suite question that a strengthened rule 9 prompt alone did NOT stop the model from citing
    a Dieu number leaked from academic_reference text (20/20 violations, well past the >10-15%
    threshold that was pre-agreed to require a code-level guard instead of a prompt-only fix). See
    _rule9_ungrounded_dieu_numbers's docstring for the fail-closed vs log-only split.
    """
    if intent == "out_of_scope":
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

    if intent == "greeting":
        answer_text = random.choice(GREETING_TEMPLATES)
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

    if intent == "summarize_previous":
        if last_turn is None:
            answer_text = NO_PREVIOUS_ANSWER_MESSAGE
            citations: list[Citation] = []
        else:
            try:
                summary_response = await asyncio.to_thread(
                    generate_answer, SUMMARIZE_SYSTEM_PROMPT,
                    build_summarize_prompt(last_turn["answer"], question), settings
                )
                answer_text = summary_response.strip() or last_turn["answer"]
            except Exception:
                # A broken summarize call must never break the whole chat request - fall back to
                # showing the original (unsummarized) answer rather than erroring out, same
                # resilience pattern as query_understanding_service.rewrite_question's own fallback.
                logger.exception("summarize_previous call failed - falling back to the original answer")
                answer_text = last_turn["answer"]
            citations = [Citation(**c) for c in last_turn["citations"]]
        result.answer = answer_text
        result.citations = citations
        result.related_articles = []
        result.suggested_followups = []
        result.is_fallback = False
        result.used_academic_reference = False
        result.retrieved_chunks = []
        yield ("citations", ChatStreamCitationsEvent(
            citations=citations, related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
        yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=[]))
        yield ("done", ChatStreamDoneEvent())
        return

    if intent == "explain_simpler":
        if last_turn is None:
            answer_text = NO_PREVIOUS_ANSWER_FOR_EXPLAIN_MESSAGE
            citations = []
        else:
            try:
                explain_response = await asyncio.to_thread(
                    generate_answer, EXPLAIN_SIMPLER_SYSTEM_PROMPT,
                    build_explain_simpler_prompt(last_turn["answer"], question), settings
                )
                answer_text = explain_response.strip() or last_turn["answer"]
            except Exception:
                # A broken explain_simpler call must never break the whole chat request - fall
                # back to showing the original answer rather than erroring out, same resilience
                # pattern as summarize_previous above.
                logger.exception("explain_simpler call failed - falling back to the original answer")
                answer_text = last_turn["answer"]
            citations = [Citation(**c) for c in last_turn["citations"]]
        result.answer = answer_text
        result.citations = citations
        result.related_articles = []
        result.suggested_followups = []
        result.is_fallback = False
        result.used_academic_reference = False
        result.retrieved_chunks = []
        yield ("citations", ChatStreamCitationsEvent(
            citations=citations, related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
        yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=[]))
        yield ("done", ChatStreamDoneEvent())
        return

    if intent == "request_scenario":
        scenario_key_points: list[str] | None = None
        if not recent_turns:
            answer_text = NO_SCENARIO_CONTEXT_MESSAGE
        else:
            try:
                scenario_result = await asyncio.to_thread(generate_scenario, recent_turns, question, settings)
            except Exception:
                # A broken scenario call must never break the whole chat request - same
                # resilience pattern as summarize_previous above.
                logger.exception("request_scenario call failed - falling back to no-context message")
                scenario_result = None
            if scenario_result is None or not scenario_result.scenario:
                answer_text = NO_SCENARIO_CONTEXT_MESSAGE
            else:
                answer_text = scenario_result.scenario
                scenario_key_points = scenario_result.key_points
        result.answer = answer_text
        result.citations = []
        result.related_articles = []
        result.suggested_followups = []
        result.is_fallback = scenario_key_points is None
        result.used_academic_reference = False
        result.retrieved_chunks = []
        result.scenario_key_points = scenario_key_points
        yield ("citations", ChatStreamCitationsEvent(
            citations=[], related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
        yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=[]))
        yield ("done", ChatStreamDoneEvent())
        return

    if intent == "answer_evaluation":
        # last_turn["scenario_key_points"] is trusted here - query_understanding_service already
        # hard-downgraded this intent to legal_question if it were missing (see that module's
        # rewrite_question). The `or []` defensive fallback below only matters if that invariant
        # is ever violated (e.g. a future bug), never in the normal path.
        key_points: list[str] = (last_turn or {}).get("scenario_key_points") or []
        scenario_text: str = (last_turn or {}).get("answer") or ""
        grading = None
        if key_points and scenario_text:
            try:
                grading = await asyncio.to_thread(grade_scenario_answer, scenario_text, key_points, question, settings)
            except Exception:
                # A broken grading call must never break the whole chat request - same resilience
                # pattern as summarize_previous/request_scenario above.
                logger.exception("answer_evaluation call failed - falling back to no-context message")
        if grading is None:
            answer_text = NO_SCENARIO_TO_GRADE_MESSAGE
            matched_points: list[str] = []
            missing_points: list[str] = []
            missing_points_display: list[str] | None = None
        else:
            answer_text = grading.feedback
            matched_points = grading.matched
            missing_points = grading.missing
            missing_points_display = grading.missing_points_display
        result.answer = answer_text
        result.citations = []
        result.related_articles = []
        result.suggested_followups = []
        result.is_fallback = grading is None
        result.used_academic_reference = False
        result.retrieved_chunks = []
        result.scenario_key_points = None
        yield ("citations", ChatStreamCitationsEvent(
            citations=[], related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
        yield ("grading_result", ChatStreamGradingEvent(
            matched_points=matched_points, missing_points=missing_points,
            missing_points_display=missing_points_display
        ))
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
    system_prompt = build_system_prompt(is_long_question, needs_anonymization=needs_anonymization)
    generation_model = settings.resolved_complex_chat_model if is_long_question else settings.gemini_chat_model
    fallback_model = settings.gemini_chat_model if is_long_question else None
    first_token_timeout = LONG_QUESTION_FIRST_TOKEN_TIMEOUT_SECONDS if is_long_question else None

    # requirements.md RAG_SYSTEM_PROMPT rule 9 grounding audit: buffer generation (instead of
    # token-streaming live) for questions whose retrieval used academic_reference - measured via
    # 20 repeated runs of a real eval-suite question that a legal_primary chunks and an expanded
    # rule 9 prompt did NOT stop the model from leaking a Dieu number that only appeared inside an
    # academic_reference chunk's own text (20/20 violations even with legal_primary non-empty and
    # substantial - "weak/no legal_primary" is NOT the actual risk signal, used_academic_reference
    # is). Buffering here (same trade-off already accepted for needs_anonymization below) lets the
    # fail-closed check run BEFORE anything reaches the client, on exactly the subset of questions
    # that actually needs it - direct-citation/legal_text-only questions (the majority of traffic)
    # keep true live token streaming, unaffected.
    buffer_for_rule9_risk = retrieval.used_academic_reference and not needs_anonymization

    # requirements.md muc C: needs_anonymization buffers the whole answer instead of forwarding
    # each token as it arrives (unlike the normal path) so the leak check + disclaimer below can
    # run BEFORE anything reaches the client - see this function's docstring.
    answer_parts: list[str] = []
    async for text_chunk in stream_generate_answer(
        system_prompt, user_prompt, settings, model=generation_model,
        fallback_model=fallback_model, first_token_timeout=first_token_timeout
    ):
        answer_parts.append(text_chunk)
        if not (needs_anonymization or buffer_for_rule9_risk):
            yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=text_chunk))

    answer_text = "".join(answer_parts)
    leaked_real_name = False
    rule9_fail_closed = False
    rule9_ungrounded_before_fail_closed: list[str] = []

    if needs_anonymization:
        if answer_text and not _is_fallback_answer(answer_text):
            if _answer_leaks_real_name(answer_text, anonymized_names or []):
                logger.warning(
                    "Anonymized generation still named a real person from anonymized_names - "
                    "failing closed to the generic safe-answer fallback"
                )
                answer_text = ANONYMIZATION_LEAK_FALLBACK_ANSWER
                leaked_real_name = True
            else:
                answer_text = f"{answer_text.rstrip()}\n\n{ANONYMIZATION_DISCLAIMER}"
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
    elif buffer_for_rule9_risk:
        if answer_text and not _is_fallback_answer(answer_text):
            rule9_ungrounded_before_fail_closed = _rule9_ungrounded_dieu_numbers(answer_text, retrieval.legal_primary)
            if rule9_ungrounded_before_fail_closed:
                logger.warning(
                    "RAG_SYSTEM_PROMPT rule 9 violation caught pre-send: answer cited Dieu %s not "
                    "grounded in any retrieved legal_text chunk - failing closed to the generic "
                    "safe-answer fallback (question=%r)", rule9_ungrounded_before_fail_closed, question
                )
                answer_text = RULE9_VIOLATION_FALLBACK_ANSWER
                rule9_fail_closed = True
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))
    # Same trust-the-model's-own-refusal reasoning as the old answer_question: the retrieval
    # threshold is intentionally lenient (see LEGAL_SCORE_THRESHOLD), so weakly-related chunks
    # sometimes get passed as context even though none of them actually answer the question -
    # when the model refuses anyway, clear citations/related_articles so the final logged/served
    # answer never shows "sources" for a response that admits it found nothing relevant. A leaked-
    # name safety fallback (leaked_real_name) or a rule 9 fail-closed replacement counts as a
    # fallback too, for the same reason, even though their wording doesn't match
    # _is_fallback_answer's usual "not found" phrase.
    is_fallback = leaked_real_name or rule9_fail_closed or _is_fallback_answer(answer_text)

    # Restrict citations to the legal_primary chunks the model actually cited (per the system
    # prompt's rule 2, a legal_text citation always names its Dieu as "Theo Dieu [so]...") rather
    # than every chunk that merely passed retrieval threshold - see the module-level docstring's
    # "BUG PHAT HIEN SAU" reference for why a high-scoring legal_primary chunk isn't necessarily
    # one the model actually used.
    cited_dieu_numbers = _extract_cited_dieu_numbers(answer_text)
    actually_cited_primary = [c for c in retrieval.legal_primary if c.payload["dieu_number"] in cited_dieu_numbers]
    # citations is intentionally NOT gated on is_fallback (unlike related_articles below) -
    # requirements.md muc B investigation: a compound multi-part answer (several sub-questions in
    # one message) can correctly cite a Dieu for one part while ANOTHER part refuses with the
    # fallback phrase - _is_fallback_answer's whole-text substring check can't tell those apart,
    # so gating citations on it wiped out a legitimately-cited Dieu (e.g. Dieu 174) just because a
    # different part of the same answer happened to also contain "khong tim thay noi dung lien
    # quan". actually_cited_primary is already extraction-based (only Dieu the model's own text
    # names via "Theo Dieu [so]...") so a genuine single-topic refusal naturally yields an empty
    # list here anyway - this only changes behavior for the compound-answer case it's meant to fix.
    citations = _build_citations(actually_cited_primary)
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

    # requirements.md RAG_SYSTEM_PROMPT rule 9 grounding audit: reuse the pre-fail-closed result
    # for the buffered path (the answer text has already been replaced by the time we'd re-check
    # it here, so re-running the check would always find nothing) - needs_anonymization's path
    # never generates a legal_text-cited answer worth checking (question is about an anonymized
    # scenario, not a Dieu lookup), and the plain-streamed path is checked fresh here since it was
    # never buffered/checked before reaching the client (log-only monitoring, not a guard - see
    # _rule9_ungrounded_dieu_numbers's docstring).
    if buffer_for_rule9_risk:
        rule9_ungrounded = rule9_ungrounded_before_fail_closed
    elif needs_anonymization:
        rule9_ungrounded = []
    else:
        rule9_ungrounded = _rule9_ungrounded_dieu_numbers(answer_text, retrieval.legal_primary) if not is_fallback else []
        if rule9_ungrounded:
            logger.warning(
                "RAG_SYSTEM_PROMPT rule 9 violation detected post-stream (already sent to client): "
                "answer cited Dieu %s not grounded in any retrieved legal_text chunk "
                "(question=%r)", rule9_ungrounded, question
            )

    result.answer = answer_text
    result.citations = citations
    result.related_articles = related_articles
    result.suggested_followups = suggested_followups
    result.is_fallback = is_fallback
    result.used_academic_reference = (not is_fallback) and retrieval.used_academic_reference
    result.rule9_ungrounded_dieu_numbers = rule9_ungrounded

    yield ("suggested_followups", ChatStreamSuggestedFollowupsEvent(suggested_followups=suggested_followups))
    yield ("done", ChatStreamDoneEvent())
