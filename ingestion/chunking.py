"""Chunking strategies dispatched by source_type:
- legal_text: split strictly on "Dieu X." boundaries (one chunk per Dieu, or per Khoan
  when a Dieu is unusually long). No fixed-token splitter, per requirements.md.
- academic_reference: split on heading lines, then group whole paragraphs up to a target
  size without ever cutting mid-sentence.
"""
from __future__ import annotations

import re
from typing import Any

from ingestion.pdf_extraction import PageExtraction

# Decrees/circulars often end with appendix form templates ("PHU LUC" + "Mau so ...") that
# contain their own illustrative "Dieu 1/2/3/4" boilerplate (e.g. a sample decision form).
# Those are not real provisions of the document and their repeated "Dieu 4" etc. would
# otherwise collide with (and duplicate-shadow) the real Dieu 4 - verified against real
# output on Nghi dinh 250 where one appendix alone produced 7 bogus "Dieu 4, Khoan 1" chunks.
APPENDIX_HEADING_PATTERN = re.compile(r"^PHỤ LỤC(\s+[IVXLCDM]+)?\s*$", re.MULTILINE)

# Amended Vietnamese codes insert new articles alongside an existing number using a letter
# suffix (e.g. "Dieu 217a" inserted next to "Dieu 217" in BLHS) - without the [a-z]? here,
# "217a." fails to match at all (digits followed by "." doesn't fit "217a."), so its content
# silently gets absorbed as trailing body text into the PRECEDING Dieu's chunk instead of
# becoming its own chunk. Verified against real source PDFs, not a hypothetical case.
#
# Two independent font/encoding glitches confirmed by codepoint inspection, each dropping
# an isolated "Dieu N." header from a DIFFERENT source PDF (silently merging that Dieu's
# content into the preceding one, causing duplicate dieu_number+khoan_number chunks):
#   - Nghi dinh 250: "Dieu" survives, but the tone mark is dropped on the second syllable
#     ("e" U+00EA instead of the correct "e-grave-hook" U+1EC1) -> "Đieu" not "Điều".
#   - Van ban hop nhat BLHS: the leading D is the WRONG Unicode character - Latin Ð (U+00D0,
#     as in Icelandic) instead of Vietnamese Đ (U+0110) - visually identical, byte-different.
# Tolerating both keeps every real Dieu header matching regardless of which glitch hit it.
DIEU_PATTERN = re.compile(r"^[ĐÐ]i[êề]u\s+(\d+[a-z]?)\.\s*(.+)$", re.MULTILINE)
KHOAN_PATTERN = re.compile(r"^(\d{1,2})\.\s+", re.MULTILINE)

# A Dieu longer than this is split into per-Khoan chunks instead of staying as one chunk.
LONG_DIEU_CHAR_THRESHOLD = 2500

HEADING_PATTERN = re.compile(
    r"^(?:[IVXLCDM]+\.\s+[A-ZÀ-Ỹ]|(?:\d+\.){1,3}\s+[A-ZÀ-Ỹ]|[A-ZÀ-Ỹ\s,\-]{8,80})$"
)
TARGET_CHUNK_CHARS = 1400
MIN_HEADING_LINE_LEN = 4
MAX_HEADING_LINE_LEN = 90

QualityRank = {"ok": 0, "degraded": 1, "unusable": 2}


def _build_document_text(pages: list[PageExtraction]) -> tuple[str, list[tuple[int, int, PageExtraction]]]:
    full_text = ""
    offsets: list[tuple[int, int, PageExtraction]] = []
    for page in pages:
        start = len(full_text)
        full_text += page.text + "\n"
        end = len(full_text)
        offsets.append((start, end, page))
    return full_text, offsets


def _aggregate_quality(offsets: list[tuple[int, int, PageExtraction]], start: int, end: int) -> tuple[str, str]:
    overlapping = [page for (page_start, page_end, page) in offsets if page_end > start and page_start < end]
    if not overlapping:
        return "text_layer", "ok"

    methods = {page.extraction_method for page in overlapping}
    worst_quality = max((page.extraction_quality for page in overlapping), key=lambda q: QualityRank[q])
    method = methods.pop() if len(methods) == 1 else "mixed"
    return method, worst_quality


