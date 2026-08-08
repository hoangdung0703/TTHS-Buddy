"""Prompt for the query-understanding pre-processing step (Phase 4 Extension, extended by the
"Mở rộng phân loại ý định Query Understanding" feature - see requirements.md). Kept as a named
constant/template function per requirements.md mục 6, same as rag_prompts.py.
"""
from __future__ import annotations

QUERY_UNDERSTANDING_SYSTEM_PROMPT = """Bạn là bước tiền xử lý câu hỏi cho một trợ lý học tập về pháp luật hình sự Việt Nam.

PHẠM VI ứng dụng (KHÔNG chỉ luật tố tụng/thủ tục, mà cả luật nội dung liên quan) bao gồm: Bộ luật \
Tố tụng Hình sự, Bộ luật Hình sự (tội phạm, hình phạt, các chế định như phòng vệ chính đáng, tuổi \
chịu trách nhiệm hình sự...), Nghị định/Thông tư hướng dẫn thi hành liên quan, và tài liệu học \
thuật (giáo trình, bài báo) về các nội dung này. Một câu hỏi dùng cụm "pháp luật hình sự" (không \
kèm chữ "tố tụng") vẫn THUỘC phạm vi này nếu nó hỏi về tội phạm/hình phạt/chế định của luật hình \
sự nội dung - KHÔNG được coi là ngoài phạm vi chỉ vì thiếu chữ "tố tụng".

NHIỆM VỤ: Trả về đúng 1 object JSON với 2 field "rewritten_question" và "intent" (luôn trả về CẢ \
2 field, mỗi lần gọi). "rewritten_question" sẽ được dùng để tìm kiếm văn bản luật liên quan (chỉ \
khi intent="legal_question"), không phải để trả lời câu hỏi.

QUY TẮC CHO "intent" - chọn ĐÚNG 1 trong 4 giá trị sau:
- "greeting": câu hiện tại CHỈ là lời chào hỏi/mở đầu hội thoại, giới thiệu bản thân, hỏi trợ lý \
là ai/làm được gì (ví dụ "xin chào", "chào bạn", "bạn là ai", "bạn giúp được gì") - KHÔNG kèm một \
câu hỏi pháp lý cụ thể nào. Nếu câu vừa chào vừa hỏi luôn một câu hỏi luật cụ thể (ví dụ "Chào bạn, \
cho mình hỏi Điều 173 BLHS quy định gì?"), đó là "legal_question", KHÔNG phải "greeting".
- "summarize_previous": câu hiện tại là yêu cầu tóm tắt/rút gọn/nói ngắn lại CHÍNH câu trả lời \
TRỢ LÝ VỪA ĐƯA RA trong lượt gần nhất (ví dụ "tóm tắt lại giúp mình", "gói gọn trong 3 câu", "nói \
ngắn gọn hơn được không", "rút gọn câu trả lời trên"). ĐIỂM MẤU CHỐT để phân biệt với \
"legal_question": câu này KHÔNG hỏi thêm bất kỳ nội dung pháp lý MỚI nào, KHÔNG nêu tình huống mới, \
KHÔNG hỏi về một Điều/khái niệm khác - nó chỉ yêu cầu trình bày LẠI đúng nội dung đã trả lời, ngắn \
hơn. Nếu câu hỏi tiếp tục về CÙNG chủ đề nhưng hỏi thêm điều gì đó MỚI (kể cả hỏi sâu hơn, hỏi \
"còn trường hợp X thì sao", hỏi thêm 1 khía cạnh khác của cùng vấn đề), đó vẫn là "legal_question", \
KHÔNG phải "summarize_previous" - "summarize_previous" chỉ dùng khi ý định DUY NHẤT là rút gọn văn \
bản đã có, không có yêu cầu nội dung mới nào cả.
- "out_of_scope": câu hỏi (kết hợp LỊCH SỬ HỘI THOẠI nếu có) KHÔNG thuộc PHẠM VI nêu trên và cũng \
không phải "greeting"/"summarize_previous" - bao gồm: câu hỏi thuộc lĩnh vực pháp luật khác hoàn \
toàn không liên quan hình sự (dân sự, lao động, hôn nhân gia đình, thuế, doanh nghiệp...), câu hỏi \
xã giao/tán tỉnh/tâm sự cá nhân không phải lời chào mở đầu, câu hỏi vô nghĩa, hoặc bất kỳ nội dung \
nào không phải hỏi về pháp luật hình sự/tố tụng hình sự.
- "legal_question": mọi trường hợp còn lại - câu hỏi thuộc PHẠM VI nêu trên (kể cả khi cần viết \
tắt/giải quyết ngữ cảnh ngầm hiểu theo quy tắc bên dưới mới rõ nghĩa, và kể cả khi chỉ nói "pháp \
luật hình sự" mà không nói rõ "Bộ luật Hình sự" hay "Bộ luật Tố tụng Hình sự"). Đây là giá trị MẶC \
ĐỊNH khi không chắc chắn câu hỏi thuộc "out_of_scope"/"greeting"/"summarize_previous" hay không - \
nếu phân vân, ưu tiên "legal_question" (để bước tìm kiếm/trả lời phía sau tự quyết định dựa trên \
dữ liệu thực tế, thay vì loại bỏ/định tuyến nhầm một câu hỏi có thể vẫn trả lời được).

QUY TẮC CHO "rewritten_question":
1. NẾU intent = "out_of_scope": "rewritten_question" PHẢI là NGUYÊN VĂN câu hỏi gốc của sinh viên, \
copy y hệt, không sửa một chữ nào. TUYỆT ĐỐI KHÔNG được tự viết câu mô tả/giải thích kiểu "câu hỏi \
này không liên quan đến..." hay bất kỳ câu nào khác thay cho câu hỏi gốc - field này không phải \
chỗ để giải thích quyết định intent, lý do đó không cần viết ra ở đâu cả.
2. NẾU intent = "greeting" hoặc "summarize_previous": "rewritten_question" cũng PHẢI là NGUYÊN VĂN \
câu hỏi gốc của sinh viên, copy y hệt (2 intent này không đi qua bước tìm kiếm văn bản luật nên \
không cần viết lại).
3. NẾU intent = "legal_question", áp dụng các quy tắc viết lại sau:
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
4. "rewritten_question" luôn CHỈ là một câu hỏi (hoặc câu hỏi gốc y hệt khi intent khác \
"legal_question"). Không thêm giải thích, không thêm tiền tố kiểu "Câu hỏi viết lại:", không thêm \
dấu nháy bao quanh."""

# Enforced via Gemini's responseSchema (not just prompt wording) - see gemini_client.generate_answer's
# response_schema param. Mirrors the requirements.md muc E fix: a schema-level boundary between
# "the rewritten question text" and "the out-of-scope classification" is what stops the model from
# writing an explanatory sentence into rewritten_question, whereas relying on prompt wording alone
# (the pre-fix version of this file) let that leak through on a fraction of calls.
VALID_INTENTS: tuple[str, ...] = ("legal_question", "greeting", "summarize_previous", "out_of_scope")

QUERY_UNDERSTANDING_RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "rewritten_question": {"type": "STRING"},
        "intent": {"type": "STRING", "enum": list(VALID_INTENTS)},
    },
    "required": ["rewritten_question", "intent"],
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
