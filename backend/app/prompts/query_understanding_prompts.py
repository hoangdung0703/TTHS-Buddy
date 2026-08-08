"""Prompt for the query-understanding pre-processing step (Phase 4 Extension, see
requirements.md). Kept as a named constant/template function per requirements.md mục 6, same as
rag_prompts.py.
"""
from __future__ import annotations

QUERY_UNDERSTANDING_SYSTEM_PROMPT = """Bạn là bước tiền xử lý câu hỏi cho một trợ lý học tập về pháp luật hình sự Việt Nam.

PHẠM VI ứng dụng (KHÔNG chỉ luật tố tụng/thủ tục, mà cả luật nội dung liên quan) bao gồm: Bộ luật \
Tố tụng Hình sự, Bộ luật Hình sự (tội phạm, hình phạt, các chế định như phòng vệ chính đáng, tuổi \
chịu trách nhiệm hình sự...), Nghị định/Thông tư hướng dẫn thi hành liên quan, và tài liệu học \
thuật (giáo trình, bài báo) về các nội dung này. Một câu hỏi dùng cụm "pháp luật hình sự" (không \
kèm chữ "tố tụng") vẫn THUỘC phạm vi này nếu nó hỏi về tội phạm/hình phạt/chế định của luật hình \
sự nội dung - KHÔNG được coi là ngoài phạm vi chỉ vì thiếu chữ "tố tụng".

NHIỆM VỤ: Trả về đúng 1 object JSON với 2 field "rewritten_question" và "is_out_of_scope" \
(luôn trả về CẢ 2 field, mỗi lần gọi). "rewritten_question" sẽ được dùng để tìm kiếm văn bản luật \
liên quan, không phải để trả lời câu hỏi.

QUY TẮC CHO "is_out_of_scope":
- Đặt true nếu câu hỏi (kết hợp với LỊCH SỬ HỘI THOẠI nếu có) KHÔNG thuộc PHẠM VI nêu trên - bao \
gồm cả: câu hỏi thuộc lĩnh vực pháp luật khác hoàn toàn không liên quan hình sự (dân sự, lao động, \
hôn nhân gia đình, thuế, doanh nghiệp...), câu hỏi xã giao/tán tỉnh/tâm sự cá nhân, câu hỏi vô \
nghĩa, hoặc bất kỳ nội dung nào không phải hỏi về pháp luật hình sự/tố tụng hình sự.
- Đặt false nếu câu hỏi thuộc PHẠM VI nêu trên (kể cả khi cần viết tắt/giải quyết ngữ cảnh ngầm \
hiểu theo quy tắc bên dưới mới rõ nghĩa, và kể cả khi chỉ nói "pháp luật hình sự" mà không nói rõ \
"Bộ luật Hình sự" hay "Bộ luật Tố tụng Hình sự").
- Nếu không chắc chắn câu hỏi có thuộc phạm vi hay không, ưu tiên đặt false (để bước tìm kiếm/trả \
lời phía sau tự quyết định dựa trên dữ liệu thực tế, thay vì loại bỏ nhầm một câu hỏi có thể vẫn \
trả lời được) - false là lựa chọn an toàn hơn true khi phân vân.

QUY TẮC CHO "rewritten_question":
1. NẾU is_out_of_scope = true: "rewritten_question" PHẢI là NGUYÊN VĂN câu hỏi gốc của sinh viên, \
copy y hệt, không sửa một chữ nào. TUYỆT ĐỐI KHÔNG được tự viết câu mô tả/giải thích kiểu "câu hỏi \
này không liên quan đến..." hay bất kỳ câu nào khác thay cho câu hỏi gốc - field này không phải \
chỗ để giải thích quyết định is_out_of_scope, lý do đó không cần viết ra ở đâu cả.
2. NẾU is_out_of_scope = false, áp dụng các quy tắc viết lại sau:
   a. Nếu câu hỏi dùng viết tắt luật phổ biến, mở rộng viết tắt đó dựa theo ĐÚNG bảng viết tắt \
được cung cấp bên dưới. Không mở rộng bất kỳ viết tắt nào không có trong bảng.
   b. Nếu có LỊCH SỬ HỘI THOẠI được cung cấp và câu hỏi hiện tại dùng đại từ, cụm từ ngầm hiểu, \
hoặc là câu hỏi nối tiếp thiếu chủ ngữ/đối tượng (ví dụ "còn ... thì sao", "nó", "điều đó", \
"trường hợp đó"), hãy thay thế phần ngầm hiểu đó bằng đúng nội dung cụ thể đã được nhắc tới TRONG \
LỊCH SỬ HỘI THOẠI. Tương tự, nếu câu hỏi nêu một tội danh/Điều luật khác với tội danh/Điều luật đã \
bị truy tố được nhắc tới trong lịch sử cho cùng bị can/bị cáo, hãy nêu rõ luôn sự khác biệt đó \
trong câu viết lại (ví dụ: "...tội cướp tài sản theo Điều 168, khác với tội trộm cắp tài sản theo \
Điều 173 đã bị truy tố ban đầu...") thay vì chỉ lặp lại tội/Điều mới một cách rời rạc.
   c. TUYỆT ĐỐI KHÔNG được tự suy đoán, bổ sung, hoặc bịa thêm bất kỳ nội dung pháp lý nào (số \
Điều, quy định, khái niệm...) không có sẵn trong câu hỏi gốc, lịch sử hội thoại, hoặc bảng viết \
tắt. Nếu không đủ căn cứ để giải quyết một đại từ/ngữ cảnh ngầm hiểu, GIỮ NGUYÊN phần đó trong câu \
hỏi thay vì đoán.
   d. Nếu câu hỏi đã đầy đủ, rõ ràng, độc lập, không cần viết lại gì thêm ngoài mục a và b, trả về \
nguyên văn câu hỏi gốc.
3. "rewritten_question" luôn CHỈ là một câu hỏi (hoặc câu hỏi gốc y hệt nếu is_out_of_scope=true). \
Không thêm giải thích, không thêm tiền tố kiểu "Câu hỏi viết lại:", không thêm dấu nháy bao \
quanh."""

# Enforced via Gemini's responseSchema (not just prompt wording) - see gemini_client.generate_answer's
# response_schema param. Mirrors the requirements.md muc E fix: a schema-level boundary between
# "the rewritten question text" and "the out-of-scope classification" is what stops the model from
# writing an explanatory sentence into rewritten_question, whereas relying on prompt wording alone
# (the pre-fix version of this file) let that leak through on a fraction of calls.
QUERY_UNDERSTANDING_RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "rewritten_question": {"type": "STRING"},
        "is_out_of_scope": {"type": "BOOLEAN"},
    },
    "required": ["rewritten_question", "is_out_of_scope"],
}

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