def _split_dieu_into_khoan(dieu_number: str, dieu_title: str, body: str) -> list[tuple[str | None, str]]:
    if len(body) <= LONG_DIEU_CHAR_THRESHOLD:
        return [(None, body)]

    matches = list(KHOAN_PATTERN.finditer(body))
    if len(matches) < 2:
        return [(None, body)]

    header_line = f"Điều {dieu_number}. {dieu_title}"
    segments: list[tuple[str | None, str]] = []

    intro = body[:matches[0].start()].strip()
    if len(intro) > len(header_line):
        segments.append((None, intro))

    for i, match in enumerate(matches):
        khoan_number = match.group(1)
        seg_start = match.start()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        khoan_text = body[seg_start:seg_end].strip()
        segments.append((khoan_number, f"{header_line}\n{khoan_text}"))

    return segments


MAX_TITLE_CONTINUATION_LINE_LEN = 80
MAX_MERGED_TITLE_LEN = 140
MAX_KHOAN_AWARE_MERGED_TITLE_LEN = 220

# A page break inside a Dieu's title span sometimes injects the page's footer/header page
# number as stray text - either as its own line, or fused directly onto the end of a word with
# no separating space (confirmed by direct inspection: Dieu 7 "...hinh su10", Dieu 41 a lone
# "20" line, Dieu 476/477/506a "...toi cao224" etc). Stripped wherever a title span is built,
# not just at the one Dieu it was first noticed on (Phase 5a manual fix, generalized here).
PAGE_NUMBER_LINE_PATTERN = re.compile(r"^\d{1,4}$", re.MULTILINE)
TRAILING_PAGE_NUMBER_PATTERN = re.compile(r"(?<=[a-zà-ỹ])\d{1,4}$", re.IGNORECASE)

# A title continuation fragment never contains its own terminal punctuation - if the text before
# a Khoan marker does, it's a real (rare) preamble sentence, not a wrapped title. Includes ":"
# because Vietnamese legal drafting commonly introduces an enumerated Khoan list with a
# colon-terminated lead sentence (e.g. Dieu 223 "...co the ap dung cac bien phap dieu tra to
# tung dac biet:" before "1. Ghi am...") - confirmed by direct inspection after this exact
# pattern caused a false-positive merge (Dieu 223/224/300/393/98 in the first pass).
SENTENCE_END_PATTERN = re.compile(r"[.!?:]")

# A Dieu title is a noun phrase. If it wraps onto a second physical line, the first line
# necessarily breaks off mid-phrase - it ends on a function word that cannot stand alone
# (a preposition/conjunction needing an object). A title that already ends on an ordinary
# noun (e.g. "...giam doc tham") is grammatically complete and should NOT swallow the next
# line, even if that line happens to be short - it's the start of the Dieu's body text. Used
# only as the fallback for Dieu with no nearby Khoan marker (see _merge_wrapped_title) - a
# "first sentence-punctuation" boundary was tried and rejected for that case (Phase 6 decision
# log): a short genuine continuation and a short complete body sentence are indistinguishable
# by that signal alone, so the safer trigger-word gate is kept there.
TITLE_CONTINUATION_TRIGGER_WORDS = {
    "bị", "về", "của", "cho", "và", "với", "theo", "tại", "trong", "khi", "để", "do",
    "là", "hay", "hoặc", "các", "những", "khỏi", "đến", "từ", "trên", "dưới", "sau", "trước"
}


def _strip_page_number_noise(text: str) -> str:
    cleaned = PAGE_NUMBER_LINE_PATTERN.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = TRAILING_PAGE_NUMBER_PATTERN.sub("", cleaned).strip()
    return cleaned


def _merge_wrapped_title_khoan_aware(dieu_title: str, body_after_title_line: str) -> tuple[str, int]:
    """For Dieu that have Khoan structure, real BLTTHS/BLHS/etc. drafting never inserts a
    preamble sentence between the title and Khoan 1 (verified against the corpus - every
    Khoan-structured Dieu goes straight from title to "1. ..."). So any text between the
    (possibly line-1-only) captured title and the first Khoan marker is unconditionally a
    wrapped continuation of the title, not real content - no trigger-word guessing needed, this
    boundary is exact."""
    khoan_match = KHOAN_PATTERN.search(body_after_title_line)
    if not khoan_match or khoan_match.start() == 0:
        return dieu_title, 0

    continuation = _strip_page_number_noise(body_after_title_line[:khoan_match.start()])
    if not continuation or SENTENCE_END_PATTERN.search(continuation):
        return dieu_title, 0

    merged = f"{dieu_title} {continuation}".strip()
    if len(merged) > MAX_KHOAN_AWARE_MERGED_TITLE_LEN:
        return dieu_title, 0

    return merged, khoan_match.start()


