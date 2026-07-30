TTHS Buddy — Frontend Design Reference
File tham chiếu thiết kế UI — đọc cùng với requirements.md khi build giao diện (Phase 8 và các phase liên quan UI).

1. Định hướng phong cách
Phong cách: Academic/legal-tech hiện đại — gọn gàng, đáng tin cậy, không phô trương. Cảm giác giống công cụ nghiên cứu pháp lý chuyên nghiệp, không phải app giải trí.

Nguyên tắc thiết kế:
- Whitespace rộng rãi, border mỏng thay vì shadow đậm
- Typography: Fraunces (serif, heading/display) + Inter (sans, UI/body) qua next/font/google
- Bo góc vừa phải (rounded-lg), không bo tròn quá mức kiểu app tiêu dùng

Bảng màu editorial (be ấm + indigo-navy) — DUY NHẤT xuyên suốt toàn dự án kể từ bản đồng bộ token gốc, không còn tách biệt landing/app như trước:
- Nền chính (`--background`): `#F5F0E8` (be ấm) — HSL `37 39% 94%`
- Nền card/popover (`--card`): `#FAF7F2` (be ấm nhạt hơn nền chính) — HSL `38 44% 96%`
- Chữ chính (`--foreground`): `#1A1830` (mực đậm gần đen) — HSL `245 33% 14%`
- Chữ phụ/muted (`--muted-foreground`): `#6B6580` — HSL `253 12% 45%`
- Accent chính/primary (`--primary`): indigo-navy `#1E2460` — HSL `235 52% 25%` — dùng cho logo, nút chính, tag nổi bật, tin nhắn user trong chat
- Accent phụ (`--accent`): vàng đồng (gold) `#B89A52` — HSL `42 42% 52%` — dùng cho eyebrow label, citation pill, icon badge trang trí
- Nền phụ (`--secondary`) `#E8E2D6`, nền muted trung tính (`--muted`) `#DDD8CE`
- Border/input: navy nhạt hoá, HSL `235 20% 88%`; ring focus dùng thẳng giá trị primary, HSL `235 52% 25%`
- Toàn bộ định nghĩa nằm ở `frontend/src/app/globals.css` (`:root`), KHÔNG có namespace Tailwind riêng cho landing nữa — mọi nơi dùng class ngữ nghĩa chuẩn (`bg-background`, `text-foreground`, `bg-primary`, `text-accent`...) tự động ăn đúng bảng màu này.
- QUAN TRỌNG — màu mang Ý NGHĨA CHỨC NĂNG (đỏ/vàng/xanh theo ngưỡng điểm quiz, trạng thái đúng/sai) KHÔNG dùng token ngữ nghĩa ở trên — luôn hardcode trực tiếp Tailwind red-400/amber-400/emerald-600... (xem `progress-bar.tsx`, `quiz/page.tsx`) để không bao giờ đổi màu theo re-theme thương hiệu. Chỉ dùng màu cảnh báo (amber/đỏ nhạt) cho trạng thái cần chú ý (điểm thấp, cần ôn tập), không dùng cho mục đích trang trí.

Bố cục chung toàn app:
- Sidebar trái cố định: logo "TTHS Buddy" + subtitle "Học tập · BLTTHS 2015", điều hướng chính (Tổng quan, Trợ lý AI), nút "Hội thoại mới", ô tìm kiếm hội thoại, danh sách lịch sử hội thoại (mỗi item có tiêu đề, tag chủ đề nhỏ, thời gian)
- Top bar: breadcrumb/tiêu đề trang hiện tại bên trái, thông tin ngày giờ + avatar user bên phải
- Góc dưới sidebar: thông tin user (tên, mã lớp/khoa)


2. Màn hình Chat

Bố cục:
- Tin nhắn user: căn phải, nền accent đậm (`bg-primary`, navy `#1E2460`), chữ trắng
- Tin nhắn AI: căn trái, nền card be ấm nhạt (`bg-card`, không phải trắng tinh), có avatar/icon logo nhỏ kèm nhãn "TTHS Buddy · AI · [tên chủ đề]"
- Nội dung câu trả lời AI: format có heading phụ (in đậm), danh sách đánh số khi liệt kê hệ quả/điều kiện, không dùng bảng nếu không cần thiết

