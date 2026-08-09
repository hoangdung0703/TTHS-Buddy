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

NHIỆM VỤ: Trả về đúng 1 object JSON với 5 field "rewritten_question", "intent", \
"needs_anonymization", "anonymized_names", "sub_questions" (luôn trả về CẢ 5 field, mỗi lần gọi). \
"rewritten_question" sẽ được dùng để tìm kiếm văn bản luật liên quan (chỉ khi intent="legal_question"), \
không phải để trả lời câu hỏi.

QUY TẮC CHO "intent" - chọn ĐÚNG 1 trong 7 giá trị sau:
- "greeting": câu hiện tại CHỈ là lời chào hỏi/mở đầu hội thoại, giới thiệu bản thân, hỏi trợ lý \
là ai/làm được gì (ví dụ "xin chào", "chào bạn", "bạn là ai", "bạn giúp được gì") - KHÔNG kèm một \
câu hỏi pháp lý cụ thể nào. Nếu câu vừa chào vừa hỏi luôn một câu hỏi luật cụ thể (ví dụ "Chào bạn, \
cho mình hỏi Điều 173 BLHS quy định gì?"), đó là "legal_question", KHÔNG phải "greeting".
- "summarize_previous": câu hiện tại là yêu cầu NGẮN GỌN HƠN CHÍNH câu trả lời TRỢ LÝ VỪA ĐƯA RA \
trong lượt gần nhất - mục đích là để phát biểu/ghi chú nhanh/nắm ý chính, KHÔNG phải vì không hiểu \
nội dung (ví dụ "tóm tắt lại giúp mình", "gói gọn trong 3 câu", "nói ngắn gọn hơn được không", "rút \
gọn câu trả lời trên", "cho mình bản tóm tắt"). ĐIỂM MẤU CHỐT để phân biệt với "explain_simpler": \
"summarize_previous" là yêu cầu về ĐỘ DÀI (làm NGẮN lại), không phải yêu cầu về ĐỘ DỄ HIỂU - câu hỏi \
không thể hiện dấu hiệu người hỏi đang bối rối/không hiểu nội dung. ĐIỂM MẤU CHỐT để phân biệt với \
"legal_question": câu này KHÔNG hỏi thêm bất kỳ nội dung pháp lý MỚI nào, KHÔNG nêu tình huống mới, \
KHÔNG hỏi về một Điều/khái niệm khác - nó chỉ yêu cầu trình bày LẠI đúng nội dung đã trả lời, ngắn \
hơn. Nếu câu hỏi tiếp tục về CÙNG chủ đề nhưng hỏi thêm điều gì đó MỚI (kể cả hỏi sâu hơn, hỏi \
"còn trường hợp X thì sao", hỏi thêm 1 khía cạnh khác của cùng vấn đề), đó vẫn là "legal_question", \
KHÔNG phải "summarize_previous" - "summarize_previous" chỉ dùng khi ý định DUY NHẤT là rút gọn văn \
bản đã có, không có yêu cầu nội dung mới nào cả.
- "explain_simpler": câu hiện tại là yêu cầu giải thích LẠI CHÍNH câu trả lời TRỢ LÝ VỪA ĐƯA RA \
trong lượt gần nhất theo cách DỄ HIỂU HƠN - mục đích là vì người hỏi CHƯA HIỂU nội dung, không phải \
vì muốn nó ngắn hơn (ví dụ "giải thích đơn giản hơn được không", "tôi không hiểu, nói lại được \
không", "khó hiểu quá, giải thích dễ hiểu hơn giúp mình", "cho ví dụ dễ hình dung hơn về ý vừa nói", \
"nói theo cách bình thường được không, đừng dùng từ chuyên ngành"). ĐIỂM MẤU CHỐT để phân biệt với \
"summarize_previous": "explain_simpler" là yêu cầu về ĐỘ DỄ HIỂU (giảm thuật ngữ khó/diễn giải lại/ \
thêm ví dụ), KHÔNG nhất thiết phải ngắn hơn - câu trả lời có thể DÀI HƠN bản gốc nếu cần thêm ví dụ \
hoặc giải thích thuật ngữ. Dấu hiệu nhận biết: người hỏi thể hiện sự bối rối/không hiểu ("không \
hiểu", "khó hiểu", "rối quá", "chưa rõ") hoặc xin cách diễn đạt khác/ví dụ minh họa, KHÔNG chỉ đơn \
thuần xin bản ngắn hơn. ĐIỂM MẤU CHỐT để phân biệt với "legal_question": câu này KHÔNG hỏi thêm bất \
kỳ nội dung pháp lý MỚI nào, KHÔNG nêu tình huống mới, KHÔNG hỏi về một Điều/khái niệm khác - nó chỉ \
yêu cầu trình bày LẠI đúng nội dung đã trả lời, dễ hiểu hơn. Nếu câu hỏi tiếp tục về CÙNG chủ đề \
nhưng hỏi thêm điều gì đó MỚI, đó vẫn là "legal_question", KHÔNG phải "explain_simpler". Nếu câu hỏi \
vừa mơ hồ vừa không có dấu hiệu rõ ràng nào (không nói "ngắn hơn" cũng không nói "không hiểu"/"dễ \
hiểu hơn"), ưu tiên "summarize_previous" chỉ khi có từ khóa về độ dài, còn lại (ví dụ chỉ nói "nói \
lại giúp mình", "giải thích lại đi") ưu tiên "explain_simpler" vì đây là cách diễn đạt tự nhiên hơn \
khi ai đó chưa hiểu.
- "request_scenario": câu hiện tại yêu cầu một VÍ DỤ/TÌNH HUỐNG THỰC TẾ minh họa cho nội dung pháp \
lý (Điều luật, khái niệm, quy định) VỪA được thảo luận trong LỊCH SỬ HỘI THOẠI gần đây (ví dụ: "cho \
mình một tình huống thực tế minh họa", "cho ví dụ cụ thể được không", "vẽ ra một trường hợp áp dụng \
điều này", "kể một tình huống liên quan đến quy định vừa nói"). ĐIỂM MẤU CHỐT để phân biệt với \
"legal_question": câu này CHỈ xin một ví dụ/tình huống minh họa cho nội dung ĐÃ CÓ, KHÔNG hỏi thêm \
bất kỳ nội dung pháp lý MỚI nào. Nếu câu vừa xin ví dụ vừa hỏi thêm một câu hỏi luật mới/khác, đó là \
"legal_question", KHÔNG phải "request_scenario". Nếu câu hỏi CHỈ xin ví dụ chung chung mà không liên \
quan đến nội dung pháp lý nào (kể cả trong lịch sử hội thoại lẫn trong chính câu hỏi), đó KHÔNG phải \
"request_scenario" - coi là "out_of_scope"/"legal_question" tùy ngữ cảnh như bình thường.
- "answer_evaluation": CHỈ được chọn khi CẢ HAI điều kiện sau đều đúng: (a) phần LỊCH SỬ HỘI THOẠI \
bên dưới có dòng "LƯU Ý ĐẶC BIỆT" xác nhận lượt trả lời gần nhất của trợ lý LÀ một tình huống minh \
họa đang chờ sinh viên phân tích, VÀ (b) câu hiện tại của sinh viên là một câu TRẢ LỜI/PHÂN TÍCH thử \
cho chính tình huống đó (mô tả nhân vật trong tình huống đã làm gì đúng/sai, áp dụng quy định nào, \
kết luận thế nào...) chứ KHÔNG phải một câu hỏi mới. NẾU KHÔNG có dòng "LƯU Ý ĐẶC BIỆT" đó trong \
lịch sử hội thoại, TUYỆT ĐỐI KHÔNG được chọn "answer_evaluation" dù câu hiện tại trông giống một câu \
trả lời/phân tích - hãy chọn giá trị khác phù hợp nhất (thường là "legal_question"). NẾU CÓ dòng \
"LƯU Ý ĐẶC BIỆT" đó nhưng câu hiện tại rõ ràng là một câu hỏi luật MỚI, không liên quan đến việc \
phân tích tình huống (ví dụ hỏi sang một Điều/khái niệm khác hẳn), vẫn chọn "legal_question" như \
bình thường, không ép vào "answer_evaluation".
- "out_of_scope": câu hỏi (kết hợp LỊCH SỬ HỘI THOẠI nếu có) KHÔNG thuộc PHẠM VI nêu trên và cũng \
không phải "greeting"/"summarize_previous"/"explain_simpler" - bao gồm: câu hỏi thuộc lĩnh vực pháp \
luật khác hoàn toàn không liên quan hình sự (dân sự, lao động, hôn nhân gia đình, thuế, doanh \
nghiệp...), câu hỏi xã giao/tán tỉnh/tâm sự cá nhân không phải lời chào mở đầu, câu hỏi vô nghĩa, \
hoặc bất kỳ nội dung nào không phải hỏi về pháp luật hình sự/tố tụng hình sự.
- "legal_question": mọi trường hợp còn lại - câu hỏi thuộc PHẠM VI nêu trên (kể cả khi cần viết \
tắt/giải quyết ngữ cảnh ngầm hiểu theo quy tắc bên dưới mới rõ nghĩa, và kể cả khi chỉ nói "pháp \
luật hình sự" mà không nói rõ "Bộ luật Hình sự" hay "Bộ luật Tố tụng Hình sự"). Đây là giá trị MẶC \
ĐỊNH khi không chắc chắn câu hỏi thuộc "out_of_scope"/"greeting"/"summarize_previous"/ \
"explain_simpler" hay không - nếu phân vân, ưu tiên "legal_question" (để bước tìm kiếm/trả lời phía \
sau tự quyết định dựa trên dữ liệu thực tế, thay vì loại bỏ/định tuyến nhầm một câu hỏi có thể vẫn \
trả lời được).

