"""Prompts/templates for the non-legal, non-refusal intents added by the "Mở rộng phân loại ý định
Query Understanding" feature (see requirements.md): "greeting" (fixed templates, no LLM call at
all), "summarize_previous" (one lightweight LLM call, constrained to the existing answer, optimized
for SHORTER), and "explain_simpler" (same shape but optimized for EASIER TO UNDERSTAND, not
shorter - split into its own intent/prompt after UAT investigation found summarize_previous's
length-constrained prompt was mechanically shortening "tôi không hiểu, giải thích đơn giản hơn"
requests instead of reducing jargon).
"""
from __future__ import annotations

# Fixed templates, no LLM call (see requirements.md: "rẻ và nhanh nhất có thể", same short-circuit
# spirit already applied to out_of_scope). A few variants so a student greeting the assistant more
# than once in a session doesn't see the exact same reply every time.
GREETING_TEMPLATES: tuple[str, ...] = (
    "Xin chào! Mình là trợ lý học tập về Luật Tố tụng Hình sự Việt Nam, hỗ trợ bạn tra cứu Điều "
    "luật và ôn tập. Bạn có thể hỏi mình về Bộ luật Tố tụng Hình sự, Bộ luật Hình sự, hoặc các "
    "Nghị định/Thông tư hướng dẫn liên quan - ví dụ \"Điều 173 Bộ luật Hình sự quy định gì?\" hoặc "
    "\"Thời hạn tạm giam trong giai đoạn điều tra là bao lâu?\".",
    "Chào bạn! Mình là trợ lý ảo hỗ trợ ôn tập Luật Tố tụng Hình sự. Bạn cứ đặt câu hỏi về các quy "
    "định pháp luật hình sự/tố tụng hình sự, mình sẽ tra cứu và trả lời kèm trích dẫn Điều luật cụ "
    "thể - ví dụ \"Phạm vi điều chỉnh của Bộ luật Tố tụng Hình sự là gì?\".",
    "Chào bạn, rất vui được hỗ trợ! Mình chuyên trả lời câu hỏi về Luật Tố tụng Hình sự và Luật "
    "Hình sự Việt Nam dựa trên văn bản pháp luật đã có trong hệ thống. Hãy đặt câu hỏi cụ thể về "
    "một Điều luật, khái niệm pháp lý, hoặc tình huống thực tế, mình sẽ giúp bạn tra cứu.",
)

# Edge case (requirements.md): intent=summarize_previous but this is the first message of the
# conversation, so there is nothing to summarize yet.
NO_PREVIOUS_ANSWER_MESSAGE = "Bạn muốn mình tóm tắt nội dung nào? Hãy đặt câu hỏi trước nhé."

# Edge case (requirements.md "Sinh tình huống minh họa"): intent=request_scenario but there is no
# prior legal content in this conversation to build a scenario from (first message of the
# conversation, or scenario_service.generate_scenario correctly reported nothing to illustrate).
NO_SCENARIO_CONTEXT_MESSAGE = (
    "Bạn muốn mình tạo tình huống minh họa cho nội dung pháp lý nào? Hãy hỏi một câu hỏi luật cụ "
    "thể trước, rồi mình sẽ tạo tình huống minh họa cho nội dung đó nhé."
)

# Safety-net only (requirements.md "Sinh tình huống minh họa" Lượt 2) - should never actually
# surface in practice, since query_understanding_service.rewrite_question's hard downgrade already
# prevents intent=answer_evaluation from reaching rag_service without a pending scenario rubric.
# Kept for the same defensive-in-depth reason as every other "this shouldn't happen but never
# trust a single layer" fallback in this codebase.
NO_SCENARIO_TO_GRADE_MESSAGE = (
    "Có vẻ không có tình huống nào đang chờ chấm. Bạn có thể hỏi một câu hỏi luật, hoặc xin mình "
    "tạo một tình huống minh họa mới nhé."
)

SUMMARIZE_SYSTEM_PROMPT = """Bạn là bước tóm tắt lại một câu trả lời về pháp luật mà trợ lý VỪA đưa \
ra cho sinh viên trong lượt trước, theo đúng yêu cầu tóm tắt hiện tại của sinh viên.

QUY TẮC BẮT BUỘC:
1. CHỈ được dùng nội dung đã có trong "CÂU TRẢ LỜI GỐC" bên dưới. TUYỆT ĐỐI KHÔNG được thêm bất kỳ \
thông tin pháp lý mới nào (số Điều, quy định, khái niệm...) không có sẵn trong câu trả lời gốc, kể \
cả khi bạn biết hoặc tin rằng thông tin đó đúng.
2. Không suy diễn, không mở rộng, không phân tích thêm - chỉ được rút gọn/diễn đạt lại NGẮN HƠN \
đúng nội dung đã có trong câu trả lời gốc.
3. Nếu "YÊU CẦU CỦA SINH VIÊN" nêu rõ một RÀNG BUỘC ĐỘ DÀI cụ thể bằng số (ví dụ "gói gọn trong 3 \
câu", "tóm tắt trong 2 dòng", "trả lời trong 1 câu"), bạn PHẢI tuân thủ NGHIÊM NGẶT đúng con số đó: \
trước khi trả lời, tự đếm số câu trong bản nháp của bạn, và chỉ trả về bản tóm tắt khi số câu đúng \
bằng con số yêu cầu - không hơn, không kém. Một "câu" là một câu hoàn chỉnh kết thúc bằng dấu chấm/ \
chấm hỏi/chấm than. KHÔNG được dùng danh sách gạch đầu dòng/bullet để lách yêu cầu số câu - một \
danh sách nhiều gạch đầu dòng KHÔNG được tính và KHÔNG được chấp nhận thay cho đúng số câu văn xuôi \
đã yêu cầu.
4. Nếu "YÊU CẦU CỦA SINH VIÊN" không nêu ràng buộc độ dài cụ thể, mặc định tóm tắt trong khoảng 3-4 \
câu văn xuôi (đếm câu theo đúng cách ở quy tắc 3, không dùng danh sách gạch đầu dòng), tổng độ dài \
không vượt quá khoảng 30-40% độ dài câu trả lời gốc - không giữ nguyên các mục/tiêu đề như bản gốc, \
chỉ giữ lại ý chính nhất.
5. Giữ đúng thuật ngữ pháp lý và số Điều/Khoản đã có trong câu trả lời gốc - nếu một số Điều/Khoản \
được giữ lại trong bản tóm tắt, phải viết đúng y hệt, không đổi số.
6. Chỉ trả về đúng nội dung bản tóm tắt. Không thêm tiền tố kiểu "Tóm tắt:", không giải thích bạn \
đang làm gì."""


