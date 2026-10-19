"""Rule 9 for the mock trial, checked per (văn bản, Điều) PAIR - design doc Mục 5.1.

Why not reuse rag_service._rule9_ungrounded_dieu_numbers: it compares Điều NUMBERS only. A
trial speech routinely cites both codes at once (Điều 173, 51 BLHS next to Điều 326 BLTTHS), so a
number-only check passes a fabricated "Điều 326 Bộ luật Hình sự" because 326 is allowed - as a
BLTTHS article. This module parses each citation into (law, Điều, khoản, điểm) and checks it
against the case's deterministic legal pack. Chat and Vở ghi keep their own guard unchanged.

Modes:
- "lenient" (indictment, luận tội, bào chữa, đối đáp, opening): a citation without a law name is
  accepted only if its Điều number belongs to exactly ONE document among the allowed pairs.
- "strict" (tuyên án): every citation must name its law.
Lay speakers (bị cáo, bị hại, người làm chứng, ...) may not cite any Điều at all - see
lay_speaker_citations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.trial_config import BLHS_DOCUMENT, BLTTHS_DOCUMENT
from app.services.trial_legal_pack import DIEU_LIST_PATTERN, LegalPack, numbers_in_dieu_list

Mode = Literal["lenient", "strict"]
OTHER_LAW = "other"

# BLTTHS is checked first; "bộ luật hình sự" is not a substring of "bộ luật tố tụng hình sự"
# anyway, the order just keeps the intent obvious.
_LAW_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"bộ\s+luật\s+tố\s+tụng\s+hình\s+sự|bltths|\btths\b", re.IGNORECASE), BLTTHS_DOCUMENT),
    (re.compile(r"bộ\s+luật\s+hình\s+sự|\bblhs\b", re.IGNORECASE), BLHS_DOCUMENT),
)
_OTHER_LAW_PATTERN = re.compile(
    r"\b(?:luật|nghị\s+quyết|nghị\s+định|thông\s+tư|quyết\s+định|hiến\s+pháp|quy\s+chế)\b", re.IGNORECASE
)
# Khoản/điểm written immediately before "Điều N": "điểm b, s khoản 1", "khoản 1, khoản 2".
_KHOAN_DIEM_TAIL = re.compile(
    r"(?:điểm\s+(?P<diem>[a-zđ](?:\s*(?:,|và)\s*(?:điểm\s+)?[a-zđ])*)\s+)?"
    r"khoản\s+(?P<khoan>\d+(?:\s*(?:,|và)\s*(?:khoản\s+)?\d+)*)\s*(?:của\s+)?$",
    re.IGNORECASE,
)
_LETTER = re.compile(r"(?<![a-zđ])[a-zđ](?![a-zđ])", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")
_LOOKBACK_CHARS = 120
_LOOKAHEAD_CHARS = 70
# What may sit between two citations for the first to inherit the second's law name, as in
# "khoản 1 Điều 173 và điểm s khoản 1 Điều 51 Bộ luật Hình sự".
_LAW_INHERIT_GAP = re.compile(r"^[\s,;]*(?:và|cùng)?[\s,;]*(?:(?:điểm|khoản)[\s\w,]*?)?$", re.IGNORECASE)


@dataclass(frozen=True)
class Citation:
    dieu: str
    khoan: tuple[str, ...]
    diem: tuple[str, ...]
    law: str | None          # source_document, OTHER_LAW, or None when no law is named
    start: int               # span start, including a leading khoản/điểm phrase
    end: int                 # span end of the "Điều N" phrase (law name not included)

    def label(self) -> str:
        parts = []
        if self.diem:
            parts.append("điểm " + ",".join(self.diem))
        if self.khoan:
            parts.append("khoản " + ",".join(self.khoan))
        parts.append(f"Điều {self.dieu}")
        parts.append({BLHS_DOCUMENT: "BLHS", BLTTHS_DOCUMENT: "BLTTHS", OTHER_LAW: "văn bản khác",
                      None: "(không nêu luật)"}.get(self.law, self.law or ""))
        return " ".join(parts)


@dataclass(frozen=True)
class Violation:
    kind: str     # unknown_pair | other_law | ambiguous_law | missing_law | khoan_missing | diem_missing
    citation: Citation

    def label(self) -> str:
        return f"{self.kind}: {self.citation.label()}"


def _law_after(text: str, end: int) -> str | None:
    window = text[end:end + _LOOKAHEAD_CHARS]
    next_dieu = DIEU_LIST_PATTERN.search(window)
    if next_dieu:
        window = window[:next_dieu.start()]
    window = re.split(r"[.;:\n]", window, maxsplit=1)[0]
    for pattern, document in _LAW_NAME_PATTERNS:
        if pattern.search(window):
            return document
    if re.search(r"bộ\s+luật\s+này", window, re.IGNORECASE):
        return None
    if _OTHER_LAW_PATTERN.search(window):
        return OTHER_LAW
    return None


def extract_citations(text: str) -> list[Citation]:
    """Every "Điều N" mention, expanded per number for lists ("Điều 51, 52 BLHS" -> two)."""
    raw: list[Citation] = []
    for match in DIEU_LIST_PATTERN.finditer(text):
        lookback_start = max(0, match.start() - _LOOKBACK_CHARS)
        tail = _KHOAN_DIEM_TAIL.search(text[lookback_start:match.start()])
        khoan: tuple[str, ...] = ()
        diem: tuple[str, ...] = ()
        start = match.start()
        if tail:
            khoan = tuple(_DIGITS.findall(tail.group("khoan")))
            if tail.group("diem"):
                diem = tuple(m.group(0).lower() for m in _LETTER.finditer(tail.group("diem")))
            start = lookback_start + tail.start()
        law = _law_after(text, match.end())
        numbers = numbers_in_dieu_list(match.group(1))
        for index, number in enumerate(numbers):
            # A khoản/điểm phrase before a list ("khoản 1 Điều 51, 52") belongs to the first number.
            raw.append(Citation(number, khoan if index == 0 else (), diem if index == 0 else (),
                                law, start, match.end()))
    # Right-to-left: a citation with no law inherits the next citation's law when only
    # connectors / khoản-điểm phrases separate them.
    resolved = list(raw)
    for i in range(len(resolved) - 2, -1, -1):
        current, following = resolved[i], resolved[i + 1]
        if current.law is None and following.law is not None:
            gap = text[current.end:following.start] if following.start >= current.end else ""
            if current.end == following.end or _LAW_INHERIT_GAP.match(gap):
                resolved[i] = Citation(current.dieu, current.khoan, current.diem, following.law,
                                       current.start, current.end)
    return resolved


def check_citations(text: str, pack: LegalPack, mode: Mode) -> list[Violation]:
    allowed = pack.allowed_pairs()
    violations: list[Violation] = []
    for citation in extract_citations(text):
        document = citation.law
        if document == OTHER_LAW:
            violations.append(Violation("other_law", citation))
            continue
        if document is None:
            if mode == "strict":
                violations.append(Violation("missing_law", citation))
                continue
            candidates = {doc for doc, dieu in allowed if dieu == citation.dieu}
            if not candidates:
                violations.append(Violation("unknown_pair", citation))
                continue
            if len(candidates) > 1:
                violations.append(Violation("ambiguous_law", citation))
                continue
            document = next(iter(candidates))
        if (document, citation.dieu) not in allowed:
            violations.append(Violation("unknown_pair", citation))
            continue
        article = pack.get(document, citation.dieu)
        if article is None:
            continue  # a cross-reference inside a pack article: number is grounded, text is not here
        for khoan in citation.khoan:
            if not article.has_khoan(khoan):
                violations.append(Violation("khoan_missing", citation))
                break
        else:
            if citation.diem and citation.khoan:
                for letter in citation.diem:
                    if not any(article.has_diem(k, letter) for k in citation.khoan):
                        violations.append(Violation("diem_missing", citation))
                        break
    return violations


def lay_speaker_citations(text: str) -> list[Citation]:
    """Lay participants never cite law in this simulation; any Điều they mention is a violation."""
    return extract_citations(text)


def mask_unverified_citations(text: str, pack: LegalPack, speaker_label: str) -> tuple[str, int]:
    """For text the STUDENT wrote: every citation that fails the lenient check is replaced before
    the text reaches a prompt, so the AI can answer "that citation does not apply" without
    repeating a made-up number. The stored transcript keeps the student's original text."""
    bad_spans = sorted({(v.citation.start, v.citation.end) for v in check_citations(text, pack, "lenient")})
    if not bad_spans:
        return text, 0
    placeholder = f"[một điều luật do {speaker_label} viện dẫn, không có trong hồ sơ pháp lý của phiên tòa]"
    out, cursor = [], 0
    for start, end in bad_spans:
        if start < cursor:
            continue
        out.append(text[cursor:start])
        out.append(placeholder)
        cursor = end
    out.append(text[cursor:])
    return "".join(out), len(bad_spans)
