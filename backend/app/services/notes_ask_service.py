"""Vở ghi Giai đoạn 2 - "Hỏi AI trên đoạn được chọn" (POST /api/notes/ask).

The student selects a passage in their own notes and asks a question about it. The passage is
unreviewed, student-written text, so it is treated the way the note-era Chat integration learned
to treat it (see RAG_USER_PASSAGE_ADDENDUM's comment), with the same layers:

1. Retrieval runs on the question PLUS the passage, so legal_primary holds the Dieu the passage is
   actually about - which is what a contradiction has to be checked against.
2. Every "Dieu N" in the passage whose N is not in rule 9's allowed list for that legal_primary is
   masked BEFORE the prompt (rag_service._mask_unverified_dieu_numbers): the model cannot echo a
   made-up number it never saw.
3. The passage sits in a delimited block that the addendum declares to be data, never instructions
   (prompt injection), and the question comes last, outside it.
4. Generation is ALWAYS buffered - nothing reaches the client until two fail-closed guards pass:
   rule 9 (every Dieu the answer names must be grounded in legal_primary) and passage echo (the
   answer must not copy a long verbatim run of the passage). Unlike Chat, there is no streamed
   path here: Chat buffers only when academic_reference was used, but on this path every request
   carries extra unreviewed text, and the echo guard can only be enforced on a complete answer.

The passage is never stored and never logged - only its length (request telemetry). The turn is
stored in chat_query_logs with source='notes' (question as typed, the answer, citations), never the
passage itself.

Not run through query understanding: the question is usually only meaningful together with the
passage ("đoạn này đúng không?"), which the rewrite step never sees, and its intent short-circuits
(greeting, request_scenario, ...) are Chat features this page does not have.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

from qdrant_client import QdrantClient

from app.core import request_telemetry as telemetry
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.chat import (
    ChatStreamAnswerDeltaEvent,
    ChatStreamCitationsEvent,
    ChatStreamDoneEvent,
    ChatStreamStatusEvent,
)
from app.prompts.rag_prompts import (
    PASSAGE_ECHO_FALLBACK_ANSWER,
    RULE9_VIOLATION_FALLBACK_ANSWER,
    build_passage_user_prompt,
    build_system_prompt,
    format_passage_block,
)
from app.services.gemini_client import stream_generate_answer
from app.services.rag_service import (
    FALLBACK_ANSWER,
    LONG_QUESTION_CHAR_THRESHOLD,
    LONG_QUESTION_FIRST_TOKEN_TIMEOUT_SECONDS,
    STATUS_CROSS_CHECKING,
    STATUS_RETRIEVING,
    UNVERIFIED_PASSAGE_DIEU_PLACEHOLDER,
    RagAnswer,
    _build_citations,
    _build_related_articles,
    _extract_cited_dieu_numbers,
    _is_fallback_answer,
    _mask_unverified_dieu_numbers,
    _rule9_allowed_dieu_numbers,
    _rule9_ungrounded_dieu_numbers,
    retrieve_context,
)

logger = get_logger(__name__)

# The addendum asks for a quote of at most ~200 characters; this is the hard line, with headroom so
# a quote that runs slightly long is not thrown away. Any verbatim run of the passage at least this
# long (after whitespace/case normalisation) fails the answer closed. Consequence worth knowing: a
# passage SHORTER than this can legitimately be quoted whole by the contradiction template; a
# longer one can never appear whole in an answer, and therefore never in chat_query_logs.answer.
PASSAGE_ECHO_LIMIT_CHARS = 250

_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()


def answer_echoes_passage(answer_text: str, passage: str, limit: int = PASSAGE_ECHO_LIMIT_CHARS) -> bool:
    """True when `answer_text` contains a verbatim run of `passage` at least `limit` characters
    long. Slides a `limit`-wide window across the passage, one character at a time, and asks
    whether the answer contains it - at most ~3000 C-level substring searches over a few thousand
    characters, so milliseconds, and exact rather than a similarity heuristic."""
    answer_n, passage_n = _normalise(answer_text), _normalise(passage)
    if len(passage_n) < limit or len(answer_n) < limit:
        return False
    return any(passage_n[i:i + limit] in answer_n for i in range(len(passage_n) - limit + 1))


def build_retrieval_query(question: str, passage: str) -> str:
    """Question first, then the passage. detect_dieu_number takes the first "Dieu N" it finds, so a
    Dieu the student names in the question wins the exact-match slot over one the passage names."""
    return f"{question}\n\n{passage}"


async def stream_answer_about_passage(
    question: str, passage: str, conversation_id: uuid.UUID, settings: Settings,
    qdrant_client: QdrantClient, result: RagAnswer, recent_turns: list[dict[str, str]] | None = None,
) -> AsyncIterator[tuple[str, ChatStreamStatusEvent | ChatStreamAnswerDeltaEvent |
                          ChatStreamCitationsEvent | ChatStreamDoneEvent]]:
    """Yields (event_name, payload): status (retrieving) -> status (cross-checking) -> answer_delta
    (exactly one - the answer is buffered) -> citations -> done. The no-context case yields
    citations (empty) before its single answer_delta, as Chat's does. `result` is mutated in place
    for the route to store after the stream ends, as with rag_service.stream_answer_question.

    Log lines here carry Dieu numbers and counts only - never the question, the passage or the
    answer (Chat's own rule 9 warnings quote the question; this path does not)."""
    telemetry.set_path("notes_buffer")
    yield ("status", ChatStreamStatusEvent(message=STATUS_RETRIEVING))
    with telemetry.stage("retrieval"):
        retrieval = await retrieve_context(build_retrieval_query(question, passage), settings, qdrant_client)
    result.retrieved_chunks = retrieval.all_retrieved

    if not retrieval.context_blocks:
        logger.info("Notes ask: no context passed threshold, returning fallback answer")
        telemetry.set_path("short_circuit:no_context")
        telemetry.set_answer_flags(is_fallback=True)
        result.answer = FALLBACK_ANSWER
        result.is_fallback = True
        result.used_academic_reference = False
        result.rule9_ungrounded_dieu_numbers = []
        yield ("citations", ChatStreamCitationsEvent(
            citations=[], related_articles=[], conversation_id=conversation_id, rewritten_question=question
        ))
        yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=FALLBACK_ANSWER))
        yield ("done", ChatStreamDoneEvent())
        return

    allowed = _rule9_allowed_dieu_numbers(retrieval.legal_primary)
    masked_passage = _mask_unverified_dieu_numbers(passage, allowed)
    telemetry.set_passage_masked_dieu(masked_passage.count(UNVERIFIED_PASSAGE_DIEU_PLACEHOLDER))

    user_prompt = build_passage_user_prompt(
        question, retrieval.context_blocks, format_passage_block(masked_passage), recent_turns
    )
    # Long = the QUESTION is long, not question + passage: a 3000-character passage would otherwise
    # route every request to the slower complex model and its step-by-step addendum, which exist
    # for multi-actor tình huống questions.
    is_long_question = len(question) > LONG_QUESTION_CHAR_THRESHOLD
    system_prompt = build_system_prompt(is_long_question, user_passage=True)
    generation_model = settings.resolved_complex_chat_model if is_long_question else settings.gemini_chat_model
    fallback_model = settings.gemini_chat_model if is_long_question else None
    first_token_timeout = LONG_QUESTION_FIRST_TOKEN_TIMEOUT_SECONDS if is_long_question else None

    yield ("status", ChatStreamStatusEvent(message=STATUS_CROSS_CHECKING))
    answer_parts: list[str] = []
    with telemetry.stage("generation"):
        async for text_chunk in stream_generate_answer(
            system_prompt, user_prompt, settings, model=generation_model,
            fallback_model=fallback_model, first_token_timeout=first_token_timeout
        ):
            answer_parts.append(text_chunk)
    answer_text = "".join(answer_parts)

    guard_fail_closed = False
    rule9_ungrounded: list[str] = []
    if answer_text and not _is_fallback_answer(answer_text):
        rule9_ungrounded = _rule9_ungrounded_dieu_numbers(answer_text, retrieval.legal_primary)
        if rule9_ungrounded:
            logger.warning("Notes ask: rule 9 violation caught pre-send - answer cited Dieu %s not "
                           "grounded in legal_primary; failing closed", rule9_ungrounded)
            answer_text = RULE9_VIOLATION_FALLBACK_ANSWER
            guard_fail_closed = True
            telemetry.set_answer_flags(guard_tripped="rule9_notes")
        elif answer_echoes_passage(answer_text, masked_passage):
            logger.warning("Notes ask: answer copied >= %d characters of the passage verbatim; "
                           "failing closed", PASSAGE_ECHO_LIMIT_CHARS)
            answer_text = PASSAGE_ECHO_FALLBACK_ANSWER
            guard_fail_closed = True
            telemetry.set_answer_flags(guard_tripped="passage_echo")

    is_fallback = guard_fail_closed or _is_fallback_answer(answer_text)
    cited_dieu_numbers = _extract_cited_dieu_numbers(answer_text)
    actually_cited_primary = [c for c in retrieval.legal_primary if c.payload["dieu_number"] in cited_dieu_numbers]
    citations = _build_citations(actually_cited_primary)
    related_articles = [] if is_fallback else _build_related_articles(retrieval.legal_related)

    yield ("answer_delta", ChatStreamAnswerDeltaEvent(delta=answer_text))

    result.answer = answer_text
    result.citations = citations
    result.related_articles = related_articles
    result.suggested_followups = []
    result.is_fallback = is_fallback
    result.used_academic_reference = (not is_fallback) and retrieval.used_academic_reference
    result.rule9_ungrounded_dieu_numbers = rule9_ungrounded
    telemetry.set_answer_flags(is_fallback=is_fallback)

    yield ("citations", ChatStreamCitationsEvent(
        citations=citations, related_articles=related_articles,
        conversation_id=conversation_id, rewritten_question=question
    ))
    yield ("done", ChatStreamDoneEvent())
