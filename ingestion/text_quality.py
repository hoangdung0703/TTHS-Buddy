"""Heuristic to detect when text-layer PDF extraction failed or produced garbage
(broken font CMap), triggering the OCR fallback path in pdf_extraction.py."""
from __future__ import annotations

VIETNAMESE_DIACRITIC_CHARS = set(
    "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    "ùúụủũưừứựửữỳýỵỷỹđ"
    "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ"
    "ÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ"
)

# Below this length, a diacritic-ratio check is unreliable (short headers/page numbers
# are legitimately diacritic-sparse), so short text is assumed OK.
MIN_TEXT_LENGTH_FOR_QUALITY_CHECK = 80

# Empirically, genuine Vietnamese legal/academic prose has a diacritic ratio well above
# this (observed 15%+); corrupted CMap-font text (e.g. the "đã nén" giáo trình PDF) drops
# to ~0% because the wrong glyphs strip the accent marks entirely.
MIN_DIACRITIC_RATIO = 0.05


def is_text_garbage(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) == 0:
        return True

    if len(stripped) < MIN_TEXT_LENGTH_FOR_QUALITY_CHECK:
        return False

    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return True

    diacritic_ratio = sum(1 for char in letters if char in VIETNAMESE_DIACRITIC_CHARS) / len(letters)
    return diacritic_ratio < MIN_DIACRITIC_RATIO
