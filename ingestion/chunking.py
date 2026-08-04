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

# Chuong/Muc headings only ever appear as a bare heading line - the roman numeral alone for
# Chuong ("Chuong I"), roman-or-arabic for Muc ("Muc I" in Bo luat TTHS, "Muc 1." in BLHS) -
# never with trailing text on the same line for Chuong, and only the numbered-with-dot form
# carries same-line title text for Muc. Anchoring to a bare/numbered-only line start is
# required, not optional: real body text cross-references a chapter by number too (e.g.
# "...quy dinh tai Chuong XIII cua Bo luat nay" in BLHS, "...theo quy dinh tai Chuong XXXIII
# cua Bo luat nay" in Bo luat TTHS), and when such a reference happens to start a wrapped
# line, a loose "^Chuong\s+[IVXLCDM]+" pattern matches it as if it were a second, bogus
# heading for that chapter number - confirmed by direct inspection of extracted text from
# both documents before this pattern was tightened.
CHUONG_PATTERN = re.compile(r"^Chương\s+([IVXLCDM]+)\s*$", re.MULTILINE)
MUC_PATTERN = re.compile(r"^Mục\s+([IVXLCDM]+|\d+)\.?[ \t]*", re.MULTILINE)

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


# "Luat to chuc toa an nhan dan.pdf" Dieu 150 quotes several OTHER laws' own numbered clauses
# verbatim as illustrative amendment text (see KNOWN_BOGUS_DIEU_MATCHES above for the sibling
# bug this is adjacent to). Its real top-level khoan ("1.", "2.", ...) are genuinely interleaved
# with those quoted laws' OWN "1.", "2." clause numbers, which KHOAN_PATTERN can't tell apart
# from real ones - splitting on every match produces multiple chunks with the SAME khoan_number
# (khoan "1" three times, khoan "2" four times - confirmed by direct inspection), which collide
# into the same deterministic Qdrant point ID (vector_store.build_point_id keys only on
# dieu_number + khoan_number) and silently drop all but the last upserted chunk. No general
# rule safely disambiguates real-vs-quoted khoan numbering here, so this specific Dieu is kept
# as a single unsplit chunk instead (~6.3k chars - large but coherent, and correctness beats
# chunk-size convention for this one-off case).
KNOWN_NO_KHOAN_SPLIT_DIEU: set[tuple[str, str]] = {
    ("Luật tổ chức toà án nhân dân.pdf", "150"),
}

# "Van ban hop nhat BLHS 2015.pdf" Dieu 189 khoan 3 is printed TWICE in the source PDF itself
# (confirmed by direct visual inspection of page 97 - both paragraphs sit as ordinary body text,
# no quote marks, no footnote marker, no "truoc day quy dinh" framing - this is a genuine
# publishing/editing error in the government's own consolidated text, NOT the "quoted excerpt
# from another law" pattern behind KNOWN_BOGUS_DIEU_MATCHES above): once reading "hang pham
# phap tri gia tu 500.000.000 dong tro len...", once reading "vat pham phap tri gia
# 500.000.000 dong tro len...". "vat pham phap" is the term used everywhere else in this same
# Dieu (khoan 1, khoan 2) and 22x across the whole document; "hang pham phap" appears nowhere
# else at all - confirmed the current/correct wording is "vat pham phap", "hang pham phap" is
# a leftover draft phrase mistakenly left in. Both share the same khoan_number "3", which
# collided into the same deterministic Qdrant point ID; by document order "vat pham phap" is
# parsed second and so already happened to win the upsert - this fix just makes chunks.json
# agree with what Qdrant already (correctly) holds instead of also carrying the wrong duplicate.
KNOWN_DUPLICATE_KHOAN_TO_DROP: dict[tuple[str, str, str], str] = {
    ("Văn bản hợp nhất BLHS 2015.pdf", "189", "3"): "hàng phạm pháp trị giá từ 500.000.000",
}


