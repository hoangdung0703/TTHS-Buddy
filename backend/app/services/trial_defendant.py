"""Static content of the Bị cáo role (chặng R3, design doc Mục 11.2 and decisions 9-14 of 11.8).

The student playing Bị cáo answers inside AI slots (đoạn xen, trial_state_machine.is_interleaved).
Everything here is code, 0 LLM calls:
- the fixed sentence recorded when the student declines a question ("Từ chối trả lời"), and the
  explanation of that right shown next to the button;
- the sentences recorded when the student skips an optional turn (steps 7 and 8);
- the questions code puts to the student when the AI ended a slot without asking the minimum;
- the step-2 identity answer prefilled from the case file;
- the role card ("Vai của bạn", decision 9): the defendant's OWN stance, knowledge and demeanour,
  returned only in a Bị cáo session and never anyone else's card.

Legal references were checked against the corpus (ingestion/chunks.json, BLTTHS 2015 as amended in
2021): điểm h khoản 2 Điều 61 ("không buộc phải đưa ra lời khai chống lại chính mình hoặc buộc phải
nhận mình có tội"), điểm b khoản 2 Điều 308 (statements made during the investigation may be read out
when the person questioned "không khai tại phiên tòa"). The legal team has not reviewed the wording
yet (Mục 11.2.8), so `reviewed` is false.
"""
from __future__ import annotations

from typing import Any

from app.models.trial import CaseFile
from app.services.trial_anonymise import anonymise_text
from app.services.trial_names import render

DEFENDANT_ID = "BI_CAO"
DEFENDANT_TEXT_REVIEWED = False

# Mục 11.2.1: recorded verbatim (kind "procedural", in the biên bản) when the student declines.
DECLINE_TEXT = "Bị cáo không trả lời câu hỏi này."
DECLINE_NOTE = {
    "text": ("Bị cáo có quyền trình bày lời khai, trình bày ý kiến, không buộc phải đưa ra lời khai chống lại chính "
             "mình hoặc buộc phải nhận mình có tội. Việc từ chối trả lời được ghi vào biên bản phiên tòa. Khi bị cáo "
             "không khai tại phiên tòa, lời khai của bị cáo trong giai đoạn điều tra, truy tố có thể được công bố."),
    "legal_basis": ["điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự",
                    "điểm b khoản 2 Điều 308 Bộ luật Tố tụng hình sự"],
    "reviewed": DEFENDANT_TEXT_REVIEWED,
}

# Optional turns (Mục 11.2.1, steps 7-8): Chủ tọa's invitation (a template slot) and the sentence
# recorded when the student answers "Không bổ sung" / "Không có ý kiến" (end_slot).
INVITATIONS = {
    "moi_bi_cao_bo_sung": "Bị cáo {BI_CAO} có bổ sung ý kiến bào chữa cho mình không?",
    "moi_bi_cao_tranh_luan": "Bị cáo {BI_CAO} có ý kiến tranh luận, đối đáp gì với Kiểm sát viên không?",
}
OPT_OUT_TEXTS = {
    "bi_cao_bo_sung_bao_chua": "Bị cáo không bổ sung ý kiến bào chữa.",
    "bi_cao_tranh_luan": "Bị cáo không có ý kiến tranh luận.",
}

# Asked by Chủ tọa when the AI closed a đoạn xen before putting `min_questions` questions to the
# student; indexed by how many the student has answered in the slot (the last entry repeats).
FALLBACK_QUESTIONS: dict[str, tuple[str, ...]] = {
    "khai_mac": (
        "Đề nghị bị cáo cho biết họ tên, tuổi, nơi cư trú, nghề nghiệp, trình độ học vấn, tiền án, tiền sự và "
        "ngày nhận bản cáo trạng.",
        "Bị cáo có đề nghị thay đổi Thẩm phán, Hội thẩm, Kiểm sát viên hay Thư ký phiên tòa không?",
    ),
    "hdxx_hoi_bi_cao": ("Đề nghị bị cáo trình bày ý kiến về bản cáo trạng và diễn biến sự việc.",),
    "loi_sau_cung": ("Bị cáo được nói lời sau cùng trước khi Hội đồng xét xử vào phòng nghị án.",),
}

ROLE_BRIEF_NOTE = "Đây là gợi ý nhập vai. Bạn có thể khai khác; Hội đồng xét xử sẽ đối chiếu với hồ sơ."
# The step-2 identity question is the first question of khai mạc.
IDENTITY_SLOT = "khai_mac"


def fallback_question(slot_key: str, answered: int) -> str:
    questions = FALLBACK_QUESTIONS[slot_key]
    return questions[min(answered, len(questions) - 1)]


def identity_prefill(case: CaseFile) -> str:
    """The answer to the identity question, from the case file (Mục 11.2.1: prefilled, editable).
    Only what the file holds; the date the indictment was received is not in it, so it is left out."""
    d = case.draft.defendant
    name = case.participants[DEFENDANT_ID].name
    text = (f"Thưa Hội đồng xét xử, tôi tên là {name}, {d.age} tuổi; nơi cư trú: {d.residence_place}; nghề "
            f"nghiệp: {d.occupation}; trình độ học vấn: {d.education}; tiền án, tiền sự: {d.prior_record}.")
    return render(text, case.participants)


def role_brief(case: CaseFile) -> dict[str, Any]:
    """The defendant's own character card, rendered and with other lay people's names abbreviated as
    in the case-file panel. Never the plea code, never another person's card, never the verdict."""
    d = case.draft.defendant

    def show(text: str) -> str:
        return anonymise_text(render(text, case.participants), case.participants)

    return {"stance": show(d.stance), "knowledge": [show(k) for k in d.knowledge], "demeanor": show(d.demeanor),
            "note": ROLE_BRIEF_NOTE}
