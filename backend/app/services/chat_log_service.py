"""Persists every chat query + retrieved chunks + answer into Postgres (Supabase table
chat_query_logs, see migrations/0001_chat_query_logs.sql) for Phase 9 evaluation - citation
accuracy, groundedness, and correct-refusal rate all need the retrieved chunks, not just the
final answer text.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from app.core.data_access import DataUnavailable, execute_with_retry
from app.core.logging import get_logger
from app.services.rag_service import RagAnswer, RetrievedChunk

logger = get_logger(__name__)

CHAT_QUERY_LOGS_TABLE = "chat_query_logs"
# How many prior turns of the SAME conversation feed into query rewriting + the final answer
# prompt - deliberately small per requirements.md Phase 4 Extension ("khong phai toan bo lich
# su") to avoid token bloat on long conversations.
RECENT_TURNS_LIMIT = 3

# Phase 4 Extension 2: the Sidebar's "title" for a conversation is its first question, possibly
# long - truncated here so the list view stays a clean chip/row, not a full sentence.
CONVERSATION_TITLE_MAX_LENGTH = 60

# Which page a row came from - migrations/0011_chat_query_logs_source.sql. Chat reads only 'chat'
# rows, the Vở ghi passage-ask (api/notes.py) only 'notes' rows, so neither surface ever shows the
# other's turns as its own history.
SOURCE_CHAT = "chat"
SOURCE_NOTES = "notes"

# How PostgREST reports a column it does not know: 42703 (Postgres undefined_column) when a filter
# or select names it, PGRST204 when an insert body does.
_MISSING_COLUMN_CODES = frozenset({"42703", "PGRST204"})


def _is_missing_source_column(error: BaseException) -> bool:
    """True when `error` (or the error a DataUnavailable wraps) says the `source` column does not
    exist - i.e. the code is deployed but migration 0011 has not been run yet."""
    cause = error.__cause__ if isinstance(error, DataUnavailable) else error
    return (isinstance(cause, APIError) and cause.code in _MISSING_COLUMN_CODES
            and "source" in (cause.message or ""))


def _execute_filtered_by_source(build_query: Callable[[bool], Any], what: str) -> Any:
    """Runs `build_query(True)` (the query WITH its .eq("source", ...) filter). If that fails only
    because migration 0011 has not been applied, runs `build_query(False)` instead: without the
    column no 'notes' row can exist yet (log_chat_query refuses to write one), so the unfiltered
    query returns exactly the rows the filtered one would. Not cached - the moment the migration is
    run, the very next read filters again, with no restart needed."""
    try:
        return execute_with_retry(lambda: build_query(True), what)
    except DataUnavailable as error:
        if not _is_missing_source_column(error):
            raise
        logger.warning("%s: chat_query_logs.source does not exist yet (migration 0011 not applied) "
                       "- reading without the source filter", what)
        return execute_with_retry(lambda: build_query(False), what)


def _with_source(query: Any, source: str, filtered: bool) -> Any:
    return query.eq("source", source) if filtered else query


def get_recent_turns(supabase_client: Client, user_id: str, conversation_id: uuid.UUID,
                     source: str = SOURCE_CHAT) -> list[dict[str, str]]:
    """Returns up to RECENT_TURNS_LIMIT prior turns of this conversation, oldest first, as
    {"question", "answer"} pairs - the rewritten_question (self-contained) is preferred over the
    raw question when available, since that's what the history should read like for the next
    rewrite/generation step.

    Raises DataUnavailable if the read still fails after one retry. It used to return [] instead,
    which silently answered a follow-up ("vậy nó có được gia hạn không?") as if it opened the
    conversation, with nothing pointing at what "nó" meant. Degrading is still the right call - a
    history outage must not cost the student the answer - but that decision now belongs to the
    caller (api/chat.py), which can also TELL the student their answer may lack context."""
    response = _execute_filtered_by_source(
        lambda filtered: _with_source(
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("question, rewritten_question, answer")
            .eq("user_id", user_id)
            .eq("conversation_id", str(conversation_id)), source, filtered)
        .order("created_at", desc=True)
        .limit(RECENT_TURNS_LIMIT),
        "read conversation history",
    )

    rows = list(reversed(response.data or []))
    return [{"question": row.get("rewritten_question") or row["question"], "answer": row["answer"]} for row in rows]


def get_last_assistant_turn(supabase_client: Client, user_id: str,
                             conversation_id: uuid.UUID, source: str = SOURCE_CHAT) -> dict[str, Any] | None:
    """Returns the most recently logged answer + its citations + hidden scenario rubric (if any)
    for this conversation, or None if this conversation has no prior turn yet. Used by:
    - intent=summarize_previous/explain_simpler (answer/citations - see rag_service.stream_answer_question)
    - intent=request_scenario/answer_evaluation gating (scenario_key_points - requirements.md
      "Sinh tình huống minh họa"): chat.py calls this UNCONDITIONALLY on every turn (not just when
      the intent is already known to need it) specifically so it can compute
      has_pending_scenario BEFORE query_understanding_service.rewrite_question runs, since that
      fact is part of what the classifier itself needs to decide intent - a chicken-and-egg
      requirement summarize_previous's original conditional fetch (fetched only after intent was
      already known) didn't have.

    Raises DataUnavailable on a read that still fails after one retry - same reasoning as
    get_recent_turns, and the same caller decides how to degrade.
    """
    response = _execute_filtered_by_source(
        lambda filtered: _with_source(
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("answer, citations, scenario_key_points")
            .eq("user_id", user_id)
            .eq("conversation_id", str(conversation_id)), source, filtered)
        .order("created_at", desc=True)
        .limit(1),
        "read last conversation turn",
    )

    rows = response.data or []
    if not rows:
        return None
    return {
        "answer": rows[0]["answer"],
        "citations": rows[0].get("citations") or [],
        "scenario_key_points": rows[0].get("scenario_key_points") or None,
    }


def _truncate_title(question: str) -> str:
    stripped = question.strip()
    if len(stripped) <= CONVERSATION_TITLE_MAX_LENGTH:
        return stripped
    return stripped[:CONVERSATION_TITLE_MAX_LENGTH].rstrip() + "…"


def list_conversations(supabase_client: Client, user_id: str) -> list[dict[str, Any]]:
    """Groups chat_query_logs rows by conversation_id, most-recently-updated first. Grouping is
    done in Python from one filtered select, not a Postgres GROUP BY/RPC - this codebase has no
    custom Postgres functions anywhere (see dashboard_service.py for the same aggregate-on-read
    pattern used for keywords/weak-topics), only the supabase-py fluent .table() client. Rows
    with conversation_id IS NULL (logged before migrations/0004_chat_multiturn.sql, or before a
    client ever attached one) are excluded - they predate the conversation concept and can't be
    grouped into one.

    Ownership: filtered by user_id in this same query (the backend uses the Supabase
    service-role key, which bypasses RLS - per migrations/0001 comments - so this explicit
    filter is the ONLY thing preventing one user's rows from leaking into another's list).

    Only source='chat' rows: a question asked inside Vở ghi (source='notes') is not a Chat
    conversation and must not appear in this sidebar.

    Raises DataUnavailable when the read fails. Returning [] - as this did until 2026-10-17 - made
    a student with fifty conversations look exactly like a brand-new account."""
    response = _execute_filtered_by_source(
        lambda filtered: _with_source(
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("conversation_id, question, created_at, title")
            .eq("user_id", user_id)
            .not_.is_("conversation_id", "null"), SOURCE_CHAT, filtered)
        .order("created_at", desc=False),
        "list conversations",
    )

    # Rows arrive oldest-first (asc), so the first time a conversation_id is seen its question
    # is the conversation's opening question (-> fallback title), and each subsequent sighting
    # keeps pushing updated_at forward to that conversation's latest turn. A custom title (see
    # migrations/0005_chat_conversation_title.sql) is denormalized onto every row of the
    # conversation by rename_conversation, so it can surface from whichever row has it set,
    # regardless of row order - but re-check on every sighting in case an older row predates the
    # rename and still has title IS NULL.
    grouped: dict[str, dict[str, Any]] = {}
    for row in response.data or []:
        conversation_id = row["conversation_id"]
        custom_title = row.get("title")
        if conversation_id not in grouped:
            grouped[conversation_id] = {
                "conversation_id": conversation_id,
                "title": custom_title or _truncate_title(row["question"]),
                "updated_at": row["created_at"],
            }
        else:
            grouped[conversation_id]["updated_at"] = row["created_at"]
            if custom_title:
                grouped[conversation_id]["title"] = custom_title

    conversations = list(grouped.values())
    conversations.sort(key=lambda c: c["updated_at"], reverse=True)
    return conversations


def get_conversation_detail(supabase_client: Client, user_id: str,
                             conversation_id: uuid.UUID) -> list[dict[str, Any]] | None:
    """Returns all turns of one conversation, oldest first, or None if it doesn't exist OR
    doesn't belong to this user - both cases are indistinguishable on purpose (404, not 403):
    ownership is enforced by filtering on user_id in the SAME query as conversation_id, so a
    nonexistent conversation_id and another user's real conversation_id both come back as an
    empty result here, never revealing to a caller that a given id belongs to someone else.

    Only source='chat' rows, for the same reason as list_conversations: a Vở ghi conversation id
    opened on the Chat page is "not found" there.

    None means "not found" and nothing else: a read that FAILS raises DataUnavailable instead. The
    two used to share None, so a database outage told the student their conversation did not
    exist."""
    response = _execute_filtered_by_source(
        lambda filtered: _with_source(
            supabase_client.table(CHAT_QUERY_LOGS_TABLE)
            .select("question, answer, created_at")
            .eq("user_id", user_id)
            .eq("conversation_id", str(conversation_id)), SOURCE_CHAT, filtered)
        .order("created_at", desc=False),
        "read conversation detail",
    )

    rows = response.data or []
    if not rows:
        return None

    return [{"question": row["question"], "answer": row["answer"], "created_at": row["created_at"]} for row in rows]


def delete_conversation(supabase_client: Client, user_id: str, conversation_id: uuid.UUID) -> bool:
    """Deletes every chat_query_logs row of this conversation and returns whether anything was
    actually deleted. SECURITY: same ownership pattern as get_conversation_detail - user_id and
    conversation_id are filtered in the SAME delete query, so a nonexistent conversation_id and
    another user's real conversation_id both delete 0 rows and return False here, letting the
    route 404 either way instead of ever confirming "that id belongs to someone else".

    False means "nothing matched" only; a delete that FAILS raises DataUnavailable. Safe to retry:
    deleting by the same id twice removes the same rows once."""
    response = execute_with_retry(
        lambda: supabase_client.table(CHAT_QUERY_LOGS_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("conversation_id", str(conversation_id)),
        "delete conversation",
    )

    return len(response.data or []) > 0


def rename_conversation(supabase_client: Client, user_id: str, conversation_id: uuid.UUID,
                         title: str | None) -> bool:
    """Sets (or clears, if title is None) the custom title on every row of this conversation and
    returns whether anything matched. Same ownership pattern as delete_conversation/
    get_conversation_detail - user_id + conversation_id filtered in the same update query, 0 rows
    matched (wrong owner or nonexistent) -> False -> route 404s.

    As with delete_conversation, a write that FAILS raises DataUnavailable rather than returning
    False. Safe to retry: setting the same title twice is the same as setting it once."""
    response = execute_with_retry(
        lambda: supabase_client.table(CHAT_QUERY_LOGS_TABLE)
        .update({"title": title})
        .eq("user_id", user_id)
        .eq("conversation_id", str(conversation_id)),
        "rename conversation",
    )

    return len(response.data or []) > 0


def _serialize_retrieved_chunk(chunk: RetrievedChunk) -> dict[str, Any]:
    payload = chunk.payload
    return {
        "point_id": chunk.point_id,
        "score": chunk.score,
        "is_exact_match": chunk.is_exact_match,
        "source_type": payload["source_type"],
        "source_document": payload["source_document"],
        "dieu_number": payload["dieu_number"],
        "khoan_number": payload["khoan_number"],
    }


def log_chat_query(supabase_client: Client, user_id: str, conversation_id: uuid.UUID, question: str,
                    rewritten_question: str, result: RagAnswer, source: str = SOURCE_CHAT) -> bool:
    """Returns whether the turn was saved. Still never raises - this runs after the answer has
    already been streamed, so there is no response left to fail - but the caller records a False in
    the request telemetry, so a turn that will be missing from the student's history on reload is
    visible in the logs as a field, not only as a traceback.

    One attempt, no retry: this is an insert, and an insert that timed out after Postgres committed
    it would be stored twice if sent again. The one exception is a row rejected because the `source`
    column does not exist yet (migration 0011 not applied): PostgREST refuses that body before
    anything is written, so nothing can be duplicated. A Chat turn is then re-sent without the
    column, exactly as it was stored before 0011. A Vở ghi turn is NOT stored at all - without the
    column it would be indistinguishable from a Chat turn and show up in the Chat sidebar.

    `question` is what the student typed into the question box. For a Vở ghi turn that is the
    question only - the selected passage is never passed here and never stored."""
    row = {
        "user_id": user_id,
        "conversation_id": str(conversation_id),
        "question": question,
        "rewritten_question": rewritten_question,
        "answer": result.answer,
        "is_fallback": result.is_fallback,
        "used_academic_reference": result.used_academic_reference,
        "citations": [c.model_dump() for c in result.citations],
        "related_articles": [r.model_dump() for r in result.related_articles],
        "retrieved_chunks": [_serialize_retrieved_chunk(c) for c in result.retrieved_chunks],
        "scenario_key_points": result.scenario_key_points,
        # requirements.md RAG_SYSTEM_PROMPT rule 9 grounding audit - see
        # migrations/0008_chat_query_logs_rule9_grounding.sql and
        # rag_service._rule9_ungrounded_dieu_numbers's docstring. None for branches that never ran
        # the check (not a legal-content answer at all); [] means it ran and found nothing.
        "rule9_ungrounded_dieu_numbers": result.rule9_ungrounded_dieu_numbers,
        # requirements.md "Viec 3" Buoc 3 completeness guard - see
        # migrations/0009_chat_query_logs_multipart_completeness.sql and
        # rag_service._multipart_missing_parts's docstring. None for every branch except the
        # multi-part one; [] means it ran and every PHAN was present.
        "multipart_missing_parts": result.multipart_missing_parts,
        "source": source,
    }
    try:
        supabase_client.table(CHAT_QUERY_LOGS_TABLE).insert(row).execute()
    except Exception as error:
        if not _is_missing_source_column(error):
            # A logging failure must never turn a successful answer into an error for the student.
            logger.exception("Failed to log chat query to Postgres (user_id=%s)", user_id)
            return False
        if source != SOURCE_CHAT:
            logger.warning("Not storing a %s turn: chat_query_logs.source does not exist yet "
                           "(migration 0011 not applied)", source)
            return False
        logger.warning("chat_query_logs.source does not exist yet (migration 0011 not applied) - "
                       "storing this chat turn without it")
        del row["source"]
        try:
            supabase_client.table(CHAT_QUERY_LOGS_TABLE).insert(row).execute()
        except Exception:
            logger.exception("Failed to log chat query to Postgres (user_id=%s)", user_id)
            return False
    return True
