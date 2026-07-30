"""Parses the law students' question-bank source PDFs into a single unified JSON, per
requirements.md Phase 5a:
  - "Câu hỏi trắc nghiệm.pdf": 5 quiz sets of MCQ 4-choice questions ("Đề số N" markers).
  - "Tôi hỏi bạn trả lời.pdf": 15 True/False assertions (converted to 2-choice MCQ, distributed
    3 per quiz set) + 25 pure essay questions (with a sample answer and "Từ khóa cho bài học"
    bullets that get LLM-normalized into essay_key_points).

Usage:
    python -m ingestion.parse_question_bank
    python -m ingestion.parse_question_bank --mcq-file "..." --qa-file "..." --output ...
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber

from ingestion.config import CHUNKS_OUTPUT_PATH, QUESTION_BANK_OUTPUT_PATH, RAW_DOCUMENTS_DIR
from ingestion.logging_utils import configure_logging, get_logger
from ingestion.qb_llm_client import generate_text
from ingestion.qb_prompts import NORMALIZE_KEY_POINTS_SYSTEM_PROMPT, build_normalize_key_points_prompt

logger = get_logger(__name__)

DEFAULT_MCQ_PDF = RAW_DOCUMENTS_DIR / "Câu hỏi trắc nghiệm.pdf"
DEFAULT_QA_PDF = RAW_DOCUMENTS_DIR / "Tôi hỏi bạn trả lời.pdf"

# Tolerant of the real source typo "BỘ ĐÈ SỐ 02" (should be "ĐỀ") - not used for splitting
# (that's done via the consistently-spelled "Đề số N" marker instead) but kept for reference.
DIEU_NUMBER_PATTERN = re.compile(r"Điều\s+(\d+[a-zA-Z]?)")
QUIZ_SET_MARKER_PATTERN = re.compile(r"Đề số\s+(\d+)")

# All markers below are anchored to the start of a line (^ with MULTILINE) - a question body
# can itself contain a bare single-letter reference like "...chỗ ở của A. Trong trường hợp
# này:" (a hypothetical person named "A"), which a non-anchored r"A\." would misfire on as if
# it were the option-A marker. Every real marker in the source PDFs sits on its own line, so
# requiring a line start avoids that false match without needing to special-case letter names.
MCQ_QUESTION_PATTERN = re.compile(
    r"^Câu\s*(\d+)\.\s*(.*?)\s*"
    r"^A\.\s*(.*?)\s*"
    r"^B\.\s*(.*?)\s*"
    r"^C\.\s*(.*?)\s*"
    r"^D\.\s*(.*?)\s*"
    r"^Đáp án:\s*([A-D])\.?\s*"
    r"^Giải thích:\s*(.*?)"
    r"(?=^Câu\s*\d+\.|\Z)",
    re.DOTALL | re.MULTILINE
)

TRUE_FALSE_PATTERN = re.compile(
    r"^Nhận định:\s*(.*?)\s*"
    r"^Đáp án:\s*(Đúng|Sai)\.?\s*"
    r"^Căn cứ pháp lý:\s*(.*?)\s*"
    r"^Giải thích:\s*(.*?)"
    r"(?=^Nhận định:|^Tự luận:|\Z)",
    re.DOTALL | re.MULTILINE
)

# "kh\S{1,3}" tolerates the source file's inconsistent spelling of "khóa"/"khoá" - both valid
# Vietnamese, not an OCR error, but the diacritic lands on a different vowel letter ("kh" + "óa"
# vs "kh" + "oá"), so a literal "kho" prefix only matches one of the two variants.
ESSAY_PATTERN = re.compile(
    r"^Tự luận:\s*(.*?)\s*"
    r"^⇒\s*Đáp án:\s*(.*?)\s*"
    r"^⇒\s*Cơ sở pháp lý:\s*(.*?)\s*"
    r"^⇒\s*Từ kh\S{1,3}\s*cho bài học:\s*(.*?)"
    r"(?=^Tự luận:|\Z)",
    re.DOTALL | re.MULTILINE
)
BULLET_PATTERN = re.compile(r"●\s*(.*?)(?=●|\Z)", re.DOTALL)

QUOTE_CHARS = "“”\"'"


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().strip(QUOTE_CHARS).strip()


def _extract_pdf_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _extract_first_dieu_number(text: str) -> str | None:
    match = DIEU_NUMBER_PATTERN.search(text)
    return match.group(1) if match else None


def _load_bltths_dieu_title_lookup() -> dict[str, str]:
    """topic_category is derived from dieu_number by looking up the Dieu's title in the
    already-ingested Phase 3 legal_text chunks - simpler and less error-prone than trying to
    infer a chapter/topic name from scratch, and grounded in real data instead of a guess."""
    if not CHUNKS_OUTPUT_PATH.exists():
        logger.warning("chunks.json not found at %s - topic_category will be left null for all "
                        "questions with a dieu_number", CHUNKS_OUTPUT_PATH)
        return {}

    chunks = json.loads(CHUNKS_OUTPUT_PATH.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for chunk in chunks:
        if chunk["source_type"] != "legal_text" or "BLTTHS" not in (chunk["law_version"] or ""):
            continue
        dieu_number = chunk["dieu_number"]
        if dieu_number not in lookup:
            lookup[dieu_number] = chunk["dieu_title"]
    return lookup


@dataclass
class QuestionBankEntry:
    question_id: str
    question_text: str
    question_type: str
    mcq_options: list[str] | None = None
    mcq_correct: str | None = None
    essay_sample_answer: str | None = None
    essay_key_points: list[str] | None = None
    dieu_number: str | None = None
    topic_category: str | None = None
    quiz_set: int | None = None
    explanation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "mcq_options": self.mcq_options,
            "mcq_correct": self.mcq_correct,
            "essay_sample_answer": self.essay_sample_answer,
            "essay_key_points": self.essay_key_points,
            "dieu_number": self.dieu_number,
            "topic_category": self.topic_category,
            "quiz_set": self.quiz_set,
            "explanation": self.explanation,
        }


def parse_mcq_4choice(pdf_path: Path, dieu_title_lookup: dict[str, str]) -> list[QuestionBankEntry]:
    full_text = _extract_pdf_text(pdf_path)
    markers = list(QUIZ_SET_MARKER_PATTERN.finditer(full_text))
    if len(markers) != 5:
        logger.warning("Expected 5 'Đề số N' markers in %s, found %d", pdf_path.name, len(markers))

    entries: list[QuestionBankEntry] = []
    for i, marker in enumerate(markers):
        quiz_set = int(marker.group(1))
        segment_start = marker.end()
        segment_end = markers[i + 1].start() if i + 1 < len(markers) else len(full_text)
        segment = full_text[segment_start:segment_end]

        set_entries = []
        for match in MCQ_QUESTION_PATTERN.finditer(segment):
            local_num, question_text, opt_a, opt_b, opt_c, opt_d, correct_letter, explanation = match.groups()
            options = [_normalize_whitespace(o) for o in (opt_a, opt_b, opt_c, opt_d)]
            correct_text = options["ABCD".index(correct_letter)]
            explanation_norm = _normalize_whitespace(explanation)
            dieu_number = _extract_first_dieu_number(explanation_norm)

            set_entries.append(QuestionBankEntry(
                question_id=f"mcq4-set{quiz_set}-q{local_num}",
                question_text=_normalize_whitespace(question_text),
                question_type="mcq_4choice",
                mcq_options=options,
                mcq_correct=correct_text,
                dieu_number=dieu_number,
                topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
                quiz_set=quiz_set,
                explanation=explanation_norm,
            ))

        if len(set_entries) != 15:
            logger.warning("Quiz set %d: expected 15 MCQ questions, parsed %d", quiz_set, len(set_entries))
        entries.extend(set_entries)

    return entries


def parse_true_false(qa_text: str, dieu_title_lookup: dict[str, str]) -> list[QuestionBankEntry]:
    tu_luan_idx = qa_text.find("Tự luận:")
    nhan_dinh_section = qa_text[:tu_luan_idx] if tu_luan_idx != -1 else qa_text

    entries: list[QuestionBankEntry] = []
    for i, match in enumerate(TRUE_FALSE_PATTERN.finditer(nhan_dinh_section)):
        assertion_text, answer, legal_basis, explanation = match.groups()
        quiz_set = (i // 3) + 1
        local_num = (i % 3) + 1
        legal_basis_norm = _normalize_whitespace(legal_basis)
        dieu_number = _extract_first_dieu_number(legal_basis_norm)

        entries.append(QuestionBankEntry(
            question_id=f"tf-set{quiz_set}-q{local_num}",
            question_text=_normalize_whitespace(assertion_text),
            question_type="mcq_true_false",
            mcq_options=["Đúng", "Sai"],
            mcq_correct=answer,
            dieu_number=dieu_number,
            topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
            quiz_set=quiz_set,
            explanation=f"Căn cứ pháp lý: {legal_basis_norm.rstrip('.')}. {_normalize_whitespace(explanation)}",
        ))

    if len(entries) != 15:
        logger.warning("Expected 15 True/False assertions, parsed %d", len(entries))
    return entries


def _normalize_key_points_with_llm(question_text: str, sample_answer: str, raw_bullets: list[str]) -> list[str]:
    user_prompt = build_normalize_key_points_prompt(question_text, sample_answer, raw_bullets)
    try:
        response_text = generate_text(NORMALIZE_KEY_POINTS_SYSTEM_PROMPT, user_prompt)
    except Exception:
        logger.exception("LLM normalization failed for question %r - falling back to raw bullets", question_text)
        return [_fallback_normalize_bullet(b) for b in raw_bullets]

    lines = [line.strip(" -\u2022●") for line in response_text.split("\n") if line.strip()]
    if len(lines) != len(raw_bullets):
        logger.warning("LLM returned %d lines for %d bullets (question=%r) - falling back to raw bullets",
                        len(lines), len(raw_bullets), question_text)
        return [_fallback_normalize_bullet(b) for b in raw_bullets]

    return lines


def _fallback_normalize_bullet(bullet: str) -> str:
    text = bullet.strip()
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text[0].upper() + text[1:] if text else text


def parse_essays(qa_text: str, dieu_title_lookup: dict[str, str]) -> list[QuestionBankEntry]:
    tu_luan_idx = qa_text.find("Tự luận:")
    essay_section = qa_text[tu_luan_idx:] if tu_luan_idx != -1 else ""

    entries: list[QuestionBankEntry] = []
    for i, match in enumerate(ESSAY_PATTERN.finditer(essay_section)):
        question_text, sample_answer, legal_basis, bullets_block = match.groups()
        question_text_norm = _normalize_whitespace(question_text)
        sample_answer_norm = _normalize_whitespace(sample_answer)
        legal_basis_norm = _normalize_whitespace(legal_basis)
        dieu_number = _extract_first_dieu_number(legal_basis_norm)

        raw_bullets = [_normalize_whitespace(b) for b in BULLET_PATTERN.findall(bullets_block)]
        key_points = _normalize_key_points_with_llm(question_text_norm, sample_answer_norm, raw_bullets)

        entries.append(QuestionBankEntry(
            question_id=f"essay-q{i + 1}",
            question_text=question_text_norm,
            question_type="essay",
            essay_sample_answer=sample_answer_norm,
            essay_key_points=key_points,
            dieu_number=dieu_number,
            topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
            quiz_set=None,
            explanation=f"Cơ sở pháp lý: {legal_basis_norm}",
        ))

    if len(entries) != 25:
        logger.warning("Expected 25 essay questions, parsed %d", len(entries))
    return entries


def print_full_review_dump(mcq_entries: list[QuestionBankEntry], tf_entries: list[QuestionBankEntry],
                            essay_entries: list[QuestionBankEntry]) -> None:
    print("\n" + "=" * 100)
    print(f"MCQ 4-CHOICE ({len(mcq_entries)} câu)")
    print("=" * 100)
    for e in mcq_entries:
        print(f"\n[{e.question_id}] (quiz_set={e.quiz_set}, dieu={e.dieu_number}, topic={e.topic_category})")
        print(f"  Q: {e.question_text}")
        for letter, opt in zip("ABCD", e.mcq_options or []):
            marker = " <-- ĐÚNG" if opt == e.mcq_correct else ""
            print(f"    {letter}. {opt}{marker}")
        print(f"  Giải thích: {e.explanation}")

    print("\n" + "=" * 100)
    print(f"MCQ TRUE/FALSE ({len(tf_entries)} câu)")
    print("=" * 100)
    for e in tf_entries:
        print(f"\n[{e.question_id}] (quiz_set={e.quiz_set}, dieu={e.dieu_number}, topic={e.topic_category})")
        print(f"  Nhận định: {e.question_text}")
        print(f"  Đáp án: {e.mcq_correct}")
        print(f"  {e.explanation}")

    print("\n" + "=" * 100)
    print(f"ESSAY ({len(essay_entries)} câu)")
    print("=" * 100)
    for e in essay_entries:
        print(f"\n[{e.question_id}] (dieu={e.dieu_number}, topic={e.topic_category})")
        print(f"  Q: {e.question_text}")
        print(f"  Đáp án mẫu: {e.essay_sample_answer}")
        print(f"  {e.explanation}")
        print("  essay_key_points:")
        for kp in e.essay_key_points or []:
            print(f"    - {kp}")


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Parse the question bank source PDFs into question_bank.json")
    parser.add_argument("--mcq-file", type=Path, default=DEFAULT_MCQ_PDF)
    parser.add_argument("--qa-file", type=Path, default=DEFAULT_QA_PDF)
    parser.add_argument("--output", type=Path, default=QUESTION_BANK_OUTPUT_PATH)
    args = parser.parse_args()

    dieu_title_lookup = _load_bltths_dieu_title_lookup()

    logger.info("Parsing MCQ 4-choice from %s", args.mcq_file)
    mcq_entries = parse_mcq_4choice(args.mcq_file, dieu_title_lookup)

    logger.info("Parsing True/False + essay from %s", args.qa_file)
    qa_text = _extract_pdf_text(args.qa_file)
    tf_entries = parse_true_false(qa_text, dieu_title_lookup)
    essay_entries = parse_essays(qa_text, dieu_title_lookup)

    all_entries = mcq_entries + tf_entries + essay_entries
    args.output.write_text(
        json.dumps([e.to_dict() for e in all_entries], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print_full_review_dump(mcq_entries, tf_entries, essay_entries)

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"mcq_4choice: {len(mcq_entries)}")
    print(f"mcq_true_false: {len(tf_entries)}")
    print(f"essay: {len(essay_entries)}")
    print(f"Total: {len(all_entries)}")
    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
