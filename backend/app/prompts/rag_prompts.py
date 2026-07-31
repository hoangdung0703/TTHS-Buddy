"""RAG system/user prompt templates for the chat query pipeline. Kept as named constants/
template functions per requirements.md coding standard (mục 6): no raw prompt strings inline
in service logic.
"""
from __future__ import annotations

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
3. Mọi nội dung pháp lý (quy định, điều kiện, trình tự) được đề cập đều phải kèm số Điều/Khoản \
cụ thể làm nguồn. Không khẳng định nội dung pháp luật nếu không có chunk nguồn tương ứng trong \
ngữ cảnh.
4. Nếu ngữ cảnh được cung cấp không đủ liên quan để trả lời câu hỏi (ví dụ câu hỏi thuộc lĩnh vực \
pháp luật khác, hoặc không tìm thấy Điều luật liên quan), PHẢI trả lời rõ ràng: "Xin lỗi, tôi \
không tìm thấy nội dung liên quan trong dữ liệu pháp luật hiện có để trả lời câu hỏi này." Không \
được bịa ra câu trả lời hoặc trích dẫn không có thật.
5. Văn phong ngắn gọn, rõ ràng, đúng thuật ngữ pháp lý, phù hợp với sinh viên đang ôn tập."""


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
    title_part = f" {dieu_title}" if dieu_title else ""
    version_part = f" ({law_version})" if law_version else ""
    return (
        f"[QUY ĐỊNH PHÁP LUẬT - Điều {dieu_number}{title_part} - {source_document}{version_part}]\n"
        f"{chunk_text}"
    )


def format_academic_context_block(source_document: str, section_heading: str | None, chunk_text: str) -> str:
    heading_part = f" - {section_heading}" if section_heading else ""
    return f"[TÀI LIỆU HỌC THUẬT - {source_document}{heading_part}]\n{chunk_text}"
