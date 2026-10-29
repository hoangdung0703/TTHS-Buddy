"""Static procedure notes for the Người xem role (design doc Mục 11.1, decision 2026-10-29 item 4).

One short note per hearing step: what the step does, who speaks, and the BLTTHS articles it rests
on. Plain data, 0 LLM calls, the same text for every session.

Written by the developer from the BLTTHS 2015 text in the corpus (amended 2021 and by Luật
99/2025/QH15). Each claim was checked by the developer against the corpus article text on 2026-10-29
and the notes corrected accordingly, see docs/phien-toa-gia-dinh/procedure-notes-verification.md; the
project owner approved the result, so PROCEDURE_NOTES_REVIEWED is True and the draft label is gone.
NOT appraised by the legal team, and not checked against the original text of Luật 99/2025/QH15
(only the amendment footnotes in the corpus).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.trial_state_machine import STEP_BY_NUMBER, STEPS

PROCEDURE_NOTES_REVIEWED = True
MAX_NOTE_WORDS = 80


@dataclass(frozen=True)
class ProcedureNote:
    step: int
    text: str
    legal_basis: tuple[str, ...]  # BLTTHS Điều numbers


PROCEDURE_NOTES: dict[int, ProcedureNote] = {n.step: n for n in (
    ProcedureNote(1, (
        "Trước khi khai mạc, Thư ký kiểm tra sự có mặt của người được triệu tập, nêu lý do người vắng mặt và phổ biến "
        "nội quy. Kiểm sát viên vắng mặt mà không có người dự khuyết thì phải hoãn phiên tòa; bị cáo vắng mặt có thể "
        "bị áp giải, hoãn hoặc xét xử vắng mặt khi luật cho phép; người bào chữa, bị hại, người làm chứng vắng mặt "
        "thì tùy trường hợp hoãn hoặc vẫn xử."
    ), ("300", "289", "290", "291", "292", "293", "297")),
    ProcedureNote(2, (
        "Chủ tọa khai mạc, đọc quyết định đưa vụ án ra xét xử. Thư ký báo cáo sự có mặt; Chủ tọa kiểm tra lại, kiểm "
        "tra lý lịch, phổ biến quyền và nghĩa vụ của người được triệu tập, rồi hỏi có ai đề nghị thay đổi Thẩm phán, "
        "Hội thẩm, Kiểm sát viên, Thư ký, người giám định, phiên dịch không. Người làm chứng cam đoan khai trung thực "
        "và được cách ly trước khi được hỏi."
    ), ("301", "302", "303", "304", "305")),
    ProcedureNote(3, (
        "Trước khi xét hỏi, Kiểm sát viên công bố bản cáo trạng và có thể trình bày ý kiến bổ sung, nhưng không được "
        "làm xấu đi tình trạng của bị cáo. Tòa án xét xử những bị cáo và hành vi theo tội danh bị truy tố; có thể xử "
        "theo khoản khác hoặc về tội bằng hay nhẹ hơn, còn muốn xử tội nặng hơn thì phải trả hồ sơ để Viện kiểm sát "
        "truy tố lại."
    ), ("306", "298")),
    ProcedureNote(4, (
        "Hội đồng xét xử phải xác định đầy đủ tình tiết về từng sự việc, từng tội và từng người. Chủ tọa hỏi trước, "
        "rồi để Thẩm phán, Hội thẩm, người khác hỏi. Bị cáo trình bày về cáo trạng rồi được hỏi thêm; bị hại, người "
        "làm chứng trình bày điều họ biết. Lời khai giai đoạn điều tra, truy tố chỉ được công bố khi luật cho phép, "
        "như lời khai mâu thuẫn hoặc người khai vắng mặt."
    ), ("307", "308", "309", "310", "311")),
    ProcedureNote(5, (
        "Theo sự điều hành của Chủ tọa, sau Hội đồng xét xử, Kiểm sát viên hỏi về chứng cứ liên quan đến việc buộc "
        "tội, gỡ tội; người bào chữa hỏi về chứng cứ liên quan đến việc bào chữa. Bị cáo được hỏi người khác khi Chủ "
        "tọa đồng ý. Khi tình tiết đã được xem xét đầy đủ, Chủ tọa hỏi còn ai yêu cầu xét hỏi không; nếu không thì "
        "kết thúc xét hỏi."
    ), ("307", "309", "310", "311", "318")),
    ProcedureNote(6, (
        "Mở đầu tranh luận, Kiểm sát viên luận tội: phân tích chứng cứ có tội, vô tội, đề nghị kết tội theo toàn bộ "
        "hay một phần cáo trạng hoặc về tội nhẹ hơn, đề nghị hình phạt, bồi thường và xử lý vật chứng. Nếu không có "
        "căn cứ kết tội, Kiểm sát viên rút toàn bộ quyết định truy tố, đề nghị tuyên bị cáo không có tội; Hội đồng "
        "xét xử vẫn nghị án."
    ), ("320", "321", "319", "325")),
    ProcedureNote(7, (
        "Sau luận tội, bị cáo và người bào chữa trình bày lời bào chữa; bị cáo, người đại diện của bị cáo có quyền bổ "
        "sung. Người bào chữa đưa ra chứng cứ, lập luận để đối đáp với Kiểm sát viên về chứng cứ, tình tiết giảm nhẹ, "
        "mức hình phạt và đưa ra đề nghị. Bị hại, đương sự hoặc người đại diện của họ trình bày ý kiến để bảo vệ "
        "quyền lợi của mình."
    ), ("320", "322")),
    ProcedureNote(8, (
        "Kiểm sát viên phải đưa ra chứng cứ, lập luận đối đáp đến cùng từng ý kiến của bị cáo, người bào chữa, người "
        "tham gia tố tụng khác; người tranh luận có quyền đáp lại. Chủ tọa không được hạn chế thời gian tranh luận "
        "nhưng được cắt ý kiến không liên quan hoặc lặp lại. Nếu còn tình tiết chưa được làm sáng tỏ, Hội đồng xét xử "
        "phải trở lại xét hỏi rồi tiếp tục tranh luận."
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
        "Chủ tọa hoặc thành viên khác của Hội đồng xét xử đọc bản án (xử kín thì chỉ đọc phần quyết định), rồi có thể "
        "giải thích chấp hành án và quyền kháng cáo. Bị cáo, bị hại, người đại diện của họ có quyền kháng cáo; đương "
        "sự kháng cáo phần liên quan đến mình. Thời hạn 15 ngày kể từ ngày tuyên án; bị cáo, đương sự vắng mặt tính "
        "từ ngày nhận hoặc niêm yết bản án."
    ), ("327", "331", "333")),
)}

assert set(PROCEDURE_NOTES) == {s.number for s in STEPS}


def procedure_note(step: int) -> dict:
    """The note of `step` as the API returns it (TrialStateOut.procedure_note)."""
    note = PROCEDURE_NOTES[step]
    return {"step": step, "title": STEP_BY_NUMBER[step].title, "text": note.text,
            "legal_basis": list(note.legal_basis), "reviewed": PROCEDURE_NOTES_REVIEWED}