def _split_dieu_into_khoan(
    source_document: str, dieu_number: str, dieu_title: str, body: str
) -> list[tuple[str | None, str, int, int]]:
    """Returns (khoan_number, chunk_text, local_start, local_end) - the last two are offsets
    into `body` (the reconstructed, header-rewritten string, NOT full_text), used by the caller
    to compute per-segment extraction_quality instead of one value for the whole Dieu (see
    chunk_legal_text - a Dieu long enough to khoan-split can straddle a page boundary where only
    SOME khoan actually touch a bad page)."""
    if (source_document, dieu_number) in KNOWN_NO_KHOAN_SPLIT_DIEU:
        return [(None, body, 0, len(body))]

    if len(body) <= LONG_DIEU_CHAR_THRESHOLD:
        return [(None, body, 0, len(body))]

    matches = list(KHOAN_PATTERN.finditer(body))
    if len(matches) < 2:
        return [(None, body, 0, len(body))]

    header_line = f"Điều {dieu_number}. {dieu_title}"
    segments: list[tuple[str | None, str, int, int]] = []

    intro = body[:matches[0].start()].strip()
    if len(intro) > len(header_line):
        segments.append((None, intro, 0, matches[0].start()))

    dropped_duplicates = 0
    for i, match in enumerate(matches):
        khoan_number = match.group(1)
        seg_start = match.start()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        khoan_text = body[seg_start:seg_end].strip()

        drop_marker = KNOWN_DUPLICATE_KHOAN_TO_DROP.get((source_document, dieu_number, khoan_number))
        if drop_marker is not None and drop_marker in khoan_text:
            dropped_duplicates += 1
            continue

        segments.append((khoan_number, f"{header_line}\n{khoan_text}", seg_start, seg_end))

    expected_drops = sum(
        1 for (doc, dnum, _knum) in KNOWN_DUPLICATE_KHOAN_TO_DROP if doc == source_document and dnum == dieu_number
    )
    assert dropped_duplicates == expected_drops, (
        f"Known duplicate-khoan fix for {source_document} Dieu {dieu_number} expected to drop "
        f"{expected_drops} segment(s) but dropped {dropped_duplicates} - source PDF may have "
        f"been re-extracted differently; update KNOWN_DUPLICATE_KHOAN_TO_DROP."
    )

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


def _heading_title_span(text: str, match: re.Match, sorted_marker_positions: list[int]) -> str:
    """A Chuong/Muc heading's title runs from the end of the heading match to wherever the
    next marker (another Chuong, another Muc, or a Dieu) starts - real drafting never puts
    ordinary body prose directly under a bare section heading, so this boundary is exact and
    needs no wrap-continuation heuristics like the Dieu title does."""
    next_pos = next((p for p in sorted_marker_positions if p > match.start()), len(text))
    return _strip_page_number_noise(text[match.end():next_pos])


def _find_chuong_muc_events(
    text: str, dieu_starts: list[int]
) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    """Returns (chuong_events, muc_events), each a list of (start_offset, number, title) in
    document order, restricted to `text` (the same appendix-truncated span Dieu detection
    already uses - Chuong/Muc headings inside an appendix, if any, are not real document
    structure either)."""
    chuong_matches = list(CHUONG_PATTERN.finditer(text))
    muc_matches = list(MUC_PATTERN.finditer(text))
    marker_positions = sorted(
        [m.start() for m in chuong_matches] + [m.start() for m in muc_matches] + dieu_starts
    )
    chuong_events = [
        (m.start(), m.group(1), _heading_title_span(text, m, marker_positions)) for m in chuong_matches
    ]
    muc_events = [
        (m.start(), m.group(1), _heading_title_span(text, m, marker_positions)) for m in muc_matches
    ]
    return chuong_events, muc_events


