"""Query understanding pre-processing step (Phase 4 Extension, see requirements.md): a single
lightweight Gemini call that runs BEFORE retrieval to (a) expand common legal abbreviations,
(b) resolve implicit conversational context (pronouns, "what about X") into a standalone
question, and (c) classify the question's intent (requirements.md muc E, extended by the "Mở rộng
phân loại ý định Query Understanding" feature, again by the "Sinh tình huống minh họa" feature,
Lượt 1 và Lượt 2, and again by the summarize_previous/explain_simpler split - see
conversational_prompts.py) into one of legal_question/greeting/summarize_previous/
explain_simpler/request_scenario/answer_evaluation/out_of_scope, using only the recent
conversation turns already logged for this
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

For intent=legal_question, this same call also flags requirements.md muc C ("Ẩn danh hóa người
thật"): a question that names a real/identifiable real-world person alongside a specific behavior
to legally classify gets its rewritten_question pre-anonymized (real names replaced by A/B/C) right
here, before retrieval/generation ever see it - see needs_anonymization/anonymized_names on
QueryUnderstandingResult and rag_service.py's use of them for the buffered-generation + leak-check
path that keeps the absolute "never repeat the real name" constraint even if this LLM call itself
misbehaves.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

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

# Cleans up whatever punctuation _scrub_residual_names's removal leaves behind (e.g. "Anh A ()"
# from a nickname that used to sit in parentheses, or doubled spaces from a name removed
# mid-sentence) - applied only after every name has already been stripped out.
_EMPTY_PARENS_PATTERN = re.compile(r"\(\s*\)")
_MULTI_SPACE_PATTERN = re.compile(r"[ \t]{2,}")


def _scrub_residual_names(text: str, anonymized_names: list[str]) -> str:
    """Second, code-level layer (requirements.md muc C's absolute constraint) on top of the
    prompt's own anonymization instructions - even with the explicit "don't leave the nickname in
    parentheses" example added to the prompt after reproducing exactly that failure, a model call
    can still occasionally leave a residual name/nickname in rewritten_question (which reaches the
    client verbatim via the citations SSE event's rewritten_question field, not just internal
    generation). Strips every string in anonymized_names (the model's own list of what it claims
    to have anonymized) out of the text it produced, longest-first so a name that's a substring of
    another (e.g. a first name inside a full name) doesn't leave a partial fragment behind."""
    if not anonymized_names:
        return text
    scrubbed = text
    for name in sorted((n for n in anonymized_names if n), key=len, reverse=True):
        scrubbed = re.sub(re.escape(name), "", scrubbed, flags=re.IGNORECASE)
    scrubbed = _EMPTY_PARENS_PATTERN.sub("", scrubbed)
    scrubbed = _MULTI_SPACE_PATTERN.sub(" ", scrubbed)
    return scrubbed.strip()


@dataclass
class QueryUnderstandingResult:
    rewritten_question: str
    intent: str  # one of VALID_INTENTS - see query_understanding_prompts.py
    # requirements.md muc C "An danh hoa nguoi that" - true only when intent="legal_question" AND
    # the question named a real/identifiable real-world person alongside a specific behavior to
    # classify legally (not a direct guilt confirmation/denial question - see the prompt's
    # rewritten_question rule 3.d). When true, rewritten_question has already had every name in
    # anonymized_names replaced by an A/B/C label - rag_service.py uses anonymized_names only as a
    # defensive post-generation leak check, never shown to the student.
    needs_anonymization: bool = False
    anonymized_names: list[str] = field(default_factory=list)
    # requirements.md "Viec 3" (tach cau hoi nhieu chu de truoc khi retrieval) - non-empty ONLY
    # when intent="legal_question" AND the message had a clear enumerated sub-question structure
    # (numbered "1./2./3.", "Nhận định N", "Trường hợp N", "Câu N"... - see the prompt's
    # sub_questions rules). Each element is that sub-question's own text, already run through the
    # same abbreviation-expansion/context-resolution rules as rewritten_question. Bước 1+2 only:
    # rag_service.py does not yet consume this for retrieval/generation - see
    # retrieve_context_for_subquestions, added standalone ahead of that wiring (Bước 3).
    sub_questions: list[str] = field(default_factory=list)


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
        needs_anonymization = bool(parsed.get("needs_anonymization", False))
        anonymized_names = [str(n).strip() for n in parsed.get("anonymized_names") or [] if str(n).strip()]
        sub_questions = [str(q).strip() for q in parsed.get("sub_questions") or [] if str(q).strip()]
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
        # Anonymization only ever applies within the legal_question retrieval/generation path
        # (requirements.md muc C) - the prompt's own rule 5 already tells the model this, but
        # don't trust that alone (same defensive layering as every other field on this call).
        needs_anonymization = False
        anonymized_names = []
        # sub_questions only ever applies within the legal_question path too (requirements.md
        # "Viec 3") - same defensive layering as needs_anonymization just above.
        sub_questions = []
    elif _looks_like_malformed_rewrite(question, rewritten):
        # Layer 2 safety net (requirements.md muc E, buoc 4) - independent of layer 1, catches the
        # same failure mode if it slips through with intent still reported as legal_question.
        logger.warning(
            "rewritten_question looked malformed (meta-commentary or abnormal length) despite "
            "intent=legal_question - falling back to the original question. original=%r rewritten=%r",
            question, rewritten
        )
        rewritten = question
        # rewritten reverted to the STUDENT'S ORIGINAL wording, which still contains the real
        # name(s) if needs_anonymization was true - never carry that flag forward onto untrusted
        # text that was never actually anonymized (requirements.md muc C's absolute constraint:
        # the final answer must never repeat the real name). Falls through to the ordinary
        # legal_question path instead, same as before this feature existed.
        if needs_anonymization:
            logger.warning(
                "needs_anonymization=true but rewritten_question was discarded as malformed - "
                "downgrading to needs_anonymization=false rather than trusting unanonymized text"
            )
        needs_anonymization = False
        anonymized_names = []
        # rewritten (and therefore each sub_question, derived from the same untrusted call) was
        # discarded as malformed - don't propagate a sub_questions split built from text this
        # module no longer trusts, same reasoning as the needs_anonymization reset just above.
        if sub_questions:
            logger.warning(
                "sub_questions was non-empty but rewritten_question was discarded as malformed - "
                "downgrading to sub_questions=[] rather than trusting an untrusted split"
            )
        sub_questions = []
    elif needs_anonymization and not anonymized_names:
        # The model flagged anonymization but gave us nothing to defensively check the final
        # answer against - safer to skip the special (buffered + disclaimer) generation path than
        # to run it with an empty leak-detection list, same "don't trust a flag with nothing behind
        # it" principle as the answer_evaluation gate above. rewritten_question may already be
        # anonymized text regardless (harmless either way), just without the disclaimer/addendum.
        logger.warning(
            "needs_anonymization=true but anonymized_names was empty - downgrading to "
            "needs_anonymization=false"
        )
        needs_anonymization = False

    if needs_anonymization:
        # Layer 2, code-level (see _scrub_residual_names docstring) - independent of the prompt's
        # own anonymization instructions, catches a residual real name/nickname the model's rewrite
        # missed (e.g. the "name (nickname)" pattern reproduced during this feature's own testing).
        scrubbed = _scrub_residual_names(rewritten, anonymized_names)
        if scrubbed:
            rewritten = scrubbed

    if len(sub_questions) < 2:
        # A "split" of 0 or 1 item isn't a real enumeration - either the model found nothing to
        # split (already []) or degenerately echoed the whole message as a single-element list.
        # Independent retrieval only makes sense for >=2 sub-questions, so normalize both cases to
        # [] rather than let a 1-item list silently trigger a per-subquestion retrieval path later.
        sub_questions = []

    return QueryUnderstandingResult(
        rewritten_question=rewritten, intent=intent,
        needs_anonymization=needs_anonymization, anonymized_names=anonymized_names,
        sub_questions=sub_questions
    )
