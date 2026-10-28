"""Text layout convention for AI speech and the indictment (chặng 3D). The frontend relies on it:

- paragraphs are separated by exactly one blank line;
- a line starting with "- " is a bullet; other single line breaks are kept as line breaks;
- no markdown (no **, #, *).

The prompts ask for this layout; `format_speech` enforces the mechanical part by CODE after
generation (the model is not trusted with it). It only removes markup and whitespace, never words or
numbers, so every guard sees the same content as before.
"""
from __future__ import annotations

import re

# Above this many characters a segment utterance (khai mạc, giải thích quyền) keeps its paragraphs;
# at or below it, the utterance is flattened to one paragraph like any short line.
LONG_TEXT_MIN_CHARS = 600

INDICTMENT_SECTIONS = ("I. Nội dung vụ án", "II. Hành vi phạm tội và chứng cứ", "III. Nhân thân và tình tiết",
                       "IV. Kết luận và truy tố")

_HEADING_MARK = re.compile(r"^\s{0,3}#{1,6}\s*")
_BULLET_MARK = re.compile(r"^\s*[*•+●▪–—-]\s+")
_EMPHASIS = re.compile(r"\*+|__|`")
_SPACES = re.compile(r"[ \t ]+")
_BLANK_RUN = re.compile(r"\n{3,}")


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _HEADING_MARK.sub("", raw)
        line = _BULLET_MARK.sub("- ", line)
        bullet = line.startswith("- ")
        line = _SPACES.sub(" ", _EMPHASIS.sub("", line)).strip()
        if bullet and not line.startswith("- "):
            line = "- " + line.lstrip("- ")
        lines.append("" if line == "-" else line)
    return lines


def format_speech(text: str, multi_paragraph: bool) -> str:
    """Normalise one AI text to the layout convention. `multi_paragraph=False` flattens it to a
    single paragraph (short lines: questions, answers, lay testimony)."""
    lines = _clean_lines(text)
    if not multi_paragraph:
        return " ".join(line[2:] if line.startswith("- ") else line for line in lines if line)
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip("\n")


def format_utterance(text: str) -> str:
    """Segment utterances: paragraphs are kept only for a long line (khai mạc, giải thích quyền)."""
    formatted = format_speech(text, multi_paragraph=True)
    return formatted if len(formatted) > LONG_TEXT_MIN_CHARS else format_speech(text, multi_paragraph=False)


def paragraphs(text: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


def indictment_sections(text: str) -> list[str]:
    """The INDICTMENT_SECTIONS headings found on a line of their own (case-insensitive)."""
    lines = [line.strip().casefold() for line in text.split("\n")]
    return [heading for heading in INDICTMENT_SECTIONS
            if any(line.startswith(heading.casefold()) and len(line) <= len(heading) + 20 for line in lines)]
