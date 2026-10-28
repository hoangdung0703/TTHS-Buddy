"""Display-only anonymisation of the case-file panel (chặng 3D).

Lay participants (bị cáo, bị hại, người làm chứng, người có quyền lợi, nghĩa vụ liên quan) are shown
as surname + middle name + initial of the given name ("Trần Đức Hùng" -> "Trần Đức H"); Chủ tọa, Hội
thẩm, Thư ký, Kiểm sát viên and the defence lawyer keep their full names.

Scope: ONLY the case_file returned to the panel. Hearing utterances, the biên bản, stored rows and
model prompts keep full names. `anonymise_case_view` is the single entry point, so a later change
of convention (or a new place to apply it) touches this module only.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from app.models.trial import Participant
from app.services.trial_names import is_anonymised, short_name

# A given name on its own is replaced only right after one of these words: "bị cáo Hùng" is a
# person, "Việt Nam" is not. Matched case-insensitively; the given name itself must be capitalised
# ("anh hùng" = hero).
ADDRESS_WORDS = ("người có quyền lợi, nghĩa vụ liên quan", "người làm chứng", "người bị hại", "bị cáo", "bị hại",
                 "bị can", "ông", "bà", "anh", "chị", "em", "cô", "chú", "cháu")
_ADDRESS = "|".join(re.escape(w) for w in sorted(ADDRESS_WORDS, key=len, reverse=True))


def display_names(participants: dict[str, Participant]) -> dict[str, str]:
    return {pid: short_name(p.name) if is_anonymised(pid) else p.name for pid, p in participants.items()}


Rule = tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]


def _lone_name_replacement(initial: str) -> Callable[[re.Match[str]], str]:
    # A capitalised word right after the name means a longer proper noun ("ông Việt Nam"): kept.
    def replace(m: re.Match[str]) -> str:
        following = m.group(2)
        return m.group(0) if following and following.lstrip()[0].isupper() else m.group(1) + initial
    return replace


def _replacements(participants: dict[str, Participant]) -> list[Rule]:
    hidden = [p for pid, p in participants.items() if is_anonymised(pid)]
    rules: list[Rule] = []
    # Full names first, longest first, so no shorter name eats part of a longer one.
    for p in sorted(hidden, key=lambda p: len(p.name), reverse=True):
        tokens = unicodedata.normalize("NFC", p.name).split()
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(t) for t in tokens) + r"(?!\w)"
        rules.append((re.compile(pattern, re.IGNORECASE), short_name(p.name)))
    for p in hidden:
        given = unicodedata.normalize("NFC", p.name).split()[-1]
        pattern = rf"(?<!\w)((?i:{_ADDRESS})\s+){re.escape(given)}(?!\w)(?=(\s+\w)?)"
        rules.append((re.compile(pattern), _lone_name_replacement(given[0])))
    return rules


def anonymise_text(text: str, participants: dict[str, Participant]) -> str:
    return _tree(text, _replacements(participants))


def _tree(value: Any, rules: list[Rule]) -> Any:
    if isinstance(value, str):
        text = unicodedata.normalize("NFC", value)
        for pattern, replacement in rules:
            text = pattern.sub(replacement, text)
        return text
    if isinstance(value, list):
        return [_tree(v, rules) for v in value]
    if isinstance(value, dict):
        return {k: _tree(v, rules) for k, v in value.items()}
    return value


def anonymise_case_view(view: dict[str, Any], participants: dict[str, Participant]) -> dict[str, Any]:
    """The rendered case-file view with every hidden full name abbreviated, plus the names the
    panel shows: `name` on each person object and `display_names` (id -> name, every participant)."""
    out = _tree(view, _replacements(participants))
    names = display_names(participants)
    for person in [out.get("defendant"), out.get("victim"), *(out.get("witnesses") or []), out.get("related_party")]:
        if isinstance(person, dict) and person.get("id") in names:
            person["name"] = names[person["id"]]
    out["display_names"] = names
    return out