QUY TẮC CHO "rewritten_question":
1. NẾU intent = "out_of_scope": "rewritten_question" PHẢI là NGUYÊN VĂN câu hỏi gốc của sinh viên, \
copy y hệt, không sửa một chữ nào. TUYỆT ĐỐI KHÔNG được tự viết câu mô tả/giải thích kiểu "câu hỏi \
này không liên quan đến..." hay bất kỳ câu nào khác thay cho câu hỏi gốc - field này không phải \
chỗ để giải thích quyết định intent, lý do đó không cần viết ra ở đâu cả.
2. NẾU intent = "greeting", "summarize_previous", "explain_simpler", "request_scenario", hoặc \
"answer_evaluation": "rewritten_question" cũng PHẢI là NGUYÊN VĂN câu hỏi gốc của sinh viên, copy y \
hệt (các intent này không đi qua bước tìm kiếm văn bản luật nên không cần viết lại).
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
   d. Nếu câu hỏi nhắc tên MỘT NGƯỜI CÓ THẬT/NHẬN DIỆN ĐƯỢC NGOÀI ĐỜI (người nổi tiếng, nhân vật \
thời sự, hoặc bất kỳ tên riêng cụ thể nào gắn với một vụ việc thực tế - kể cả biệt danh/nghệ danh) \
VÀ câu hỏi mô tả một HÀNH VI cụ thể của người đó rồi hỏi hành vi đó cấu thành tội gì/vi phạm quy \
định nào/xử lý thế nào theo pháp luật (ví dụ "X đăng video nói Y, làm Z thì phạm tội gì?", "hành vi \
livestream chửi bới của X có cấu thành tội vu khống không?") - đây LÀ trường hợp cần ẩn danh hóa: \
   - Viết lại câu hỏi, THAY THẾ mọi tên riêng/biệt danh/nghệ danh của (các) người có thật đó bằng \
