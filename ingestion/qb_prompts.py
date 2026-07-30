"""Prompt for normalizing the source PDF's terse "Từ khóa cho bài học" bullets into complete
essay_key_points sentences. Kept as a named template per requirements.md mục 6 (no raw prompt
strings inline in service logic) - same convention as backend/app/prompts/rag_prompts.py.
"""
from __future__ import annotations

NORMALIZE_KEY_POINTS_SYSTEM_PROMPT = """Bạn hỗ trợ chuẩn hóa ngân hàng câu hỏi tự luận Luật Tố \
tụng Hình sự Việt Nam.

Bạn sẽ nhận một danh sách các gạch đầu dòng ngắn gọn ("Từ khóa cho bài học"), mỗi dòng tóm tắt \
1 ý chính của đáp án mẫu cho 1 câu hỏi tự luận.

QUY TẮC BẮT BUỘC:
1. Viết lại MỖI gạch đầu dòng thành ĐÚNG 1 câu tiếng Việt hoàn chỉnh, đúng ngữ pháp, diễn đạt \
lại CHÍNH XÁC ý đã có trong gạch đầu dòng gốc.
2. KHÔNG được thêm bất kỳ ý pháp lý nào không có trong gạch đầu dòng gốc. Không suy diễn, không \
bổ sung căn cứ pháp luật mới, không đoán thêm chi tiết.
3. KHÔNG được gộp 2 gạch đầu dòng thành 1 câu, KHÔNG được tách 1 gạch đầu dòng thành nhiều câu.
4. Số câu output PHẢI bằng đúng số gạch đầu dòng input, giữ nguyên thứ tự.
5. Output MỖI câu trên 1 dòng riêng, KHÔNG đánh số thứ tự, KHÔNG thêm gạch đầu dòng, KHÔNG thêm \
giải thích hay lời dẫn nào khác ngoài các câu đã viết lại."""


def build_normalize_key_points_prompt(question_text: str, sample_answer: str, raw_bullets: list[str]) -> str:
    bullets_block = "\n".join(f"- {bullet}" for bullet in raw_bullets)
    return (
        f"Câu hỏi tự luận: {question_text}\n\n"
        f"Đáp án mẫu (bối cảnh, không cần viết lại): {sample_answer}\n\n"
        f"Các gạch đầu dòng cần viết lại thành câu hoàn chỉnh ({len(raw_bullets)} gạch đầu dòng):\n"
        f"{bullets_block}"
    )
