"""Two related but distinct suggestion mechanisms for the chat UI (Phase 6):
  - Static seed list (load_static_suggestions): shown on cold-start, before the user has asked
    anything. TODO: ingestion/chat_suggestions_seed.json is a PLACEHOLDER with a handful of
    sample questions - replace with the law student group's official seed list once provided,
    same file path, same {id, text} shape, no code changes needed.
  - Dynamic per-answer follow-ups (build_suggested_question): after a chat answer cites a Dieu,
    rag_service.py looks up nearby Dieu in the same document via vector similarity and calls
    this to turn each neighbor's dieu_title into a short natural-language question. Template
    first (deterministic, no extra LLM call/latency on every chat response); a title that
    doesn't match a known pattern still gets a readable generic question, never left as a bare
    title fragment.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.core.config import CHAT_SUGGESTIONS_SEED_PATH
from app.core.logging import get_logger

logger = get_logger(__name__)

# Ordered most-specific-first: BLTTHS titles for procedural-role Dieu (Tham phan, Thu ky Toa
# an, Dieu tra vien...) overwhelmingly follow these few fixed phrasings (verified against real
# chunks.json - Dieu 45-48 are a contiguous run of "Nhiem vu, quyen han va trach nhiem cua X"),
# so a handful of templates cover the common case well before falling back to the generic one.
TITLE_QUESTION_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Nhiệm vụ, quyền hạn và trách nhiệm của (.+)$"),
     "{subject} có nhiệm vụ, quyền hạn và trách nhiệm gì theo BLTTHS?"),
    (re.compile(r"^Nhiệm vụ, quyền hạn của (.+)$"),
     "{subject} có nhiệm vụ, quyền hạn gì theo BLTTHS?"),
    (re.compile(r"^Quyền và nghĩa vụ của (.+)$"),
     "{subject} có quyền và nghĩa vụ gì theo BLTTHS?"),
    (re.compile(r"^Trách nhiệm của (.+)$"),
     "{subject} có trách nhiệm gì theo BLTTHS?"),
    (re.compile(r"^Thay đổi (.+)$"),
     "Khi nào phải thay đổi {subject}?"),
]

GENERIC_QUESTION_TEMPLATE = "{dieu_title} được quy định như thế nào?"


def build_suggested_question(dieu_title: str) -> str:
    stripped_title = dieu_title.strip()
    for pattern, template in TITLE_QUESTION_TEMPLATES:
        match = pattern.match(stripped_title)
        if match:
            subject = match.group(1).strip().rstrip(".")
            return template.format(subject=subject)

    return GENERIC_QUESTION_TEMPLATE.format(dieu_title=stripped_title)


@lru_cache(maxsize=1)
def load_static_suggestions() -> list[dict[str, Any]]:
    if not CHAT_SUGGESTIONS_SEED_PATH.exists():
        logger.warning("Chat suggestions seed file not found at %s", CHAT_SUGGESTIONS_SEED_PATH)
        return []
    return json.loads(CHAT_SUGGESTIONS_SEED_PATH.read_text(encoding="utf-8"))