def _assign_chuong_muc(
    dieu_starts: list[int],
    chuong_events: list[tuple[int, str, str]],
    muc_events: list[tuple[int, str, str]]
) -> list[tuple[str | None, str | None, str | None, str | None]]:
    """For each Dieu start offset (in the same order as dieu_starts), returns the
    (chuong_number, chuong_title, muc_number, muc_title) in force at that point - the nearest
    preceding Chuong/Muc heading. Muc numbering restarts inside each Chuong (e.g. BLHS has a
    "Muc 1" under several different Chuong), so muc is reset to None whenever a new Chuong
    marker is crossed, even before any Muc marker follows it."""
    assignments: list[tuple[str | None, str | None, str | None, str | None]] = []
    ci = 0
    mi = 0
    current_chuong_start = -1
    current_chuong: tuple[str | None, str | None] = (None, None)
    current_muc: tuple[str | None, str | None] = (None, None)

    for start in dieu_starts:
        while ci < len(chuong_events) and chuong_events[ci][0] <= start:
            current_chuong_start, cnum, ctitle = chuong_events[ci]
            current_chuong = (cnum, ctitle)
            current_muc = (None, None)
            ci += 1

        while mi < len(muc_events) and muc_events[mi][0] <= start:
            muc_start, mnum, mtitle = muc_events[mi]
            if muc_start > current_chuong_start:
                current_muc = (mnum, mtitle)
            mi += 1

        assignments.append((current_chuong[0], current_chuong[1], current_muc[0], current_muc[1]))

    return assignments


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

# "Luat to chuc toa an nhan dan.pdf" is a consolidated ("hop nhat") text with footnote markers
# recording amendment history. For 3 repealed articles whose body is nothing but "(duoc bai
# bo)", the footnote's superscript number lands fused directly onto "Dieu N." with NO
# separating space (unlike every other footnote in this doc, which attaches to the end of a
# real title/body instead) - e.g. raw text "Dieu 63.19 (duoc bai bo)" captures dieu_title as
# "19 (duoc bai bo)". Confirmed by direct inspection (grep for "^Dieu \d+\." + digit): only
# these 3 titles in the whole 148-Dieu document contain any digit at all, all identically
# shaped, all repealed placeholder articles with no other content to lose - so a small
# enumerated fix (matching the KNOWN_NON_KHOAN_TITLE_CONTINUATIONS convention above) is safer
# than a general leading-digit-strip rule that could misfire on some other document.
KNOWN_FOOTNOTE_FUSED_DIEU_TITLES: dict[tuple[str, str], str] = {
    ("Luật tổ chức toà án nhân dân.pdf", "63"): "19 ",
    ("Luật tổ chức toà án nhân dân.pdf", "79"): "25 ",
    ("Luật tổ chức toà án nhân dân.pdf", "82"): "28 ",
}


def _strip_known_footnote_fused_prefix(source_document: str, dieu_number: str, dieu_title: str) -> str:
    prefix = KNOWN_FOOTNOTE_FUSED_DIEU_TITLES.get((source_document, dieu_number))
    if prefix is None:
        return dieu_title
    assert dieu_title.startswith(prefix), (
        f"Known footnote-fused-title fix for {source_document} Dieu {dieu_number} no longer "
        f"matches the source text - source PDF may have been re-extracted differently; "
        f"update KNOWN_FOOTNOTE_FUSED_DIEU_TITLES."
    )
    return dieu_title[len(prefix):]


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



# "Luat to chuc toa an nhan dan.pdf" Dieu 150 ("Sua doi, bo sung, bai bo mot so dieu cua luat
# co lien quan") quotes verbatim excerpts from several OTHER laws' own transitional articles
# as illustrative amendment text. Every such quoted excerpt is wrapped in curly quotes (" ...")
# so its "Dieu N." header sits right after a quote-mark, which already fails DIEU_PATTERN's
# line-start anchor (real behavior, not a fix) - except ONE: the quoted excerpt from Luat Thi
# hanh an dan su's own "Dieu 116. Dieu khoan chuyen tiep" is missing its opening quote mark in
# the source PDF, so it lines up at true line start and DIEU_PATTERN wrongly matches it as if
# it were THIS document's Dieu 116 - colliding with the real "Dieu 116. Thu ky Toa an" earlier
# in the document (confirmed: exactly 2 matches for dieu_number "116", verified by direct
# inspection of both). Left unfixed, this: (a) mislabels ~10 khoan of unrelated foreign-law text
# as if they were part of "Dieu 116" of this law, (b) truncates the real Dieu 150's own body at
# that point instead of continuing to Dieu 151, and (c) collides multiple duplicate khoan
# numbers (1, 2 each appear 3-4x across the bogus fragment) into the same deterministic Qdrant
# point ID, silently dropping all but the last one on upsert. Filtered out by exact
# (source_document, dieu_number, title-first-line) match, verified by count, so ingestion fails
# loudly (assert) if a re-typeset source document changes the false-positive count.
KNOWN_BOGUS_DIEU_MATCHES: dict[tuple[str, str], tuple[str, int]] = {
    ("Luật tổ chức toà án nhân dân.pdf", "116"): ("Điều khoản chuyển tiếp", 1),
}