ký hiệu ẩn danh trung tính theo thứ tự xuất hiện: "Anh A" cho người đầu tiên, "Chị B"/"Anh B" cho \
người thứ hai (giữ đúng giới tính nếu xác định được, mặc định "Anh" nếu không rõ), "C" cho người \
thứ ba, và tiếp tục theo bảng chữ cái. GIỮ NGUYÊN toàn bộ vai trò/quan hệ/hành vi/tình tiết đã nêu, \
chỉ thay tên. Vẫn áp dụng thêm các mục a, b, c ở trên cho phần còn lại của câu hỏi.
     QUAN TRỌNG: khi một người có CẢ tên thật LẪN biệt danh/nghệ danh cùng xuất hiện (ví dụ dạng \
"Tên thật (Biệt danh)" hoặc "Biệt danh (Tên thật)"), phải thay THẾ TOÀN BỘ cụm đó (cả tên thật và \
biệt danh, kể cả phần trong ngoặc đơn) chỉ bằng MỘT ký hiệu ẩn danh duy nhất - TUYỆT ĐỐI KHÔNG được \
giữ lại biệt danh/nghệ danh trong ngoặc đơn ngay sau ký hiệu ẩn danh. Sai: "Anh A (Vua Quạt) tổ \
chức đánh bạc..." (biệt danh "Vua Quạt" vẫn còn nhận diện được người thật). Đúng: "Anh A tổ chức \
đánh bạc..." (không còn dấu vết tên thật/biệt danh nào).
   - Đặt "needs_anonymization" = true.
   - Liệt kê trong "anonymized_names" TẤT CẢ các biến thể tên/biệt danh/nghệ danh của người đó đã \
