"""Static procedure notes for the Người xem role (design doc Mục 11.1, decision 2026-10-29 item 4).

One short note per hearing step: what the step does, who speaks, and the BLTTHS articles it rests
on. Plain data, 0 LLM calls, the same text for every session.

DRAFT written by the developer from the BLTTHS 2015 text in the corpus (amended 2021 and by Luật
99/2025/QH15). NOT yet reviewed by the legal team: PROCEDURE_NOTES_REVIEWED stays False, and the API
sends that flag with every note, until the team has read and corrected all 11 notes.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.trial_state_machine import STEP_BY_NUMBER, STEPS

PROCEDURE_NOTES_REVIEWED = False
MAX_NOTE_WORDS = 80


@dataclass(frozen=True)
class ProcedureNote:
    step: int
    text: str
    legal_basis: tuple[str, ...]  # BLTTHS Điều numbers


PROCEDURE_NOTES: dict[int, ProcedureNote] = {n.step: n for n in (
    ProcedureNote(1, (
        "Trước khi khai mạc, Thư ký Tòa án kiểm tra sự có mặt của những người được triệu tập, nêu lý do người "
        "vắng mặt và phổ biến nội quy phiên tòa. Việc vắng mặt của Kiểm sát viên, bị cáo, người bào chữa, bị hại "
        "hay người làm chứng có thể dẫn tới hoãn phiên tòa hoặc xét xử vắng mặt, tùy từng trường hợp luật định."
    ), ("300", "289", "290", "291", "292", "293", "297")),
    ProcedureNote(2, (
        "Chủ tọa khai mạc phiên tòa, đọc quyết định đưa vụ án ra xét xử, kiểm tra lý lịch bị cáo và sự có mặt của "
        "những người được triệu tập, phổ biến quyền và nghĩa vụ của họ. Chủ tọa hỏi có ai đề nghị thay đổi người "
        "tiến hành tố tụng không. Người làm chứng cam đoan khai báo đúng sự thật và được cách ly trước khi được hỏi."
    ), ("301", "302", "304", "305")),
    ProcedureNote(3, (
        "Trước khi xét hỏi, Kiểm sát viên công bố bản cáo trạng và có thể trình bày ý kiến bổ sung. Ý kiến bổ sung "
        "không được làm xấu đi tình trạng của bị cáo. Cáo trạng xác định phạm vi xét xử: Tòa án chỉ xét xử những bị "
        "cáo và hành vi theo tội danh mà Viện kiểm sát truy tố."
    ), ("306", "298")),
    ProcedureNote(4, (
        "Hội đồng xét xử phải làm rõ đầy đủ từng sự việc và từng người. Chủ tọa điều hành việc hỏi và hỏi trước, sau "
        "đó Hội thẩm hỏi. Bị cáo được hỏi về hành vi của mình; bị hại và người làm chứng được hỏi về những gì họ biết. "
        "Lời khai ở giai đoạn điều tra có thể được công bố khi lời khai tại phiên tòa mâu thuẫn hoặc người khai vắng mặt."
    ), ("307", "308", "309", "310", "311")),
    ProcedureNote(5, (
        "Sau Hội đồng xét xử, Kiểm sát viên rồi người bào chữa lần lượt hỏi theo sự điều hành của Chủ tọa. Kiểm sát "
        "viên thường làm rõ yếu tố cấu thành tội phạm và chứng cứ buộc tội; luật sư làm rõ tình tiết có lợi cho bị "
        "cáo. Khi các tình tiết đã được xem xét đầy đủ và không ai yêu cầu hỏi thêm, Chủ tọa tuyên bố kết thúc xét hỏi."
    ), ("307", "317", "318")),
    ProcedureNote(6, (
        "Kết thúc xét hỏi, phiên tòa chuyển sang tranh luận. Kiểm sát viên trình bày luận tội: phân tích chứng cứ, "
        "đề nghị kết tội bị cáo theo toàn bộ hay một phần nội dung cáo trạng hoặc về tội nhẹ hơn, đề nghị mức hình "
        "phạt, trách nhiệm dân sự và xử lý vật chứng. Nếu không còn căn cứ kết tội, Kiểm sát viên rút quyết định truy tố."
    ), ("320", "321", "319")),
    ProcedureNote(7, (
        "Sau luận tội, bị cáo và người bào chữa trình bày lời bào chữa; bị cáo có quyền bổ sung ý kiến. Luật sư phản "
        "bác những điểm buộc tội chưa vững, nêu tình tiết giảm nhẹ và đề nghị mức xử lý có lợi cho bị cáo. Bị hại hoặc "
        "người đại diện của họ trình bày ý kiến để bảo vệ quyền và lợi ích của mình."
    ), ("320",)),
    ProcedureNote(8, (
        "Kiểm sát viên phải đưa ra lập luận đối với từng ý kiến của người bào chữa và người tham gia tố tụng; người "
        "tham gia tranh luận có quyền đáp lại. Chủ tọa không được hạn chế thời gian tranh luận. Nếu qua tranh luận "
        "thấy cần xem xét thêm chứng cứ, Hội đồng xét xử quyết định trở lại việc xét hỏi."
    ), ("322", "323")),
    ProcedureNote(9, (
        "Khi không ai tranh luận thêm, Chủ tọa tuyên bố kết thúc tranh luận và bị cáo được nói lời sau cùng. Không "
        "ai được đặt câu hỏi cho bị cáo lúc này. Nếu bị cáo trình bày thêm tình tiết mới có ý nghĩa quan trọng, Hội "
        "đồng xét xử phải quyết định trở lại việc xét hỏi."
    ), ("324",)),
    ProcedureNote(10, (
        "Chỉ Thẩm phán và Hội thẩm được nghị án, tại phòng nghị án. Họ biểu quyết theo đa số về từng vấn đề, Hội thẩm "
        "biểu quyết trước, Thẩm phán biểu quyết sau cùng. Việc nghị án chỉ căn cứ vào chứng cứ, tài liệu đã được thẩm "
        "tra tại phiên tòa. Kết thúc nghị án, Hội đồng xét xử ra bản án hoặc quyết định trở lại xét hỏi, trả hồ "
        "sơ, tạm đình chỉ vụ án."
    ), ("326",)),
    ProcedureNote(11, (
        "Chủ tọa hoặc một thành viên Hội đồng xét xử đọc bản án, gồm phần nhận định và phần quyết định về tội danh, "
        "hình phạt, trách nhiệm dân sự, vật chứng và án phí, rồi có thể giải thích về việc chấp hành bản án. Bị cáo, "
        "bị hại và đương sự có quyền kháng cáo trong 15 ngày kể từ ngày tuyên án."
    ), ("327", "331", "333")),
)}

assert set(PROCEDURE_NOTES) == {s.number for s in STEPS}


def procedure_note(step: int) -> dict:
    """The note of `step` as the API returns it (TrialStateOut.procedure_note)."""
    note = PROCEDURE_NOTES[step]
    return {"step": step, "title": STEP_BY_NUMBER[step].title, "text": note.text,
            "legal_basis": list(note.legal_basis), "reviewed": PROCEDURE_NOTES_REVIEWED}