def _filter_known_bogus_dieu_matches(source_document: str, matches: list[re.Match]) -> list[re.Match]:
    if not KNOWN_BOGUS_DIEU_MATCHES:
        return matches

    removed_counts: dict[tuple[str, str], int] = {}
    kept: list[re.Match] = []
    for match in matches:
        key = (source_document, match.group(1))
        bogus_title, expected_count = KNOWN_BOGUS_DIEU_MATCHES.get(key, (None, 0))
        if bogus_title is not None and match.group(2).strip() == bogus_title:
            removed_counts[key] = removed_counts.get(key, 0) + 1
            continue
        kept.append(match)

    for key, (bogus_title, expected_count) in KNOWN_BOGUS_DIEU_MATCHES.items():
        if key[0] != source_document:
            continue
        actual = removed_counts.get(key, 0)
        # <= not ==: callers may parse a single-page/partial slice of the document (e.g. the
        # Tesseract rescue pass in rescue_unusable_chunks.py, which re-chunks one rendered page
        # at a time) where the bogus match's page legitimately isn't present at all (actual=0
        # is then correct, not a drift signal). Over-removal (actual > expected) is still the
        # real drift signal this assert guards against - it would mean the pattern now also
        # matches something it shouldn't.
        assert actual <= expected_count, (
            f"Known bogus-Dieu-match fix for {key[0]} Dieu {key[1]} expected to remove at most "
            f"{expected_count} match(es) but removed {actual} - source PDF may have been "
            f"re-extracted differently; update KNOWN_BOGUS_DIEU_MATCHES."
        )

    return kept


# The "Noi nhan" (cc/distribution list) at the very end of "Thong tu lien tich
# 01_2026...pdf"'s last Dieu (39, "To chuc thuc hien") is corrupted by the same
# character-duplication artifact seen elsewhere in this raw_documents folder (confirmed by
# direct inspection: "NNooi i nnhhaann" instead of "Noi nhan") - it drags is_text_garbage's
# ratio over threshold for the WHOLE chunk even though the real legal content just before it
# (khoan 1, 2, and the signing officials' block) is completely clean. It is pure administrative
# boilerplate (who the document was cc'd to), not part of Dieu 39's actual legal content, so
# dropping it loses nothing - truncated out before quality is computed, not just cosmetically
# trimmed after, so the surviving text is correctly classified "ok" instead of "unusable".
KNOWN_TRAILING_BOILERPLATE_MARKERS: dict[tuple[str, str], str] = {
    ("Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf", "39"): "Nơi nhận",
}


def _truncate_known_trailing_boilerplate(
    source_document: str, dieu_number: str, full_text: str, start: int, end: int
) -> int:
    marker = KNOWN_TRAILING_BOILERPLATE_MARKERS.get((source_document, dieu_number))
    if marker is None:
        return end
    marker_pos = full_text.find(marker, start, end)
    assert marker_pos != -1, (
        f"Known trailing-boilerplate fix for {source_document} Dieu {dieu_number} - marker "
        f"{marker!r} no longer found - source PDF may have been re-extracted differently; "
        f"update KNOWN_TRAILING_BOILERPLATE_MARKERS."
    )
    return marker_pos