def _merge_wrapped_title(dieu_title: str, body_after_title_line: str) -> tuple[str, int]:
    """Titles that wrap onto a second physical line (common for longer Dieu titles) would
    otherwise get truncated by DIEU_PATTERN, which only captures the first line. Two
    strategies, tried in order:
    1. Khoan-aware (_merge_wrapped_title_khoan_aware): exact, unconditional, for Dieu with a
       nearby Khoan marker.
    2. Trigger-word fallback (original heuristic): for Dieu with no nearby Khoan marker (short
       single-paragraph Dieu), only merge when the title's last word looks grammatically
       incomplete - avoids swallowing the start of flowing body prose.
    Returns (full_title, chars_to_skip_from_body_start)."""
    khoan_aware_title, khoan_aware_skip = _merge_wrapped_title_khoan_aware(dieu_title, body_after_title_line)
    if khoan_aware_skip:
        return khoan_aware_title, khoan_aware_skip

    last_word = dieu_title.split()[-1].lower() if dieu_title.split() else ""
    if last_word not in TITLE_CONTINUATION_TRIGGER_WORDS:
        return dieu_title, 0

    next_line_end = body_after_title_line.find("\n")
    next_line = body_after_title_line if next_line_end == -1 else body_after_title_line[:next_line_end]
    next_line = _strip_page_number_noise(next_line)

    if (
        next_line
        and not KHOAN_PATTERN.match(next_line)
        and len(next_line) <= MAX_TITLE_CONTINUATION_LINE_LEN
        and len(dieu_title) + len(next_line) <= MAX_MERGED_TITLE_LEN
    ):
        merged = f"{dieu_title} {next_line}".strip()
        skip = next_line_end + 1 if next_line_end != -1 else len(body_after_title_line)
        return merged, skip

    return dieu_title, 0