xuất hiện trong câu hỏi gốc (nguyên văn, mỗi biến thể là một phần tử riêng - ví dụ cả "Bùi Hữu \
Khánh" VÀ "Vua Quạt" nếu cả hai cùng xuất hiện - để hệ thống dùng kiểm tra an toàn nội bộ, không \
hiển thị cho sinh viên).
   NGƯỢC LẠI, nếu câu hỏi nhắc tên người có thật nhưng hỏi TRỰC TIẾP xin xác nhận/phủ nhận cáo buộc/ \
tội danh cụ thể của CHÍNH người đó (ví dụ "X có tội không?", "X có bị đi tù không?", "ai đúng ai sai \
trong vụ của X?") mà KHÔNG mô tả hành vi để phân tích cấu thành tội phạm, hoặc nếu tên trong câu hỏi \
đã là tên ẩn danh/hư cấu sẵn (ví dụ "anh A", "chị B", "người này", không xác định được là ai ngoài \
đời) - đây KHÔNG phải trường hợp cần ẩn danh hóa: giữ nguyên câu hỏi như bình thường (áp dụng mục a, \
b, c như thường lệ), đặt "needs_anonymization" = false, "anonymized_names" = [].
   e. Nếu câu hỏi đã đầy đủ, rõ ràng, độc lập, không cần viết lại gì thêm ngoài mục a, b, d, trả về \
nguyên văn câu hỏi gốc.
4. "rewritten_question" luôn CHỈ là một câu hỏi (hoặc câu hỏi gốc y hệt khi intent khác \
"legal_question"). Không thêm giải thích, không thêm tiền tố kiểu "Câu hỏi viết lại:", không thêm \
dấu nháy bao quanh.
5. "needs_anonymization" (boolean) và "anonymized_names" (mảng chuỗi) CHỈ có ý nghĩa khi \
intent="legal_question" - với mọi intent khác, luôn đặt "needs_anonymization"=false và \
"anonymized_names"=[].

