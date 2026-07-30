"""One-off script: appends essay-q26..q30 (added to "Tôi hỏi bạn trả lời (1).pdf" after the
original 25) to ingestion/question_bank.json. Kept in the repo for historical reference, same as
ingestion/fix_dieu_title_page_bleed.py - not meant to be re-run once question_bank.json already
has these 5 entries (re-running would raise on the question_id collision assert below).
"""
import sys
import re
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion.parse_question_bank import (
    _extract_pdf_text,
    _normalize_whitespace,
    _extract_first_dieu_number,
    _load_bltths_dieu_title_lookup,
    _normalize_key_points_with_llm,
    BULLET_PATTERN,
    RAW_DOCUMENTS_DIR,
    QuestionBankEntry,
)
from ingestion.config import QUESTION_BANK_OUTPUT_PATH

# The updated source PDF dropped the old "Tự luận:" per-question marker for the whole essay
# section (all 30, not just the new ones) in favor of a numbered list under a "TỰ LUẬN" header,
# and is inconsistent about "Cơ sở pháp lý:" vs "Căn cứ pháp lý:" / "Từ khóa cho bài học:" vs
# "Từ khoá:" for the last item - this pattern tolerates both. Verified separately that all 25
# pre-existing questions still parse identically to what's already in question_bank.json before
# trusting this pattern for the 5 new ones.
NEW_ESSAY_PATTERN = re.compile(
    r"^(\d+)\.\s*(.*?)\s*"
    r"⇒\s*Đáp án\s*:\s*(.*?)\s*"
    r"⇒\s*(?:Cơ sở pháp lý|Căn cứ pháp lý)\s*:\s*(.*?)\s*"
    r"⇒\s*Từ kh\S{1,3}(?:\s*cho bài học)?\s*:\s*(.*?)"
    r"(?=^\d+\.\s|\Z)",
    re.DOTALL | re.MULTILINE
)

new_pdf = RAW_DOCUMENTS_DIR / "Tôi hỏi bạn trả lời (1).pdf"
text = _extract_pdf_text(new_pdf)
essay_section = text[text.find("TỰ LUẬN"):]
matches = list(NEW_ESSAY_PATTERN.finditer(essay_section))
assert len(matches) == 30, f"Expected 30 essay matches in updated PDF, got {len(matches)}"

dieu_title_lookup = _load_bltths_dieu_title_lookup()

new_entries: list[QuestionBankEntry] = []
for m in matches[25:]:  # only the 5 new ones (local numbers 26-30)
    local_num, question_text, sample_answer, legal_basis, bullets_block = m.groups()
    question_text_norm = _normalize_whitespace(question_text)
    sample_answer_norm = _normalize_whitespace(sample_answer)
    legal_basis_norm = _normalize_whitespace(legal_basis)
    dieu_number = _extract_first_dieu_number(legal_basis_norm)

    raw_bullets = [_normalize_whitespace(b) for b in BULLET_PATTERN.findall(bullets_block)]
    key_points = _normalize_key_points_with_llm(question_text_norm, sample_answer_norm, raw_bullets)

    new_entries.append(QuestionBankEntry(
        question_id=f"essay-q{local_num}",
        question_text=question_text_norm,
        question_type="essay",
        essay_sample_answer=sample_answer_norm,
        essay_key_points=key_points,
        dieu_number=dieu_number,
        topic_category=dieu_title_lookup.get(dieu_number) if dieu_number else None,
        quiz_set=None,
        explanation=f"Cơ sở pháp lý: {legal_basis_norm}",
    ))

print("\n" + "=" * 100)
print(f"5 CÂU TỰ LUẬN MỚI (essay-q26 .. essay-q30)")
print("=" * 100)
for e in new_entries:
    print(f"\n[{e.question_id}] (dieu={e.dieu_number}, topic={e.topic_category})")
    print(f"  Q: {e.question_text}")
    print(f"  Đáp án mẫu: {e.essay_sample_answer}")
    print(f"  {e.explanation}")
    print("  essay_key_points:")
    for kp in e.essay_key_points or []:
        print(f"    - {kp}")

existing = json.loads(QUESTION_BANK_OUTPUT_PATH.read_text(encoding="utf-8"))
existing_ids = {q["question_id"] for q in existing}
for e in new_entries:
    assert e.question_id not in existing_ids, f"question_id collision: {e.question_id}"

merged = existing + [e.to_dict() for e in new_entries]
QUESTION_BANK_OUTPUT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
print(f"Trước: {len(existing)} câu")
print(f"Thêm mới: {len(new_entries)} câu")
print(f"Tổng sau merge: {len(merged)} câu")
print(f"Output written to: {QUESTION_BANK_OUTPUT_PATH}")
