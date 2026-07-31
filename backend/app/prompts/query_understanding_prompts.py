"""Prompt for the query-understanding pre-processing step (Phase 4 Extension, see
requirements.md). Kept as a named constant/template function per requirements.md mục 6, same as
rag_prompts.py.
"""
from __future__ import annotations

QUERY_UNDERSTANDING_SYSTEM_PROMPT = """Bạn là bước tiền xử lý câu hỏi cho một trợ lý học tập về Luật Tố tụng Hình sự Việt Nam.

NHIỆM VỤ: Viết lại câu hỏi của sinh viên thành một câu hỏi ĐỘC LẬP, ĐẦY ĐỦ NGỮ CẢNH, giữ NGUYÊN \
VẸN ý định gốc của sinh viên. Câu viết lại này sẽ được dùng để tìm kiếm văn bản luật liên quan, \
không phải để trả lời câu hỏi.

QUY TẮC BẮT BUỘC:
1. Nếu câu hỏi dùng viết tắt luật phổ biến, mở rộng viết tắt đó dựa theo ĐÚNG bảng viết tắt được \
cung cấp bên dưới. Không mở rộng bất kỳ viết tắt nào không có trong bảng.
2. Nếu có LỊCH SỬ HỘI THOẠI được cung cấp và câu hỏi hiện tại dùng đại từ, cụm từ ngầm hiểu, hoặc \
là câu hỏi nối tiếp thiếu chủ ngữ/đối tượng (ví dụ "còn ... thì sao", "nó", "điều đó", "trường \
hợp đó"), hãy thay thế phần ngầm hiểu đó bằng đúng nội dung cụ thể đã được nhắc tới TRONG LỊCH SỬ \
HỘI THOẠI.
3. TUYỆT ĐỐI KHÔNG được tự suy đoán, bổ sung, hoặc bịa thêm bất kỳ nội dung pháp lý nào (số Điều, \
quy định, khái niệm...) không có sẵn trong câu hỏi gốc, lịch sử hội thoại, hoặc bảng viết tắt. \
Nếu không đủ căn cứ để giải quyết một đại từ/ngữ cảnh ngầm hiểu, GIỮ NGUYÊN phần đó trong câu hỏi \
thay vì đoán.
4. Nếu câu hỏi đã đầy đủ, rõ ràng, độc lập, không cần viết lại gì thêm ngoài quy tắc 1, trả về \
nguyên văn câu hỏi gốc.
5. CHỈ trả về đúng một câu hỏi đã viết lại. Không thêm giải thích, không thêm tiền tố kiểu "Câu \
hỏi viết lại:", không thêm dấu nháy bao quanh."""

# Small, fixed table so expansion is grounded in a known list rather than the model's own
# general knowledge of legal abbreviations (which could drift/hallucinate an expansion) -
# mirrors the "khong tu suy doan" constraint in the system prompt above.
LEGAL_ABBREVIATIONS: dict[str, str] = {
    "CQĐT": "Cơ quan điều tra",
    "ĐTV": "Điều tra viên",
    "KSV": "Kiểm sát viên",
    "VKS": "Viện kiểm sát",
    "VKSND": "Viện kiểm sát nhân dân",
    "TA": "Tòa án",
    "TAND": "Tòa án nhân dân",
    "HĐXX": "Hội đồng xét xử",
    "BLTTHS": "Bộ luật Tố tụng Hình sự",
    "BLHS": "Bộ luật Hình sự",
}


def _format_abbreviation_table() -> str:
    return "\n".join(f"- {short}: {full}" for short, full in LEGAL_ABBREVIATIONS.items())


def _format_recent_turns(recent_turns: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"Sinh viên hỏi: {turn['question']}\nTrợ lý đã trả lời: {turn['answer']}" for turn in recent_turns
    )


def build_query_understanding_prompt(question: str, recent_turns: list[dict[str, str]]) -> str:
    parts = [f"BẢNG VIẾT TẮT LUẬT CHUẨN:\n{_format_abbreviation_table()}"]

    if recent_turns:
        parts.append(f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY (cũ nhất trước):\n{_format_recent_turns(recent_turns)}")

    parts.append(f"Câu hỏi hiện tại của sinh viên: {question}")
    return "\n\n---\n\n".join(parts)
