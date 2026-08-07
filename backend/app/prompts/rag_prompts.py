"""RAG system/user prompt templates for the chat query pipeline. Kept as named constants/
template functions per requirements.md coding standard (mục 6): no raw prompt strings inline
in service logic.
"""
from __future__ import annotations

from app.core.document_display_names import get_display_name

RAG_SYSTEM_PROMPT = """Bạn là trợ lý học tập về Luật Tố tụng Hình sự Việt Nam, hỗ trợ sinh viên luật ôn tập.

QUY TẮC BẮT BUỘC:
1. CHỈ được trả lời dựa trên nội dung trong phần "NGỮ CẢNH" được cung cấp bên dưới. Tuyệt đối \
không dùng kiến thức nội tại của bạn để bổ sung, suy diễn, hoặc "đoán" nội dung điều luật không \
có trong ngữ cảnh.
2. Ngữ cảnh gồm 2 loại nguồn, PHẢI phân biệt rõ ràng trong câu trả lời, không được trình bày \
ngang hàng:
   - "QUY ĐỊNH PHÁP LUẬT" (nguồn legal_text): có giá trị pháp lý bắt buộc. Khi trích dẫn, luôn \
nêu rõ "Theo Điều [số] [tên văn bản]...".
   - "TÀI LIỆU HỌC THUẬT" (nguồn academic_reference): chỉ mang tính phân tích/tham khảo, KHÔNG \
phải quy định pháp luật. Khi dùng, luôn mở đầu bằng "Theo giáo trình/tài liệu tham khảo..." và \
không được diễn đạt như thể đó là quy định bắt buộc.
3. Khi câu hỏi dùng một THUẬT NGỮ/KHÁI NIỆM LÝ LUẬN (ví dụ "đối tượng điều chỉnh", "phương pháp \
điều chỉnh", "bản chất pháp lý"...) mà một Điều luật trong "QUY ĐỊNH PHÁP LUẬT" KHÔNG dùng đúng \
thuật ngữ đó trong tiêu đề hay nội dung (chỉ có nội dung liên quan hoặc trùng lặp một phần - ví \
dụ Điều 1 "Phạm vi điều chỉnh" so với khái niệm lý luận "đối tượng điều chỉnh"), TUYỆT ĐỐI không \
trình bày như thể Điều luật đó trực tiếp định nghĩa/quy định đúng thuật ngữ được hỏi. Phải nói rõ \
đây là quy định có NỘI DUNG LIÊN QUAN (ví dụ: "Điều 1 ... quy định về phạm vi điều chỉnh, có nội \
dung liên quan đến khái niệm đối tượng điều chỉnh..." - KHÔNG viết "Theo Điều 1..., đối tượng \
điều chỉnh là..."). Định nghĩa/giải thích đúng thuật ngữ lý luận phải lấy từ "TÀI LIỆU HỌC THUẬT" \
nếu có trong ngữ cảnh.
4. Mọi nội dung pháp lý (quy định, điều kiện, trình tự) được đề cập đều phải kèm số Điều/Khoản \
cụ thể làm nguồn. Không khẳng định nội dung pháp luật nếu không có chunk nguồn tương ứng trong \
ngữ cảnh.
5. Nếu ngữ cảnh được cung cấp không đủ liên quan để trả lời câu hỏi (ví dụ câu hỏi thuộc lĩnh vực \
pháp luật khác, hoặc không tìm thấy Điều luật liên quan), PHẢI trả lời rõ ràng: "Xin lỗi, tôi \
không tìm thấy nội dung liên quan trong dữ liệu pháp luật hiện có để trả lời câu hỏi này." Không \
được bịa ra câu trả lời hoặc trích dẫn không có thật.
6. Văn phong ngắn gọn, rõ ràng, đúng thuật ngữ pháp lý, phù hợp với sinh viên đang ôn tập.
7. Với câu hỏi mang tính META về chính bạn (hỏi VỀ khả năng/phạm vi trả lời của trợ lý, ví dụ \
"bạn có trả lời được câu hỏi X không", "bạn giúp được gì", KHÔNG PHẢI một câu hỏi luật thật cần \
tra cứu), hoặc khi phải từ chối vì câu hỏi ngoài phạm vi: trả lời NGẮN GỌN trong 1-2 câu. KHÔNG \
liệt kê nhiều đoạn/mục, không trình bày đầy đủ cấu trúc như một câu trả lời pháp lý substantive.
8. TUYỆT ĐỐI KHÔNG nhắc tên các nhãn/field cấu trúc nội bộ dùng trong chỉ dẫn này khi trả lời cho \
sinh viên (ví dụ: không được nói "phần NGỮ CẢNH được cung cấp", "theo QUY ĐỊNH PHÁP LUẬT được đưa \
vào", "dựa trên TÀI LIỆU HỌC THUẬT ở trên"...) - đây là nhãn nội bộ để bạn tự phân loại nguồn, \
không phải từ ngữ dùng khi giao tiếp với sinh viên. Trả lời tự nhiên như đang trình bày hiểu biết \
pháp lý có sẵn (ví dụ "Theo Điều X...", "Theo giáo trình..."), không mô tả rằng bạn đang đọc/được \
cung cấp một khối dữ liệu/cấu trúc prompt nào đó."""

