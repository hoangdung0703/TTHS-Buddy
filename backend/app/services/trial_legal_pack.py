"""Deterministic legal pack for one mock-trial case (design doc Mục 4).

Every article a hearing may cite is known in advance - the charged BLHS Điều, a fixed Phần chung
set, and the BLTTHS trial chapters - so the pack is fetched by key (source_document + dieu_number)
from Qdrant once, when the case is created. No embedding, HyDE or re-rank call is involved, and no
retrieval runs per utterance. The same pack is the single source of truth for: the legal text put
in each prompt (sliced by step), the Rule 9 pair guard (trial_rule9.py) and the case/verdict
validators (khoản and điểm must exist in these texts).

Built from chunk payloads, so the unit tests construct packs from ingestion/chunks.json without
any network call, and production builds the identical structure from Qdrant payloads.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from app.services.trial_config import (
    BLHS_DOCUMENT,
    BLHS_GENERAL_PART,
    BLTTHS_DOCUMENT,
    BLTTHS_ROLE_ARTICLES,
    BLTTHS_STEP_SLICES,
    CHARGE,
    LAW_SHORT_NAMES,
    SLOT_LEGAL_SLICES,
    STEP_TO_SLICE,
    CrimeConfig,
)

# Khoản lines start with "N. " at the beginning of a line; page-number artefacts in the PDF text
# ("86" alone on a line) never carry the dot, and cross-reference lists ("170, 171, ...") carry a
# comma, so neither is mistaken for a khoản. Numbers must also run 1, 2, 3... in order.
_KHOAN_LINE = re.compile(r"^\s*(\d{1,2})\.\s")
_DIEM_LINE = re.compile(r"^\s*([a-zđ])\)\s")
# "Điều 173", "các điều 168, 169, 170 và 290": the number list after "điều".
DIEU_LIST_PATTERN = re.compile(r"(?<!\w)điều\s+(\d+[a-z]?(?:\s*(?:,|và)\s*\d+[a-z]?)*)", re.IGNORECASE)
_NUMBER_IN_LIST = re.compile(r"\d+[a-z]?")

# Upper bound for one Qdrant scroll: the largest article set requested (~70 Điều, at most 6 chunks
# each) stays far below this, so one call per document is always complete.
_SCROLL_LIMIT = 1000


@dataclass(frozen=True)
class Khoan:
    number: str
    text: str
    diem: frozenset[str]

    @property
    def head(self) -> str:
        """The khoản's own sentence before its first điểm - where the penalty frame is stated."""
        lines: list[str] = []
        for line in self.text.splitlines():
            if _DIEM_LINE.match(line):
                break
            lines.append(line)
        return " ".join(" ".join(lines).split())

    def diem_text(self, letter: str) -> str:
        collecting, out = False, []
        for line in self.text.splitlines():
            match = _DIEM_LINE.match(line)
            if match:
                if collecting:
                    break
                collecting = match.group(1) == letter
            if collecting:
                out.append(line)
        return " ".join(" ".join(out).split())


@dataclass(frozen=True)
class LegalArticle:
    source_document: str
    dieu_number: str
    dieu_title: str
    text: str
    khoans: dict[str, Khoan]
    # Điều numbers mentioned inside this article's own text (cross-references); quoting them back
    # is legitimate, same reasoning as rag_service._rule9_allowed_dieu_numbers.
    cross_refs: frozenset[str]

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_document, self.dieu_number)

    def has_khoan(self, khoan: str) -> bool:
        return khoan in self.khoans

    def has_diem(self, khoan: str, diem: str) -> bool:
        return khoan in self.khoans and diem in self.khoans[khoan].diem

    def prompt_block(self) -> str:
        return f"[{LAW_SHORT_NAMES.get(self.source_document, self.source_document)}] " \
               f"Điều {self.dieu_number}. {self.dieu_title}\n{self.text}"


def _strip_heading(text: str, dieu_number: str) -> str:
    lines = text.splitlines()
    if lines and re.match(rf"^\s*Điều\s+{re.escape(dieu_number)}\b", lines[0]):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _parse_khoans(body: str) -> dict[str, Khoan]:
    khoans: dict[str, list[str]] = {}
    current: str | None = None
    expected = 1
    for line in body.splitlines():
        match = _KHOAN_LINE.match(line)
        if match and int(match.group(1)) == expected:
            current = match.group(1)
            khoans[current] = []
            expected += 1
        if current is not None:
            khoans[current].append(line)
    result: dict[str, Khoan] = {}
    for number, lines in khoans.items():
        text = "\n".join(lines)
        diem = frozenset(m.group(1) for line in lines if (m := _DIEM_LINE.match(line)))
        result[number] = Khoan(number=number, text=text, diem=diem)
    return result


def numbers_in_dieu_list(list_text: str) -> list[str]:
    return _NUMBER_IN_LIST.findall(list_text)


