"""Query understanding pre-processing step (Phase 4 Extension, see requirements.md): a single
lightweight Gemini call that runs BEFORE retrieval to (a) expand common legal abbreviations and
(b) resolve implicit conversational context (pronouns, "what about X") into a standalone
question, using only the recent conversation turns already logged for this conversation_id -
never inventing new legal content. Retrieval and the final answer prompt use the rewritten
question this returns, not the student's raw input.
"""
from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.prompts.query_understanding_prompts import QUERY_UNDERSTANDING_SYSTEM_PROMPT, build_query_understanding_prompt
from app.services.gemini_client import generate_answer

logger = get_logger(__name__)


def rewrite_question(question: str, recent_turns: list[dict[str, str]], settings: Settings) -> str:
    user_prompt = build_query_understanding_prompt(question, recent_turns)

    try:
        rewritten = generate_answer(QUERY_UNDERSTANDING_SYSTEM_PROMPT, user_prompt, settings)
    except Exception:
        # A broken query-understanding call must never break the whole chat request - degrade to
        # retrieval/generation on the student's original wording, same as before this extension.
        logger.exception("Query understanding call failed - falling back to the original question")
        return question

    rewritten = rewritten.strip().strip('"').strip("'").strip()
    return rewritten if rewritten else question