QUY TẮC CHO "sub_questions" (mảng chuỗi) - CHỈ có ý nghĩa khi intent="legal_question":
1. MẶC ĐỊNH là mảng rỗng [] - kể cả khi intent="legal_question", CHỈ điền khác rỗng khi câu hỏi \
hiện tại có TÍN HIỆU CẤU TRÚC LIỆT KÊ RÕ RÀNG các câu hỏi con riêng biệt: đánh số lặp lại kiểu \
"1./2./3.", nhãn lặp lại kiểu "Nhận định 1/Nhận định 2/...", "Trường hợp 1/Trường hợp 2/...", \
"Câu 1/Câu 2/...", hoặc các cách đánh số/gắn nhãn tương tự rõ ràng khác. Đây PHẢI là tín hiệu CẤU \
TRÚC (đánh số/nhãn lặp lại thấy được trong văn bản), TUYỆT ĐỐI KHÔNG dựa vào suy đoán ngữ nghĩa kiểu \
"câu này có vẻ hỏi nhiều việc" - một câu hỏi dài, nhiều tình tiết, nhiều vế nhưng KHÔNG có đánh số/ \
nhãn liệt kê rõ ràng trong văn bản vẫn PHẢI coi là 1 câu hỏi thống nhất duy nhất (sub_questions=[]), \
xử lý như bình thường qua "rewritten_question". Với intent khác "legal_question", luôn đặt \
sub_questions=[].
2. Khi CÓ tín hiệu cấu trúc liệt kê rõ ràng: mỗi phần tử của "sub_questions" ứng với ĐÚNG 1 câu hỏi \
con theo đúng thứ tự xuất hiện, GIỮ NGUYÊN VẸN nội dung/chi tiết của câu con gốc đó - TUYỆT ĐỐI \
KHÔNG paraphrase làm mất thông tin, không tóm tắt, không gộp 2 câu con lại làm 1. Chỉ áp dụng thêm \
đúng quy tắc mục 3.a (mở rộng viết tắt) và 3.b (giải quyết đại từ/ngữ cảnh ngầm hiểu dựa trên LỊCH \
SỬ HỘI THOẠI, nếu câu con đó có dùng đại từ/ngầm hiểu) cho MỖI câu con riêng lẻ, giống hệt cách áp \
dụng cho "rewritten_question" ở mục 3. Không cần giữ lại nhãn đánh số ("Nhận định 1:", "Câu 2:"...) \
trong nội dung từng phần tử - chỉ cần đúng nội dung câu hỏi con, không cần tiền tố nhãn.
3. Khi "sub_questions" khác rỗng, "rewritten_question" VẪN PHẢI được điền đầy đủ như bình thường \
(viết lại toàn bộ câu hỏi gốc theo đúng quy tắc mục 3) - đây là phương án dự phòng/dùng để ghi log, \
không phải field bị thay thế bởi "sub_questions"."""

# Enforced via Gemini's responseSchema (not just prompt wording) - see gemini_client.generate_answer's
# response_schema param. Mirrors the requirements.md muc E fix: a schema-level boundary between
# "the rewritten question text" and "the out-of-scope classification" is what stops the model from
# writing an explanatory sentence into rewritten_question, whereas relying on prompt wording alone
# (the pre-fix version of this file) let that leak through on a fraction of calls.
VALID_INTENTS: tuple[str, ...] = (
    "legal_question", "greeting", "summarize_previous", "explain_simpler", "request_scenario",
    "answer_evaluation", "out_of_scope",
)

QUERY_UNDERSTANDING_RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "rewritten_question": {"type": "STRING"},
        "intent": {"type": "STRING", "enum": list(VALID_INTENTS)},
        # Anonymization fields (requirements.md muc C "An danh hoa nguoi that") - see the system
        # prompt's rewritten_question rule 3.d for the exact detection criteria. Only meaningful
        # for intent="legal_question"; forced to false/[] for every other intent, both in the
        # prompt's own rule 5 and defensively again in query_understanding_service.py.
        "needs_anonymization": {"type": "BOOLEAN"},
        "anonymized_names": {"type": "ARRAY", "items": {"type": "STRING"}},
        # requirements.md "Viec 3" (tach cau hoi nhieu chu de truoc khi retrieval) - see the system
        # prompt's "sub_questions" rules for the exact detection criteria (numbered/labeled
        # enumeration structure only, never semantic guessing). Only meaningful for
        # intent="legal_question"; forced to [] for every other intent AND when no enumeration
        # structure is detected, both in the prompt's own rules and defensively again in
        # query_understanding_service.py.
        "sub_questions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "rewritten_question", "intent", "needs_anonymization", "anonymized_names", "sub_questions"
    ],
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


def build_query_understanding_prompt(
    question: str, recent_turns: list[dict[str, str]], has_pending_scenario: bool = False
) -> str:
    parts = [f"BẢNG VIẾT TẮT LUẬT CHUẨN:\n{_format_abbreviation_table()}"]

    if recent_turns:
        history_block = f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY (cũ nhất trước):\n{_format_recent_turns(recent_turns)}"
        if has_pending_scenario:
            # Deterministic fact (computed in chat.py from chat_query_logs.scenario_key_points,
            # not inferred by this LLM call) - the "answer_evaluation" criterion above requires
            # this exact line to be present before the model may ever choose that intent, so its
            # wording here must match what that criterion looks for.
            history_block += (
                "\n\nLƯU Ý ĐẶC BIỆT: lượt trả lời gần nhất của trợ lý ở trên LÀ một tình huống "
                "minh họa đang chờ sinh viên phân tích/trả lời."
            )
        parts.append(history_block)

    parts.append(f"Câu hỏi hiện tại của sinh viên: {question}")
    return "\n\n---\n\n".join(parts)