def chunk_legal_text(pages: list[PageExtraction], source_document: str, law_version: str) -> list[dict[str, Any]]:
    full_text, offsets = _build_document_text(pages)

    appendix_match = APPENDIX_HEADING_PATTERN.search(full_text)
    dieu_search_text = full_text[:appendix_match.start()] if appendix_match else full_text

    matches = list(DIEU_PATTERN.finditer(dieu_search_text))
    matches = _filter_known_bogus_dieu_matches(source_document, matches)
    dieu_starts = [m.start() for m in matches]
    chuong_events, muc_events = _find_chuong_muc_events(dieu_search_text, dieu_starts)
    chuong_muc_assignments = _assign_chuong_muc(dieu_starts, chuong_events, muc_events)
    chunks: list[dict[str, Any]] = []

    for i, match in enumerate(matches):
        chuong_number, chuong_title, muc_number, muc_title = chuong_muc_assignments[i]
        dieu_number = match.group(1)
        # Strip a page number fused directly onto the captured line-1 title (e.g. "...hinh
        # su10") before any wrap-merge logic runs - same noise pattern as mid-title page
        # breaks, just landing on line 1 itself instead of a later line.
        dieu_title = TRAILING_PAGE_NUMBER_PATTERN.sub("", match.group(2).strip()).strip()
        dieu_title = _strip_known_footnote_fused_prefix(source_document, dieu_number, dieu_title)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(dieu_search_text)
        end = _truncate_known_trailing_boilerplate(source_document, dieu_number, full_text, start, end)
        raw_body = full_text[start:end]
        body = raw_body.strip()
        left_strip = len(raw_body) - len(raw_body.lstrip())
        body_start_in_full_text = start + left_strip

        title_line_end = body.find("\n")
        rest_offset_in_full_text: int | None = None
        if title_line_end != -1:
            dieu_title, skip = _apply_known_title_continuation(
                source_document, dieu_number, dieu_title, body[title_line_end + 1:]
            )
            if skip == 0:
                dieu_title, skip = _merge_wrapped_title(dieu_title, body[title_line_end + 1:])
            rest = body[title_line_end + 1 + skip:]
            rest_offset_in_full_text = body_start_in_full_text + title_line_end + 1 + skip
            header_line = f"Điều {dieu_number}. {dieu_title}"
            body = f"{header_line}\n{rest}"
            header_len = len(header_line) + 1
        else:
            body = f"Điều {dieu_number}. {dieu_title}"
            header_len = len(body)

        whole_method, whole_quality = _aggregate_quality(offsets, start, end)

        def _local_to_global(local_offset: int) -> int:
            # Offsets inside the (possibly rewritten) header line have no exact source - any
            # point in there is still part of the same Dieu's opening page, so start is a
            # correct enough anchor for quality lookup purposes.
            if rest_offset_in_full_text is None or local_offset <= header_len:
                return start
            return rest_offset_in_full_text + (local_offset - header_len)

        segments = _split_dieu_into_khoan(source_document, dieu_number, dieu_title, body)
        single_segment = len(segments) == 1

        for khoan_number, chunk_text, seg_local_start, seg_local_end in segments:
            if single_segment:
                method, quality = whole_method, whole_quality
            else:
                # A khoan-split Dieu can straddle a page boundary where only SOME khoan
                # actually touch a bad page - compute quality from this segment's own span
                # instead of reusing the whole-Dieu aggregate, so clean khoan aren't punished
                # for a different khoan's bad page (confirmed real case: Luat to chuc toa an
                # nhan dan Dieu 152 khoan 1-4 live entirely on a clean page but khoan 5 touches
                # a RECITATION-blocked one - see requirements.md Phase 5a/5b v2 Buoc A notes).
                method, quality = _aggregate_quality(
                    offsets, _local_to_global(seg_local_start), _local_to_global(seg_local_end)
                )

            chunks.append({
                "source_type": "legal_text",
                "source_document": source_document,
                "law_version": law_version,
                "dieu_number": dieu_number,
                "dieu_title": dieu_title,
                "khoan_number": khoan_number,
                "chuong_number": chuong_number,
                "chuong_title": chuong_title,
                "muc_number": muc_number,
                "muc_title": muc_title,
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