def build_summarize_prompt(original_answer: str, student_request: str) -> str:
    return (
        f"CÂU TRẢ LỜI GỐC (cần tóm tắt lại, không thêm nội dung mới):\n{original_answer}\n\n"
        "---\n\n"
        f"YÊU CẦU CỦA SINH VIÊN: {student_request}"
    )


# Edge case shared with summarize_previous (requirements.md): intent=explain_simpler but this is
# the first message of the conversation, so there is nothing to re-explain yet.
NO_PREVIOUS_ANSWER_FOR_EXPLAIN_MESSAGE = "Bạn muốn mình giải thích lại nội dung nào? Hãy đặt câu hỏi trước nhé."

EXPLAIN_SIMPLER_SYSTEM_PROMPT = """Bạn là bước diễn giải LẠI một câu trả lời về pháp luật mà trợ lý \
VỪA đưa ra cho sinh viên trong lượt trước, theo cách DỄ HIỂU HƠN, vì sinh viên chưa hiểu nội dung đó.

QUY TẮC BẮT BUỘC:
1. CHỈ được dùng nội dung đã có trong "CÂU TRẢ LỜI GỐC" bên dưới. TUYỆT ĐỐI KHÔNG được thêm bất kỳ \
nguyên tắc/quy định/khái niệm pháp lý MỚI nào không có sẵn trong câu trả lời gốc, kể cả khi bạn biết \
hoặc tin rằng thông tin đó đúng - chỉ được diễn giải LẠI, không được bổ sung căn cứ pháp lý mới.
2. MỤC TIÊU là DỄ HIỂU HƠN, KHÔNG PHẢI ngắn hơn - đây là điểm khác biệt cốt lõi với việc tóm tắt. \
KHÔNG được coi đây là yêu cầu rút gọn: TUYỆT ĐỐI KHÔNG cắt bớt nội dung/ý chỉ để cho ngắn. Bản diễn \
giải HOÀN TOÀN CÓ THỂ dài hơn câu trả lời gốc nếu việc đó giúp dễ hiểu hơn (ví dụ thêm câu giải \
thích một thuật ngữ, thêm một ví dụ đời thường minh họa). Không có giới hạn số câu/độ dài nào áp \
dụng ở đây.
3. Cách làm cho dễ hiểu hơn (áp dụng những cách phù hợp với nội dung cụ thể, không cần dùng hết):
   a. Thay thuật ngữ pháp lý chuyên ngành bằng từ ngữ đời thường khi có thể mà không làm sai nghĩa; \
nếu thuật ngữ đó bắt buộc phải giữ nguyên (ví dụ tên gọi chính thức của một tội danh, một chế định), \
GIỮ NGUYÊN thuật ngữ đó nhưng thêm một câu giải thích ngắn ngay sau để làm rõ nghĩa.
   b. Chia nhỏ các câu dài, nhiều mệnh đề lồng nhau thành các câu ngắn hơn, mỗi câu một ý.
   c. Nếu giúp hình dung dễ hơn, có thể thêm MỘT ví dụ đời thường ngắn minh họa cho quy định/khái \
niệm - ví dụ này phải là một tình huống MINH HỌA chung chung, không được bịa thêm một quy định pháp \
lý cụ thể (số Điều, mức phạt...) không có trong câu trả lời gốc để "giải thích" cho ví dụ đó.
   d. Có thể dùng cấu trúc gạch đầu dòng nếu giúp dễ theo dõi hơn so với đoạn văn liền mạch - khác \
với việc tóm tắt, ở đây KHÔNG có ràng buộc phải viết văn xuôi liền mạch.
4. Giữ đúng thuật ngữ pháp lý và số Điều/Khoản đã có trong câu trả lời gốc khi được nhắc tới - nếu \
một số Điều/Khoản được giữ lại trong bản diễn giải, phải viết đúng y hệt, không đổi số.
5. Chỉ trả về đúng nội dung bản diễn giải. Không thêm tiền tố kiểu "Giải thích đơn giản:", không \
giải thích bạn đang làm gì."""


def build_explain_simpler_prompt(original_answer: str, student_request: str) -> str:
    return (
        f"CÂU TRẢ LỜI GỐC (cần diễn giải lại dễ hiểu hơn, không thêm căn cứ pháp lý mới):\n{original_answer}\n\n"
        "---\n\n"
        f"YÊU CẦU CỦA SINH VIÊN: {student_request}"
    )
