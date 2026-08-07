"""Query understanding pre-processing step (Phase 4 Extension, see requirements.md): a single
lightweight Gemini call that runs BEFORE retrieval to (a) expand common legal abbreviations,
(b) resolve implicit conversational context (pronouns, "what about X") into a standalone
question, and (c) classify whether the question is out of scope for this app (requirements.md
muc E), using only the recent conversation turns already logged for this conversation_id - never
inventing new legal content. Retrieval and the final answer prompt use the rewritten question
this returns, not the student's raw input - UNLESS is_out_of_scope is true, in which case
rag_service short-circuits to the refusal answer without calling retrieval/generation at all.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.core.logging import get_logger
from app.prompts.query_understanding_prompts import (
    QUERY_UNDERSTANDING_RESPONSE_SCHEMA,
    QUERY_UNDERSTANDING_SYSTEM_PROMPT,
    build_query_understanding_prompt,
)
from app.services.gemini_client import generate_answer

logger = get_logger(__name__)

# Second safety net (requirements.md muc E, buoc 4) - even with is_out_of_scope as its own schema
# field, a model call can still occasionally violate the "rewritten_question is ONLY the question"
# contract (e.g. leaking a meta/explanatory sentence into rewritten_question while, inconsistently,
# still reporting is_out_of_scope=false). This doesn't try to detect every possible malformed
# output - it catches the specific failure mode actually observed and reproduced (see
# requirements.md muc E investigation): a meta-commentary sentence ABOUT the question standing in
# for the question itself. Matched case-insensitively against the start of common Vietnamese
# phrasings a model uses to describe/explain rather than ask.
_META_COMMENTARY_PATTERNS = (
    re.compile(r"câu hỏi (của bạn|này|hiện tại)", re.IGNORECASE),
    re.compile(r"không liên quan", re.IGNORECASE),
    re.compile(r"xin lỗi", re.IGNORECASE),
    re.compile(r"vui lòng đặt câu hỏi", re.IGNORECASE),
)
# A legitimate rewrite can legitimately grow a lot (abbreviation expansion + pulling specific
# context from conversation history onto a short follow-up like "Còn Điều 327 thì sao?") - this is
# deliberately generous so it only catches the case a short/off-topic message balloons into a full
# explanatory sentence, not normal-range expansion.
_MAX_LENGTH_MULTIPLIER = 5
_MAX_LENGTH_ABSOLUTE_MARGIN = 60


@dataclass
class QueryUnderstandingResult:
    rewritten_question: str
    is_out_of_scope: bool


def _looks_like_malformed_rewrite(original_question: str, rewritten_question: str) -> bool:
    if any(pattern.search(rewritten_question) for pattern in _META_COMMENTARY_PATTERNS):
        return True
    max_allowed_length = len(original_question) * _MAX_LENGTH_MULTIPLIER + _MAX_LENGTH_ABSOLUTE_MARGIN
    return len(rewritten_question) > max_allowed_length


def rewrite_question(question: str, recent_turns: list[dict[str, str]], settings: Settings) -> QueryUnderstandingResult:
    user_prompt = build_query_understanding_prompt(question, recent_turns)

    try:
        response_text = generate_answer(
            QUERY_UNDERSTANDING_SYSTEM_PROMPT, user_prompt, settings,
            response_json=True, response_schema=QUERY_UNDERSTANDING_RESPONSE_SCHEMA
        )
        parsed = json.loads(response_text)
        rewritten = str(parsed["rewritten_question"]).strip()
        is_out_of_scope = bool(parsed["is_out_of_scope"])
    except Exception:
        # A broken/malformed query-understanding call must never break the whole chat request -
        # degrade to retrieval/generation on the student's original wording, same as before this
        # extension, and never claim out-of-scope on a call we couldn't even parse.
        logger.exception("Query understanding call failed - falling back to the original question")
        return QueryUnderstandingResult(rewritten_question=question, is_out_of_scope=False)

    if not rewritten:
        rewritten = question

    if is_out_of_scope:
        # Layer 1 fix (requirements.md muc E): out-of-scope never uses the model's
        # rewritten_question for anything (rag_service short-circuits before retrieval), but force
        # it verbatim anyway so the logged chat_query_logs row stays honest even if the model
        # violated rule 1 of the prompt.
        rewritten = question
    elif _looks_like_malformed_rewrite(question, rewritten):
        # Layer 2 safety net (requirements.md muc E, buoc 4) - independent of layer 1, catches the
        # same failure mode if it slips through with is_out_of_scope still reported as false.
        logger.warning(
            "rewritten_question looked malformed (meta-commentary or abnormal length) despite "
            "is_out_of_scope=false - falling back to the original question. original=%r rewritten=%r",
            question, rewritten
        )
        rewritten = question

    return QueryUnderstandingResult(rewritten_question=rewritten, is_out_of_scope=is_out_of_scope)