# Explicit, hand-verified fixes for the non-Khoan Dieu whose title wraps in a way no general
# regex rule safely catches. Background (see requirements.md Phase 3 bug history): after the
# Khoan-aware rule shipped, ~35-40 non-Khoan Dieu were still known to have a truncated title.
# Two general-rule extensions were tried and REJECTED after concrete testing surfaced real
# regressions against already-correct titles:
#   1. "Merge everything up to the first terminal punctuation" (mirroring the Khoan-aware rule)
#      - fails on Dieu 15 ("Xac dinh su that cua vu an"): its very next sentence
#        ("Trach nhiem chung minh toi pham thuoc ve co quan...") is short enough to fit under any
#        reasonable length cap, so it gets wrongly absorbed into the title.
#   2. "Merge the next line unless it contains an independent-clause verb marker (la/co/duoc/
#      thuoc/...)" - catches Dieu 15, but still wrongly merges e.g. Dieu 1 ("Pham vi dieu
#      chinh"), 24, 26, 96, 212, 216, 220, 306, 327, 366, 408, 455, 458, 468 - their real next
#      sentence just doesn't happen to contain any of the tried verb markers within the length
#      cap either.
# Every non-Khoan Dieu across all 5 legal_text documents (152 candidates) was read by hand
# instead, and classified true/false positive. The confirmed true positives (37, close to but
# not exactly the earlier ~35 estimate - see requirements.md) are listed here explicitly rather
# than covered by a generalized rule, since the corpus is finite and fully enumerated - safer
# than risking new corruption across the ~115 already-correct titles in the same "no Khoan"
# bucket. Keyed by (source_document, dieu_number) -> the literal raw text that continues the
# title, exactly as it appears right after the title's captured first line (including any
# interspersed page-number/footnote-only line, e.g. Dieu 356's "177"). Matched by exact
# substring at position 0 so ingestion fails loudly (assert) if a re-typeset source document
# ever stops matching, instead of silently mis-applying a stale fix.
KNOWN_NON_KHOAN_TITLE_CONTINUATIONS: dict[tuple[str, str], str] = {
    ("Bộ luật TTHS.pdf", "8"): "pháp của cá nhân",
    ("Bộ luật TTHS.pdf", "11"): "nhân; danh dự, uy tín, tài sản của pháp nhân",
    ("Bộ luật TTHS.pdf", "12"):
        "tư, bí mật cá nhân, bí mật gia đình, an toàn và bí mật thư tín, điện thoại, điện\n"
        "tín của cá nhân",
    ("Bộ luật TTHS.pdf", "16"): "và lợi ích hợp pháp của bị hại, đương sự",
    ("Bộ luật TTHS.pdf", "20"): "theo pháp luật trong tố tụng hình sự11",
    ("Bộ luật TTHS.pdf", "21"): "tham gia tố tụng",
    ("Bộ luật TTHS.pdf", "95"):
        "bị tố giác, người bị kiến nghị khởi tố, người phạm tội tự thú, đầu thú, người\n"
        "bị bắt, bị tạm giữ",
    ("Bộ luật TTHS.pdf", "102"): "56\nphạm, khởi tố, điều tra, truy tố, xét xử",
    ("Bộ luật TTHS.pdf", "116"): "người",
    ("Bộ luật TTHS.pdf", "151"): "quyền tiến hành tố tụng trực tiếp phát hiện",
    ("Bộ luật TTHS.pdf", "168"):
        "hiện quyết định, yêu cầu của Cơ quan điều tra, cơ quan được giao nhiệm vụ\n"
        "tiến hành một số hoạt động điều tra, Viện kiểm sát",
    ("Bộ luật TTHS.pdf", "200"): "xét, thu giữ, tạm giữ",
    ("Bộ luật TTHS.pdf", "241"): "chế",
    ("Bộ luật TTHS.pdf", "265"): "pháp luật",
    ("Bộ luật TTHS.pdf", "270"):
        "của nước Cộng hòa xã hội chủ nghĩa Việt Nam đang hoạt động ngoài không\n"
        "phận hoặc ngoài lãnh hải của Việt Nam",
    ("Bộ luật TTHS.pdf", "302"):
        "sát viên, Thư ký Tòa án, người giám định, người định giá tài sản, người phiên\n"
        "dịch, người dịch thuật",
    ("Bộ luật TTHS.pdf", "303"): "giám định, người định giá tài sản",
    ("Bộ luật TTHS.pdf", "305"): "khi có người vắng mặt",
    ("Bộ luật TTHS.pdf", "317"): "hành tố tụng, người tham gia tố tụng trình bày ý kiến",
    ("Bộ luật TTHS.pdf", "319"): "hơn tại phiên tòa",
    ("Bộ luật TTHS.pdf", "343"): "có kháng cáo, kháng nghị",
    ("Bộ luật TTHS.pdf", "356"): "án sơ thẩm\n177",
    ("Bộ luật TTHS.pdf", "377"): "đốc thẩm",
    ("Bộ luật TTHS.pdf", "389"): "định đã có hiệu lực pháp luật bị kháng nghị",
    ("Bộ luật TTHS.pdf", "390"):
        "bản án, quyết định đúng pháp luật của Tòa án cấp sơ thẩm hoặc Tòa án cấp\n"
        "193\n"
        "phúc thẩm bị hủy, sửa không đúng pháp luật",
    ("Bộ luật TTHS.pdf", "391"): "lại hoặc xét xử lại",
    ("Bộ luật TTHS.pdf", "392"): "án",
    ("Bộ luật TTHS.pdf", "412"):
        "cao về việc xem xét lại quyết định của Hội đồng Thẩm phán Tòa án nhân dân\n"
        "tối cao",
    ("Bộ luật TTHS.pdf", "494"): "quốc tế trong tố tụng hình sự",
    ("Bộ luật TTHS.pdf", "495"): "Nam ở nước ngoài và người có thẩm quyền của nước ngoài ở Việt Nam",
    ("Bộ luật TTHS.pdf", "506a"): "dẫn độ237",
    ("Văn bản hợp nhất BLHS 2015.pdf", "25"): "thuật và công nghệ",
    ("Văn bản hợp nhất BLHS 2015.pdf", "41"): "định",
    ("Văn bản hợp nhất BLHS 2015.pdf", "74"): "phạm tội",
    ("Văn bản hợp nhất BLHS 2015.pdf", "181"): "bộ, cản trở ly hôn tự nguyện",
    ("Văn bản hợp nhất BLHS 2015.pdf", "347"): "trái phép",
    ("Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf", "30"):
        "trưởng, Kiểm sát viên trong trường hợp ủy thác điều tra",
}


def _apply_known_title_continuation(source_document: str, dieu_number: str, dieu_title: str,
                                     body_after_title_line: str) -> tuple[str, int]:
    continuation = KNOWN_NON_KHOAN_TITLE_CONTINUATIONS.get((source_document, dieu_number))
    if continuation is None:
        return dieu_title, 0

    idx = body_after_title_line.find(continuation)
    assert idx == 0, (
        f"Known title-continuation fix for {source_document} Dieu {dieu_number} no longer "
        f"matches the source text at the expected position - source PDF may have been "
        f"re-extracted differently; update KNOWN_NON_KHOAN_TITLE_CONTINUATIONS."
    )
    skip = len(continuation)
    merged = f"{dieu_title} {_strip_page_number_noise(continuation)}".strip()
    return merged, skip


