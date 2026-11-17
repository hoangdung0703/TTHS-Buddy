"""Money amounts in hearing text (nhóm B+, design doc Mục 11.16.3).

The money guard compares every amount an AI line states with the amounts the case holds. Before nhóm
B+ it only saw full digit forms ("12.500.000 đồng"); an amount written with a unit word ("12,5 triệu
đồng", "1 tỷ 200 triệu", "200 nghìn", "15 tr") was not seen at all, so an invented one passed and a
correct one could not be compared. This module reads both forms into the same integer value.

Amounts written only in words ("mười lăm triệu đồng") are found but only MEASURED (flag
`amount_in_words`): parsing Vietnamese number words reliably is a larger job, and no data shows yet
how often they occur.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.services.trial_case_validator import MONEY_PATTERN, parse_money

_UNITS: dict[str, int] = {"tỷ": 10**9, "tỉ": 10**9, "triệu": 10**6, "tr": 10**6, "nghìn": 10**3, "ngàn": 10**3}
_NUMBER = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:tỷ|tỉ|triệu|tr\.?|nghìn|ngàn)"
_GROUP = rf"{_NUMBER}\s*{_UNIT}(?!\w)"
# One or more "number unit" groups ("1 tỷ 200 triệu"), then an optional currency word.
UNIT_MONEY_PATTERN = re.compile(rf"(?<![\w.,])({_GROUP}(?:\s+{_GROUP})*)(?:\s*(?:đồng|vnđ|vnd|đ)(?!\w))?",
                                re.IGNORECASE)
_GROUP_PARTS = re.compile(rf"({_NUMBER})\s*({_UNIT})(?!\w)", re.IGNORECASE)

_NUMBER_WORDS = ("một", "hai", "ba", "bốn", "tư", "năm", "lăm", "sáu", "bảy", "tám", "chín", "mười", "mươi",
                 "mốt", "trăm", "linh", "lẻ", "rưỡi")
WORD_MONEY_PATTERN = re.compile(
    rf"(?<!\w)(?:(?:{'|'.join(_NUMBER_WORDS)})\s+)+(?:tỷ|tỉ|triệu|nghìn|ngàn|đồng)(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class MoneyMention:
    start: int
    end: int
    value: int
    written: str
    form: Literal["digits", "unit"]


def _number(raw: str) -> Decimal | None:
    """'15,5' -> 15.5 (decimal comma); '1.500' -> 1500 (thousands dot); '1.5' -> 1.5."""
    if "," in raw:
        raw = raw.replace(",", ".")
    elif "." in raw and len(raw.rsplit(".", 1)[1]) == 3:
        raw = raw.replace(".", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _unit_value(groups: str) -> int | None:
    total = Decimal(0)
    for number, unit in _GROUP_PARTS.findall(groups):
        value = _number(number)
        if value is None:
            return None
        total += value * _UNITS[unit.lower().rstrip(".")]
    return int(total.to_integral_value())


def money_mentions(text: str) -> list[MoneyMention]:
    """Every amount written with digits: full digit forms (MONEY_PATTERN) and digit + unit forms."""
    found: list[MoneyMention] = []
    for match in UNIT_MONEY_PATTERN.finditer(text):
        value = _unit_value(match.group(1))
        if value is not None:
            found.append(MoneyMention(match.start(), match.end(), value, match.group(0).strip(), "unit"))
    taken = [(m.start, m.end) for m in found]
    for match in MONEY_PATTERN.finditer(text):
        if not any(start <= match.start() < end for start, end in taken):
            found.append(MoneyMention(match.start(), match.end(), parse_money(match.group(1)), match.group(0),
                                      "digits"))
    return sorted(found, key=lambda m: m.start)


def money_values(text: str) -> set[int]:
    return {m.value for m in money_mentions(text)}


def word_amounts(text: str) -> list[str]:
    """Amounts written in words only ("mười lăm triệu đồng"): measured, never compared."""
    return [m.group(0) for m in WORD_MONEY_PATTERN.finditer(text)]