Khối trích dẫn (citation) — thành phần quan trọng nhất, bắt buộc có ở mọi câu trả lời liên quan luật:
- Đặt ngay dưới nội dung câu trả lời, có label "Căn cứ pháp lý" kèm số lượng
- Mỗi nguồn hiển thị dạng pill/badge bo tròn, có icon #, text ngắn gọn kiểu "Điều 23 BLTTHS 2015", có thể bấm để mở rộng xem nguyên văn điều luật
- QUAN TRỌNG — đối chiếu scope thật: chỉ hiển thị badge cho nguồn thực sự có trong vector DB (BLTTHS + Nghị quyết/Thông tư đã ingest ở Phase 3). KHÔNG dùng Hiến pháp 2013 hay bất kỳ văn bản nào chưa được ingest làm ví dụ/placeholder trong code thật, kể cả khi mockup Figma có hiển thị — tránh vi phạm nguyên tắc grounding đã định nghĩa ở requirements.md mục 4.

Suggested question chips:
- Trạng thái cold-start (chưa hỏi gì): hàng chip cuộn ngang phía trên ô nhập liệu, lấy từ GET /api/chat/suggestions — danh sách tĩnh do nhóm luật soạn sẵn
- Sau khi có câu trả lời: chip đổi sang gợi ý động từ field suggested_followups trong response — câu hỏi liên quan tới Điều vừa được trích dẫn (ví dụ đang hỏi về Thẩm phán → chip gợi ý "Thư ký Tòa án có nhiệm vụ, quyền hạn gì?"), bấm vào tự điền/gửi câu hỏi đó

Ô nhập liệu:
- Bo tròn, placeholder "Hỏi về Luật Tố tụng Hình sự...", nút gửi hình mũi tên
- Dòng disclaimer nhỏ cố định dưới cùng: "TTHS Buddy · Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp" — giữ nguyên dòng này trong bản build thật, đây là chi tiết quan trọng về minh bạch cho sản phẩm liên quan luật.


2.5. Màn hình Trắc nghiệm (Quiz) — MỚI, bổ sung theo yêu cầu "5 bộ đề, user chọn bộ"

Luồng 2 bước, không vào thẳng câu hỏi:
- Bước 1 — Chọn bộ đề: hiển thị danh sách 5 bộ đề dạng card ("BỘ ĐỀ SỐ 01-05", mỗi bộ trộn chung MCQ 4 đáp án và câu Nhận định Đúng/Sai). Mỗi card hiển thị: tên bộ đề, tổng số câu, có thể kèm % điểm cao nhất đã đạt nếu đã làm trước đó (dữ liệu từ Phase 5a). Lấy danh sách qua GET /api/quiz/sets.
- Bước 2 — Làm bài: sau khi chọn 1 bộ đề, gọi GET /api/quiz/generate với quiz_set tương ứng, hiển thị lần lượt từng câu hoặc dạng danh sách cuộn (tùy độ dài bộ đề), có nút nộp bài ở cuối.
- Sau khi nộp: hiển thị điểm số, đáp án đúng/sai từng câu, có thể mở rộng xem giải thích (nếu ngân hàng đề có field giải thích) — style giống citation collapsible ở màn hình Chat để nhất quán toàn app.

3. Màn hình Dashboard (Tổng quan học tập)

Header: lời chào theo buổi ("Chào buổi sáng, [Tên]"), câu trạng thái ngắn về tiến độ hiện tại, nút "Hỏi trợ lý AI" nổi bật góc phải.

Hàng stat nhanh (3 thẻ ngang): dùng số liệu đơn giản, dễ tính từ dữ liệu đã log — ví dụ số bài trắc nghiệm đã làm, số Điều đã hỏi/học.

Card "Từ khoá hôm qua":
- Khớp đúng Phase 7 (GET /api/dashboard/keywords-yesterday) — danh sách chip số Điều + tên ngắn, lấy từ query log ngày hôm trước, bấm vào mở lại hội thoại liên quan
- Bản 05/09: giữ đúng như spec — chỉ hiển thị tĩnh khi load trang, không cần thêm logic gì phức tạp hơn

