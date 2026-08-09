"""Query understanding pre-processing step (Phase 4 Extension, see requirements.md): a single
lightweight Gemini call that runs BEFORE retrieval to (a) expand common legal abbreviations,
(b) resolve implicit conversational context (pronouns, "what about X") into a standalone
question, and (c) classify the question's intent (requirements.md muc E, extended by the "Mở rộng
phân loại ý định Query Understanding" feature, and again by the "Sinh tình huống minh họa" feature,
Lượt 1 và Lượt 2) into one of legal_question/greeting/summarize_previous/request_scenario/
answer_evaluation/out_of_scope, using only the recent conversation turns already logged for this
conversation_id - never inventing new legal content. Retrieval and the final answer prompt use
the rewritten question this returns, not the student's raw input - UNLESS intent is not
legal_question, in which case rag_service short-circuits to the matching branch (refusal/greeting
template/summarize/scenario/grading call) without calling retrieval/generation at all.

"answer_evaluation" has an extra, DETERMINISTIC gate on top of the LLM's own classification (see
`has_pending_scenario` below): the LLM is told (via the prompt's "LƯU Ý ĐẶC BIỆT" line) whether the
previous turn actually left a scenario+rubric pending, but a model call can still occasionally
violate that instruction. This module never trusts the model alone for a decision that controls
whether a hidden rubric gets used at all - see the hard downgrade below, same defensive principle
as the meta-commentary/malformed-rewrite safety nets already in this file.
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
    VALID_INTENTS,
    build_query_understanding_prompt,
)
from app.services.gemini_client import generate_answer

logger = get_logger(__name__)

# Second safety net (requirements.md muc E, buoc 4) - even with intent as its own schema field, a
# model call can still occasionally violate the "rewritten_question is ONLY the question" contract
# (e.g. leaking a meta/explanatory sentence into rewritten_question while, inconsistently, still
# reporting intent=legal_question). This doesn't try to detect every possible malformed
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
    intent: str  # one of VALID_INTENTS - see query_understanding_prompts.py


def _looks_like_malformed_rewrite(original_question: str, rewritten_question: str) -> bool:
    if any(pattern.search(rewritten_question) for pattern in _META_COMMENTARY_PATTERNS):
        return True
    max_allowed_length = len(original_question) * _MAX_LENGTH_MULTIPLIER + _MAX_LENGTH_ABSOLUTE_MARGIN
    return len(rewritten_question) > max_allowed_length


def rewrite_question(
    question: str, recent_turns: list[dict[str, str]], settings: Settings, has_pending_scenario: bool = False
) -> QueryUnderstandingResult:
    user_prompt = build_query_understanding_prompt(question, recent_turns, has_pending_scenario)

    try:
        response_text = generate_answer(
            QUERY_UNDERSTANDING_SYSTEM_PROMPT, user_prompt, settings,
            response_json=True, response_schema=QUERY_UNDERSTANDING_RESPONSE_SCHEMA
        )
        parsed = json.loads(response_text)
        rewritten = str(parsed["rewritten_question"]).strip()
        intent = str(parsed["intent"]).strip()
        if intent not in VALID_INTENTS:
            # responseSchema's enum constraint should already prevent this, but never trust a
            # single enforcement layer alone (same principle as the meta-commentary safety net
            # below) - degrade to the safe default rather than propagating an unrecognized intent
            # string into rag_service's branching.
            logger.warning("Query understanding returned unrecognized intent %r - defaulting to legal_question", intent)
            intent = "legal_question"
        if intent == "answer_evaluation" and not has_pending_scenario:
            # Hard, code-level gate (requirements.md "Sinh tình huống minh họa" Lượt 2): the
            # caller (chat.py) computed has_pending_scenario from chat_query_logs.scenario_key_points
            # directly, which is authoritative - the LLM's own classification, even though it was
            # given this same fact in the prompt, is not trusted alone to decide whether a hidden
            # grading rubric gets used. Without this, a model that ignores the prompt's "LƯU Ý ĐẶC
            # BIỆT" gating instruction could route an ordinary message into grading against a
            # rubric that doesn't exist for this turn.
            logger.warning(
                "Query understanding returned answer_evaluation without a pending scenario rubric "
                "(has_pending_scenario=False) - downgrading to legal_question"
            )
            intent = "legal_question"
    except Exception:
        # A broken/malformed query-understanding call must never break the whole chat request -
        # degrade to retrieval/generation on the student's original wording, same as before this
        # extension, and never claim out-of-scope/greeting/summarize on a call we couldn't even
        # parse.
        logger.exception("Query understanding call failed - falling back to the original question")
        return QueryUnderstandingResult(rewritten_question=question, intent="legal_question")

    if not rewritten:
        rewritten = question

    if intent != "legal_question":
        # Layer 1 fix (requirements.md muc E, extended to all 3 non-legal_question intents): none
        # of out_of_scope/greeting/summarize_previous ever use the model's rewritten_question for
        # anything (rag_service short-circuits before retrieval for all 3), but force it verbatim
        # anyway so the logged chat_query_logs row stays honest even if the model violated the
        # prompt's rewrite rules for these intents.
        rewritten = question
    elif _looks_like_malformed_rewrite(question, rewritten):
        # Layer 2 safety net (requirements.md muc E, buoc 4) - independent of layer 1, catches the
        # same failure mode if it slips through with intent still reported as legal_question.
        logger.warning(
            "rewritten_question looked malformed (meta-commentary or abnormal length) despite "
            "intent=legal_question - falling back to the original question. original=%r rewritten=%r",
            question, rewritten
        )
        rewritten = question

    return QueryUnderstandingResult(rewritten_question=rewritten, intent=intent)