def build_article(payloads: list[dict[str, Any]]) -> LegalArticle:
    """All chunks of ONE Điều -> one article. Khoản-split chunks are ordered by khoan_number."""
    first = payloads[0]
    ordered = sorted(payloads, key=lambda p: int(p.get("khoan_number") or 0))
    body = "\n".join(_strip_heading(p["chunk_text"], p["dieu_number"]) for p in ordered)
    cross: set[str] = set()
    for match in DIEU_LIST_PATTERN.finditer(body):
        cross.update(numbers_in_dieu_list(match.group(1)))
    cross.discard(first["dieu_number"])
    return LegalArticle(
        source_document=first["source_document"], dieu_number=first["dieu_number"],
        dieu_title=first.get("dieu_title") or "", text=body, khoans=_parse_khoans(body),
        cross_refs=frozenset(cross),
    )


@dataclass
class LegalPack:
    articles: dict[tuple[str, str], LegalArticle] = field(default_factory=dict)

    def get(self, source_document: str, dieu_number: str) -> LegalArticle | None:
        return self.articles.get((source_document, dieu_number))

    def allowed_pairs(self) -> set[tuple[str, str]]:
        pairs = set(self.articles)
        for article in self.articles.values():
            pairs.update((article.source_document, ref) for ref in article.cross_refs)
        return pairs

    def keys_json(self) -> list[dict[str, str]]:
        return [{"source_document": doc, "dieu_number": dieu} for doc, dieu in sorted(self.articles)]

    def slice_for_step(self, step: int, charged_dieu: str) -> list[LegalArticle]:
        """Prompt slice: the step group's BLTTHS articles, the role articles, and - from step 6 on,
        where penalties are argued and decided - the charged Điều plus Phần chung BLHS. Steps 4-5
        get the charged Điều only (the facts are questioned against its elements)."""
        slice_name = STEP_TO_SLICE[step]
        keys: list[tuple[str, str]] = [(BLTTHS_DOCUMENT, d) for d in BLTTHS_STEP_SLICES[slice_name]]
        if slice_name == "opening":
            keys += [(BLTTHS_DOCUMENT, d) for d in ("61", "62", "65", "66", "73", "243")]
        if slice_name in ("questioning", "closing"):
            keys.append((BLHS_DOCUMENT, charged_dieu))
        if slice_name == "closing":
            keys += [(BLHS_DOCUMENT, d) for d in BLHS_GENERAL_PART]
        return [self.articles[k] for k in keys if k in self.articles]


    def slice_for_slot(self, slot_key: str, step: int, charged_dieu: str) -> list[LegalArticle]:
        """The articles one AI call sees. Long speeches and the closing dialogue slots have their own
        trimmed list (trial_config.SLOT_LEGAL_SLICES); everything else uses the step-group slice."""
        spec = SLOT_LEGAL_SLICES.get(slot_key.split(":")[0])
        if spec is None:
            return self.slice_for_step(step, charged_dieu)
        keys = [(doc, charged_dieu if d == CHARGE else d) for doc, numbers in spec.items() for d in numbers]
        return [self.articles[k] for k in keys if k in self.articles]

    def subset(self, articles: Iterable[LegalArticle]) -> "LegalPack":
        return LegalPack(articles={a.key: a for a in articles})

    def to_payloads(self) -> list[dict[str, Any]]:
        """Stored with the case (mock_trial_cases.legal_pack) so every later turn rebuilds the exact
        same pack without a Qdrant call, even if the corpus is re-ingested in the meantime."""
        return [{"source_document": a.source_document, "dieu_number": a.dieu_number, "dieu_title": a.dieu_title,
                 "khoan_number": None, "chunk_text": f"Điều {a.dieu_number}. {a.dieu_title}\n{a.text}"}
                for a in self.articles.values()]


def build_pack(payloads: Iterable[dict[str, Any]]) -> LegalPack:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for payload in payloads:
        grouped.setdefault((payload["source_document"], payload["dieu_number"]), []).append(payload)
    return LegalPack(articles={key: build_article(chunks) for key, chunks in grouped.items()})


def pack_request_for_crime(crime: CrimeConfig) -> dict[str, list[str]]:
    blttths: set[str] = set(BLTTHS_ROLE_ARTICLES)
    for numbers in BLTTHS_STEP_SLICES.values():
        blttths.update(numbers)
    return {
        BLHS_DOCUMENT: sorted({crime.dieu, *BLHS_GENERAL_PART}, key=int),
        BLTTHS_DOCUMENT: sorted(blttths, key=int),
    }


def fetch_payloads(client: QdrantClient, collection: str, request: dict[str, list[str]]) -> list[dict[str, Any]]:
    """One scroll per document with MatchAny on dieu_number. Repealed points are excluded the same
    way rag_service excludes them. Blocking - callers on the event loop wrap it in to_thread."""
    payloads: list[dict[str, Any]] = []
    for source_document, dieu_numbers in request.items():
        points, _ = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="source_type", match=MatchValue(value="legal_text")),
                    FieldCondition(key="source_document", match=MatchValue(value=source_document)),
                    FieldCondition(key="dieu_number", match=MatchAny(any=dieu_numbers)),
                ],
                must_not=[FieldCondition(key="is_repealed", match=MatchValue(value=True))],
            ),
            limit=_SCROLL_LIMIT,
            with_payload=True,
        )
        payloads.extend(p.payload for p in points)
    return payloads


def missing_keys(pack: LegalPack, request: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [(doc, d) for doc, numbers in request.items() for d in numbers if (doc, d) not in pack.articles]