def chunk_legal_text(pages: list[PageExtraction], source_document: str, law_version: str) -> list[dict[str, Any]]:
    full_text, offsets = _build_document_text(pages)

    appendix_match = APPENDIX_HEADING_PATTERN.search(full_text)
    dieu_search_text = full_text[:appendix_match.start()] if appendix_match else full_text

    matches = list(DIEU_PATTERN.finditer(dieu_search_text))
    chunks: list[dict[str, Any]] = []

    for i, match in enumerate(matches):
        dieu_number = match.group(1)
        # Strip a page number fused directly onto the captured line-1 title (e.g. "...hinh
        # su10") before any wrap-merge logic runs - same noise pattern as mid-title page
        # breaks, just landing on line 1 itself instead of a later line.
        dieu_title = TRAILING_PAGE_NUMBER_PATTERN.sub("", match.group(2).strip()).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(dieu_search_text)
        body = full_text[start:end].strip()

        title_line_end = body.find("\n")
        if title_line_end != -1:
            dieu_title, skip = _apply_known_title_continuation(
                source_document, dieu_number, dieu_title, body[title_line_end + 1:]
            )
            if skip == 0:
                dieu_title, skip = _merge_wrapped_title(dieu_title, body[title_line_end + 1:])
            rest = body[title_line_end + 1 + skip:]
            body = f"Điều {dieu_number}. {dieu_title}\n{rest}"
        else:
            body = f"Điều {dieu_number}. {dieu_title}"

        method, quality = _aggregate_quality(offsets, start, end)

        for khoan_number, chunk_text in _split_dieu_into_khoan(dieu_number, dieu_title, body):
            chunks.append({
                "source_type": "legal_text",
                "source_document": source_document,
                "law_version": law_version,
                "dieu_number": dieu_number,
                "dieu_title": dieu_title,
                "khoan_number": khoan_number,
                "chunk_index": None,
                "section_heading": None,
                "chunk_text": chunk_text,
                "extraction_method": method,
                "extraction_quality": quality
            })

    return chunks


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not (MIN_HEADING_LINE_LEN <= len(stripped) <= MAX_HEADING_LINE_LEN):
        return False
    return bool(HEADING_PATTERN.match(stripped))


def _split_into_paragraphs(text: str) -> list[tuple[str | None, str]]:
    """Returns (heading_or_None, paragraph_text) pairs, in document order."""
    lines = text.split("\n")
    paragraphs: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        joined = "\n".join(current_lines).strip()
        if joined:
            paragraphs.append((current_heading, joined))

    for line in lines:
        if line.strip() == "":
            flush()
            current_lines.clear()
            continue

        if _is_heading_line(line):
            flush()
            current_lines.clear()
            current_heading = line.strip()
            continue

        current_lines.append(line)

    flush()
    return paragraphs


def chunk_academic_reference(pages: list[PageExtraction], source_document: str) -> list[dict[str, Any]]:
    full_text, offsets = _build_document_text(pages)
    paragraphs = _split_into_paragraphs(full_text)

    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    buffer_heading: str | None = None
    buffer_text = ""
    buffer_start_offset = 0
    cursor = 0

    def flush(end_offset: int) -> None:
        nonlocal chunk_index, buffer_text
        if not buffer_text.strip():
            return
        method, quality = _aggregate_quality(offsets, buffer_start_offset, end_offset)
        chunks.append({
            "source_type": "academic_reference",
            "source_document": source_document,
            "law_version": None,
            "dieu_number": None,
            "dieu_title": None,
            "khoan_number": None,
            "chunk_index": chunk_index,
            "section_heading": buffer_heading,
            "chunk_text": buffer_text.strip(),
            "extraction_method": method,
            "extraction_quality": quality
        })
        chunk_index += 1
        buffer_text = ""

    for heading, paragraph in paragraphs:
        paragraph_offset = full_text.find(paragraph, cursor)
        if paragraph_offset == -1:
            paragraph_offset = cursor
        cursor = paragraph_offset + len(paragraph)

        if heading != buffer_heading and buffer_text:
            flush(paragraph_offset)

        if not buffer_text:
            buffer_heading = heading
            buffer_start_offset = paragraph_offset

        candidate = f"{buffer_text}\n\n{paragraph}" if buffer_text else paragraph
        if len(candidate) > TARGET_CHUNK_CHARS and buffer_text:
            flush(paragraph_offset)
            buffer_heading = heading
            buffer_start_offset = paragraph_offset
            buffer_text = paragraph
        else:
            buffer_text = candidate

    flush(len(full_text))
    return chunks