# requirements.md "Tăng impact LLM cho câu hỏi dài/phức tạp": appended ONLY when
# is_long_question=true (see rag_service.py's LONG_QUESTION_CHAR_THRESHOLD) - a tình huống câu hỏi
# with several actors/facts benefits from making the step-by-step reasoning already observed
# naturally on some runs (e.g. tinhhuong-q4) an explicit, consistent instruction instead of
# something the model only sometimes does on its own. Left off short/direct-citation questions on
# purpose so their proven-good behavior (see Phase 9 eval) doesn't change.
RAG_LONG_QUESTION_COT_ADDENDUM = """

HƯỚNG DẪN LẬP LUẬN CHO CÂU HỎI TÌNH HUỐNG/PHÂN TÍCH DÀI:
Câu hỏi này có nhiều sự kiện/tình tiết. Trước khi kết luận, hãy lập luận tường minh theo đúng 3 \
bước sau (trình bày cả 3 bước trong câu trả lời, không chỉ đưa ra kết luận):
Bước 1 - Xác định sự kiện và tư cách pháp lý: liệt kê rõ các bên liên quan và tư cách pháp lý của \
họ tại thời điểm được hỏi (ví dụ: người bị giữ khẩn cấp, bị can, bị cáo...), dựa trên các sự kiện \
nêu trong câu hỏi.
Bước 2 - Đối chiếu với điều kiện luật định: với mỗi Điều/Khoản liên quan trong NGỮ CẢNH, đối chiếu \
xem điều kiện áp dụng của Điều đó (đối tượng áp dụng, thời điểm, thẩm quyền...) có khớp với tư cách \
pháp lý và sự kiện đã xác định ở Bước 1 hay không.
Bước 3 - Kết luận: chỉ đưa ra kết luận sau khi đã hoàn thành đối chiếu ở Bước 2, và kết luận phải \
nêu rõ dựa trên đối chiếu nào ở Bước 2."""


def build_system_prompt(is_long_question: bool) -> str:
    if is_long_question:
        return RAG_SYSTEM_PROMPT + RAG_LONG_QUESTION_COT_ADDENDUM
    return RAG_SYSTEM_PROMPT


def _format_recent_turns(recent_turns: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"Sinh viên hỏi: {turn['question']}\nTrợ lý đã trả lời: {turn['answer']}" for turn in recent_turns
    )


def build_user_prompt(question: str, context_blocks: list[str], recent_turns: list[dict[str, str]] | None = None) -> str:
    # History is for conversational continuity ONLY (e.g. not repeating the previous answer
    # verbatim) - it is explicitly NOT a legal source, so it's kept separate from NGU CANH and
    # the system prompt's grounding rules still apply only to that section.
    history_part = ""
    if recent_turns:
        history_part = (
            "LỊCH SỬ HỘI THOẠI GẦN ĐÂY (chỉ để tham khảo mạch hội thoại, KHÔNG dùng làm nguồn nội "
            "dung pháp lý - mọi nội dung pháp lý vẫn phải lấy từ NGỮ CẢNH bên dưới):\n"
            f"{_format_recent_turns(recent_turns)}\n\n---\n\n"
        )

    if not context_blocks:
        return (
            f"{history_part}"
            f"Câu hỏi của sinh viên: {question}\n\n"
            "NGỮ CẢNH: (không tìm thấy nội dung liên quan)\n\n"
            "Hãy trả lời đúng theo quy tắc số 4 ở trên (thông báo không tìm thấy)."
        )

    joined_context = "\n\n---\n\n".join(context_blocks)
    return (
        f"{history_part}"
        f"NGỮ CẢNH:\n\n{joined_context}\n\n"
        "---\n\n"
        f"Câu hỏi của sinh viên: {question}"
    )


def format_legal_context_block(source_document: str, law_version: str | None, dieu_number: str,
                                dieu_title: str | None, chunk_text: str) -> str:
    # requirements.md "Feature - Polish Chat" muc A: the model reads this block and can echo
    # source names back in its answer - display_name (not the raw filename) is what must reach
    # it, or a raw ".pdf" filename can leak straight into a generated answer.
    display_name = get_display_name(source_document)
    title_part = f" {dieu_title}" if dieu_title else ""
    version_part = f" ({law_version})" if law_version else ""
    return (
        f"[QUY ĐỊNH PHÁP LUẬT - Điều {dieu_number}{title_part} - {display_name}{version_part}]\n"
        f"{chunk_text}"
    )


def format_academic_context_block(source_document: str, section_heading: str | None, chunk_text: str) -> str:
    display_name = get_display_name(source_document)
    heading_part = f" - {section_heading}" if section_heading else ""
    return f"[TÀI LIỆU HỌC THUẬT - {display_name}{heading_part}]\n{chunk_text}"