Card "Chủ đề cần ôn lại":
- Khớp Phase 7 (GET /api/dashboard/weak-topics) — rule đơn giản: điểm quiz < 50% hoặc bị hỏi lại nhiều lần
- ĐỐI CHIẾU SCOPE: mockup Figma hiển thị breakdown theo range Điều cụ thể (VD "Điều 109-122", "3 lần làm") và progress bar phần trăm chi tiết theo từng nhóm chủ đề. Đây là mức chi tiết CAO HƠN rule đơn giản đã chốt trong Phase 7.
  → Bản 05/09: rút gọn còn tên chủ đề + % điểm quiz gần nhất + nút "Ôn tập", KHÔNG cần range Điều chi tiết hay đếm "số lần" nếu không có thời gian build category-tagging cho câu hỏi quiz.
  → Nếu Phase 5 (quiz) có thời gian gắn category/chương cho mỗi câu hỏi ngay từ đầu, giữ được mức chi tiết này mà không tốn thêm effort về sau — ưu tiên quyết định lúc thiết kế schema quiz.

Card "Tiến độ trắc nghiệm":
- ĐỐI CHIẾU SCOPE: mockup có breakdown theo 4 nhóm chủ đề (Nguyên tắc cơ bản, Biện pháp ngăn chặn, Điều tra vụ án, Truy tố & Xét xử) + circular progress tổng.
  → Bản 05/09: nếu quiz không có category, rút gọn card này thành 1 số duy nhất (điểm trung bình tổng) + tổng số bài đã làm, bỏ breakdown theo nhóm.

Card "Gợi ý học tập hôm nay" — KHÔNG có trong bản 05/09 (đã bỏ hẳn, xem quyết định cuối cùng bên dưới):
- Mockup Figma có lý do cá nhân hóa theo ngữ cảnh (VD "liên quan Điều 157 bạn hỏi hôm qua") và nhãn độ khó (Mới/Gợi ý/Nâng cao) — mức chi tiết này chưa từng nằm trong scope Phase 7.
- Lúc build Phase 8 (trước khi có dữ liệu thật), card này tạm được dựng bằng 1 helper mock-only (getRelatedArticles) tách biệt hoàn toàn khỏi 3 route thật của Phase 7 (keywords-yesterday/weak-topics/stats) — không map với route backend nào.
- Quyết định cuối cùng (lúc dọn dẹp sau Phase 7): BỎ HẲN card này khỏi dashboard, không xây route mới để thay thế — card "Chủ đề cần ôn lại" (weak-topics) đã đủ đóng vai trò gợi ý nội dung cần học/ôn lại cho bản 05/09. Xem requirements.md Mục 9 (Ngoài phạm vi) nếu muốn tách riêng lại ở v2.

Streak "X ngày học liên tiếp":
- KHÔNG có trong scope Phase 7 hiện tại — cần thêm bảng tracking hoạt động theo ngày nếu muốn giữ.
  → Bản 05/09: BỎ chi tiết này khỏi bản build thật, hoặc để version tĩnh/giả lập nếu chỉ cần cho demo trực quan (ghi rõ trong code là mock data, không tính rule thật).


4. Component dùng chung
- Pill/badge: bo tròn đầy đủ (rounded-full), padding ngang rộng hơn dọc, dùng cho citation tag, suggested question chip, category label
- Card: nền be ấm nhạt (`bg-card`, không phải trắng tinh), border mỏng, bo góc rounded-lg, padding đồng nhất, không dùng shadow nặng
- Progress bar: bo tròn, màu theo ngưỡng — navy/primary khi tốt (≥75%), amber-400 khi trung bình (50-74%), red-400 khi cần chú ý (dưới 50%) — 2 mốc dưới luôn hardcode Tailwind, không đổi theo re-theme
- Nút hành động phụ (VD "Ôn tập ngay"): outline hoặc nền nhạt, không cạnh tranh thị giác với nút hành động chính (VD "Hỏi trợ lý AI")


5. Nguyên tắc khi build (cho Claude Code)
- Luôn build UI dựa trên field thật mà backend trả về (theo đúng response shape trong requirements.md Phase 4/5/6/7) — không tự thêm field hiển thị mà backend chưa có.
- Nếu 1 chi tiết trong file này đánh dấu "ĐỐI CHIẾU SCOPE" hoặc "rút gọn", ưu tiên bản rút gọn cho deadline 05/09, trừ khi được yêu cầu rõ ràng làm bản đầy đủ.
- Không hardcode dữ liệu mẫu tĩnh vào production code trừ khi được đánh dấu rõ là mock/demo data tạm thời.