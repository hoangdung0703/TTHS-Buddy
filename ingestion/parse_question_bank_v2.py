"""Phase 5a/5b v2 Buoc B: parses "Toi hoi ban tra loi (2).pdf" into the new 4-category essay
question bank (Ly thuyet / Van dung / Ban trac nghiem / Tinh huong - 111 cau total, replacing
the old flat 30-essay + 15-mcq_true_false pool entirely), and reshuffles the 75 mcq_4choice
questions from "Cau hoi trac nghiem.pdf" into 15 sets of 5 (dropping the old 5x15 layout and
the 15 mcq_true_false questions per the final decision recorded in requirements.md).

Real format of the source PDF (confirmed by direct inspection, NOT assumed to match the old
file - see parse notes below for every deviation found):
  - "Ban trac nghiem" (50 cau) and "Tinh huong" (15 cau): NO "Tu khoa cho bai hoc" bullets at
    all - essay_key_points must be EXTRACTED via LLM from the existing Giai thich/answer text
    (grounded extraction, not normalization of pre-existing bullets).
  - "Ly thuyet" (20 cau) and "Van dung" (26 cau): DO have bullets like the old file, but 2
    items (Ly thuyet #16, Van dung #26) have none at all - same LLM-extraction fallback used
    for those two only.
  - Diacritic spelling of "khoa/khoa" varies ("Tu khoa:" vs "Tu khoa cho bai hoc:"), the colon
    after "Tu khoa" is sometimes missing entirely, and one legal-basis label alternates between
    "Can cu phap ly" and "Co so phap ly" - all tolerated by the regexes below.
  - "Tinh huong" has no single consistent answer-marker: 8 items use "- Dap an:", 5 use "Tra
    loi:", and 2 (items 13, 15) have NO marker at all (the answer just continues straight from
    the question) - handled via a small hardcoded split-point table, same convention as
    chunking.py's KNOWN_* dicts for one-off source-text irregularities.

Usage:
    python -m ingestion.parse_question_bank_v2
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

import pdfplumber

from ingestion.config import QUESTION_BANK_OUTPUT_PATH, RAW_DOCUMENTS_DIR
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.parse_question_bank import (
    DEFAULT_MCQ_PDF,
    QuestionBankEntry,
    _extract_first_dieu_number,
    _fallback_normalize_bullet,
    _load_bltths_dieu_title_lookup,
    _normalize_whitespace,
    parse_mcq_4choice,
)
from ingestion.qb_llm_client import generate_text
from ingestion.qb_prompts import (
    EXTRACT_KEY_POINTS_SYSTEM_PROMPT,
    NORMALIZE_KEY_POINTS_SYSTEM_PROMPT,
    build_extract_key_points_prompt,
    build_normalize_key_points_prompt,
)

logger = get_logger(__name__)

DEFAULT_QA2_PDF = RAW_DOCUMENTS_DIR / "Tôi hỏi bạn trả lời (2).pdf"

# Fixed seed for the MCQ reshuffle, per requirements.md decision - documented here (not just
# logged) so the exact 15-set layout is reproducible from source if ever re-run.
MCQ_RESHUFFLE_SEED = 20260804

BULLET_PATTERN = re.compile(r"●\s*(.*?)(?=●|\Z)", re.DOTALL)

BAN_TRAC_NGHIEM_PATTERN = re.compile(
    r"^\d+\.\s*(.*?)\s*"
    r"^Đáp án:\s*(Đúng|Sai)[.,]?\s*"
    r"(?:^(?:Căn cứ pháp lý|Cơ sở pháp lý):\s*(.*?)\s*)?"
    r"^Giải thích:\s*(.*?)"
    r"(?=^\d+\.\s*[“\"]|\Z)",
    re.DOTALL | re.MULTILINE
)

# Same field order as the old ESSAY_PATTERN (Dap an / [legal basis] / [Tu khoa bullets]), but
# both optional groups made non-mandatory - confirmed by direct inspection that Ly thuyet #16
# and Van dung #26 lack bullets, so a version requiring them silently mis-merged neighboring
# questions during development (verified count went 20/26 -> wrong numbers before this fix).
LY_THUYET_VAN_DUNG_PATTERN = re.compile(
    r"^\d+\.\s*(.*?)\s*"
    r"^⇒\s*Đáp án\s*:\s*(.*?)\s*"
    r"(?:^⇒\s*(?:Cơ sở pháp lý|Căn cứ pháp lý):\s*(.*?)\s*)?"
    r"(?:^⇒\s*Từ kh\S{1,3}\s*(?:cho bài học\s*)?:?\s*(.*?)\s*)?"
    r"(?=^\d+\.\s|\Z)",
    re.DOTALL | re.MULTILINE
)

# Tinh huong items 13 and 15 have no "Dap an:"/"Tra loi:" marker at all - the answer just
# continues straight from the question text. Confirmed by direct inspection (not a regex bug -
# the source genuinely lacks any marker there). Split point given as the literal substring the
# question ends on, matched by exact position like chunking.py's KNOWN_* fixes.
TINH_HUONG_SPLIT_ANCHORS: dict[int, str] = {
    13: "Hãy xác định thẩm quyền quyết định chuyển vụ án nói trên thuộc về ai và Tòa án cấp nào\nnếu:",
    15: "Hãy nêu cách giải quyết của HĐXX phúc thẩm trong trường hợp này.",
}


def _extract_pdf_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _split_sections(full_text: str) -> dict[str, str]:
    markers = ["Bán trắc nghiệm", "Câu hỏi lý thuyết", "Câu hỏi vận dụng", "Bài tập tình huống"]
    positions = {m: full_text.index(m) for m in markers}
    ordered = sorted(positions.items(), key=lambda kv: kv[1])
    sections = {}
    for i, (name, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(full_text)
        sections[name] = full_text[start:end]
    return sections


def _normalize_bullets_or_extract(
    question_text: str, answer_text: str, raw_bullets: list[str]
) -> list[str]:
    """Normalizes existing bullets if present (grounded 1:1 rewrite), otherwise falls back to
    LLM extraction from the answer text (grounded extraction, variable count) - the two source
    PDFs' documented preference is "normalize existing bullets, don't invent from scratch", but
    that only applies when bullets exist at all; ~65 of the 111 questions here have none."""
    if raw_bullets:
        user_prompt = build_normalize_key_points_prompt(question_text, answer_text, raw_bullets)
        try:
            response_text = generate_text(NORMALIZE_KEY_POINTS_SYSTEM_PROMPT, user_prompt)
        except Exception:
            logger.exception("LLM normalization failed for %r - falling back to raw bullets", question_text)
            return [_fallback_normalize_bullet(b) for b in raw_bullets]

        lines = [line.strip(" -\u2022●") for line in response_text.split("\n") if line.strip()]
        if len(lines) != len(raw_bullets):
            logger.warning("LLM returned %d lines for %d bullets (question=%r) - falling back",
                            len(lines), len(raw_bullets), question_text)
            return [_fallback_normalize_bullet(b) for b in raw_bullets]
        return lines

    user_prompt = build_extract_key_points_prompt(question_text, answer_text)
    try:
        response_text = generate_text(EXTRACT_KEY_POINTS_SYSTEM_PROMPT, user_prompt)
    except Exception:
        logger.exception("LLM extraction failed for %r - leaving essay_key_points empty", question_text)
        return []
    lines = [line.strip(" -\u2022●") for line in response_text.split("\n") if line.strip()]
    if not (2 <= len(lines) <= 5):
        logger.warning("LLM extraction returned %d key points (expected 2-5) for %r",
                        len(lines), question_text)
    return lines


def parse_ban_trac_nghiem(section_text: str, dieu_title_lookup: dict[str, str]) -> list[QuestionBankEntry]:
    entries: list[QuestionBankEntry] = []
    matches = list(BAN_TRAC_NGHIEM_PATTERN.finditer(section_text))
    if len(matches) != 50:
        logger.warning("Expected 50 Ban trac nghiem questions, parsed %d", len(matches))

    for i, match in enumerate(matches, start=1):
        statement, answer, legal_basis_raw, giai_thich_raw = match.groups()
        statement_norm = _normalize_whitespace(statement)
        giai_thich_norm = _normalize_whitespace(giai_thich_raw)
        legal_basis_norm = _normalize_whitespace(legal_basis_raw) if legal_basis_raw else None
        dieu_number = _extract_first_dieu_number(legal_basis_norm or giai_thich_norm)

        sample_answer = (
            f"{'Nhận định này đúng.' if answer == 'Đúng' else 'Nhận định này sai.'} {giai_thich_norm}"
        )
        key_points = _normalize_bullets_or_extract(statement_norm, giai_thich_norm, [])

        entries.append(QuestionBankEntry(
            question_id=f"bantracnghiem-q{i}",
            question_text=statement_norm,
            question_type="essay",
            essay_sample_answer=sample_answer,
            essay_key_points=key_points,
            dieu_number=dieu_number,
            topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
            quiz_set=None,
            explanation=f"Căn cứ pháp lý: {legal_basis_norm}" if legal_basis_norm else None,
        ))
        logger.info("bantracnghiem %d/50 done", i)

    return entries


def parse_ly_thuyet_or_van_dung(
    section_text: str, id_prefix: str, expected_count: int, dieu_title_lookup: dict[str, str]
) -> list[QuestionBankEntry]:
    entries: list[QuestionBankEntry] = []
    matches = list(LY_THUYET_VAN_DUNG_PATTERN.finditer(section_text))
    if len(matches) != expected_count:
        logger.warning("Expected %d %s questions, parsed %d", expected_count, id_prefix, len(matches))

    for i, match in enumerate(matches, start=1):
        question_text, sample_answer, legal_basis_raw, bullets_block = match.groups()
        question_text_norm = _normalize_whitespace(question_text)
        sample_answer_norm = _normalize_whitespace(sample_answer)
        legal_basis_norm = _normalize_whitespace(legal_basis_raw) if legal_basis_raw else None
        dieu_number = _extract_first_dieu_number(legal_basis_norm) if legal_basis_norm else None

        raw_bullets = [_normalize_whitespace(b) for b in BULLET_PATTERN.findall(bullets_block or "")]
        key_points = _normalize_bullets_or_extract(question_text_norm, sample_answer_norm, raw_bullets)

        entries.append(QuestionBankEntry(
            question_id=f"{id_prefix}-q{i}",
            question_text=question_text_norm,
            question_type="essay",
            essay_sample_answer=sample_answer_norm,
            essay_key_points=key_points,
            dieu_number=dieu_number,
            topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
            quiz_set=None,
            explanation=f"Cơ sở pháp lý: {legal_basis_norm}" if legal_basis_norm else None,
        ))
        logger.info("%s %d/%d done", id_prefix, i, expected_count)

    return entries


def parse_tinh_huong(section_text: str, dieu_title_lookup: dict[str, str]) -> list[QuestionBankEntry]:
    items = re.split(r"\n(?=\d+\.\s)", section_text)[1:]
    if len(items) != 15:
        logger.warning("Expected 15 Tinh huong items, split into %d", len(items))

    entries: list[QuestionBankEntry] = []
    for i, raw_item in enumerate(items, start=1):
        item = re.sub(r"^\d+\.\s*", "", raw_item, count=1)

        if i in TINH_HUONG_SPLIT_ANCHORS:
            anchor = TINH_HUONG_SPLIT_ANCHORS[i]
            idx = item.find(anchor)
            assert idx != -1, (
                f"Known Tinh huong manual-split anchor for item {i} no longer matches the "
                f"source text - source PDF may have been re-extracted differently; update "
                f"TINH_HUONG_SPLIT_ANCHORS."
            )
            split_at = idx + len(anchor)
            question_raw, answer_raw = item[:split_at], item[split_at:]
        else:
            m = re.search(r"^-?\s*(Đáp án|Trả lời)\s*:", item, re.MULTILINE)
            assert m is not None, f"Tinh huong item {i} has no 'Đáp án:'/'Trả lời:' marker and no manual split anchor"
            question_raw, answer_raw = item[:m.start()], item[m.end():]

        question_norm = _normalize_whitespace(question_raw)
        answer_norm = _normalize_whitespace(answer_raw)
        dieu_number = _extract_first_dieu_number(answer_norm)
        key_points = _normalize_bullets_or_extract(question_norm, answer_norm, [])

        entries.append(QuestionBankEntry(
            question_id=f"tinhhuong-q{i}",
            question_text=question_norm,
            question_type="essay",
            essay_sample_answer=answer_norm,
            essay_key_points=key_points,
            dieu_number=dieu_number,
            topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
            quiz_set=None,
            explanation=None,
        ))
        logger.info("tinhhuong %d/15 done", i)

    return entries


def reshuffle_mcq(mcq_pdf: Path, seed: int) -> list[QuestionBankEntry]:
    """Parses the 5x15 mcq_4choice layout, drops the old quiz_set assignment, and reshuffles
    into 15 sets of 5 with a fixed documented seed (requirements.md decision: 15 sets of 5 to
    match the Buoc 1 UI, mcq_true_false dropped entirely - not converted, not reused here)."""
    entries = parse_mcq_4choice(mcq_pdf, {})
    if len(entries) != 75:
        logger.warning("Expected 75 mcq_4choice questions, parsed %d", len(entries))

    rng = random.Random(seed)
    shuffled = entries[:]
    rng.shuffle(shuffled)

    reshuffled: list[QuestionBankEntry] = []
    for i, entry in enumerate(shuffled):
        new_set = (i // 5) + 1
        local_num = (i % 5) + 1
        entry.quiz_set = new_set
        entry.question_id = f"mcq4-set{new_set}-q{local_num}"
        reshuffled.append(entry)

    return reshuffled


def print_full_review_dump(
    ban_trac_nghiem: list[QuestionBankEntry], ly_thuyet: list[QuestionBankEntry],
    van_dung: list[QuestionBankEntry], tinh_huong: list[QuestionBankEntry],
    mcq_entries: list[QuestionBankEntry]
) -> None:
    def dump_essay(label: str, entries: list[QuestionBankEntry]) -> None:
        print("\n" + "=" * 100)
        print(f"{label} ({len(entries)} câu)")
        print("=" * 100)
        for e in entries:
            print(f"\n[{e.question_id}] (dieu={e.dieu_number}, topic={e.topic_category})")
            print(f"  Q: {e.question_text}")
            print(f"  Đáp án mẫu: {e.essay_sample_answer}")
            if e.explanation:
                print(f"  {e.explanation}")
            print("  essay_key_points:")
            for kp in e.essay_key_points or []:
                print(f"    - {kp}")

    dump_essay("BÁN TRẮC NGHIỆM", ban_trac_nghiem)
    dump_essay("LÝ THUYẾT", ly_thuyet)
    dump_essay("VẬN DỤNG", van_dung)
    dump_essay("TÌNH HUỐNG", tinh_huong)

    print("\n" + "=" * 100)
    print(f"MCQ 4-CHOICE - 15 bộ x 5 câu (seed={MCQ_RESHUFFLE_SEED})")
    print("=" * 100)
    by_set: dict[int, list[QuestionBankEntry]] = {}
    for e in mcq_entries:
        by_set.setdefault(e.quiz_set, []).append(e)
    for set_num in sorted(by_set):
        print(f"\n--- Bộ {set_num:02d} ---")
        for e in by_set[set_num]:
            print(f"[{e.question_id}] (dieu={e.dieu_number}, topic={e.topic_category})")
            print(f"  Q: {e.question_text}")
            for letter, opt in zip("ABCD", e.mcq_options or []):
                marker = " <-- ĐÚNG" if opt == e.mcq_correct else ""
                print(f"    {letter}. {opt}{marker}")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa2-file", type=Path, default=DEFAULT_QA2_PDF)
    parser.add_argument("--mcq-file", type=Path, default=DEFAULT_MCQ_PDF)
    parser.add_argument("--output", type=Path, default=QUESTION_BANK_OUTPUT_PATH)
    args = parser.parse_args()

    dieu_title_lookup = _load_bltths_dieu_title_lookup()

    logger.info("Parsing %s", args.qa2_file)
    full_text = _extract_pdf_text(args.qa2_file)
    sections = _split_sections(full_text)

    ban_trac_nghiem = parse_ban_trac_nghiem(sections["Bán trắc nghiệm"], dieu_title_lookup)
    ly_thuyet = parse_ly_thuyet_or_van_dung(
        sections["Câu hỏi lý thuyết"], "lythuyet", 20, dieu_title_lookup
    )
    van_dung = parse_ly_thuyet_or_van_dung(
        sections["Câu hỏi vận dụng"], "vandung", 26, dieu_title_lookup
    )
    tinh_huong = parse_tinh_huong(sections["Bài tập tình huống"], dieu_title_lookup)

    logger.info("Reshuffling MCQ from %s (seed=%d)", args.mcq_file, MCQ_RESHUFFLE_SEED)
    mcq_entries = reshuffle_mcq(args.mcq_file, MCQ_RESHUFFLE_SEED)

    all_entries = mcq_entries + ban_trac_nghiem + ly_thuyet + van_dung + tinh_huong

    output_payload = []
    category_by_prefix = {
        "bantracnghiem": "ban_trac_nghiem",
        "lythuyet": "ly_thuyet",
        "vandung": "van_dung",
        "tinhhuong": "tinh_huong",
    }
    for e in all_entries:
        d = e.to_dict()
        prefix = e.question_id.split("-q")[0]
        d["category"] = category_by_prefix.get(prefix)
        output_payload.append(d)

    args.output.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print_full_review_dump(ban_trac_nghiem, ly_thuyet, van_dung, tinh_huong, mcq_entries)

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"mcq_4choice: {len(mcq_entries)} (15 sets x 5, seed={MCQ_RESHUFFLE_SEED})")
    print(f"ban_trac_nghiem (essay): {len(ban_trac_nghiem)}")
    print(f"ly_thuyet (essay): {len(ly_thuyet)}")
    print(f"van_dung (essay): {len(van_dung)}")
    print(f"tinh_huong (essay): {len(tinh_huong)}")
    print(f"Total essay: {len(ban_trac_nghiem) + len(ly_thuyet) + len(van_dung) + len(tinh_huong)}")
    print(f"Total: {len(all_entries)}")
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
