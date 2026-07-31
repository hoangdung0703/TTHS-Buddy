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

1.5. Mở rộng âm hưởng editorial sang UI chức năng (bổ sung 31/07/2026)

Bối cảnh: bản đồng bộ token màu (mục 1 ở trên) chỉ thống nhất MÀU SẮC giữa Welcome/Sign-in/Sign-up và toàn app. Các thành phần thị giác khác của ngôn ngữ editorial (typeface pairing, hình khối nút/card, texture nền) ban đầu chỉ áp dụng ở 3 trang landing/auth, dùng component `card.tsx`/`button.tsx` mặc định kiểu shadcn thuần (rounded-md/rounded-lg, border rõ). Bản mở rộng này lan tỏa các yếu tố còn lại sang Sidebar/TopBar/Dashboard/Chat/Quiz/Essay, có cân nhắc mật độ thông tin — không áp y hệt Welcome vào mọi nơi.

Quy tắc Card (component dùng chung, `components/ui/card.tsx`):
- Default đã đổi thành `rounded-xl`, border cực mảnh `border-primary/[0.08]` (thay vì `border-border` rõ), kèm shadow mềm `shadow-[0_2px_20px_rgba(30,36,96,0.05)]` thay vì không có shadow.
- Đây là default MỚI của chính component — mọi nơi dùng `<Card>` (Dashboard, Quiz, Essay) tự động ăn theo, không cần sửa từng trang. Khi thêm trang/feature mới dùng `<Card>`, không cần override thêm gì trừ khi có lý do đặc biệt.
- Đã kiểm chứng bằng ảnh chụp: card xếp chồng nhiều lần liên tiếp (Quiz nhiều câu hỏi/màn hình) vẫn tách bạch rõ nhờ shadow + khoảng cách `space-y`/`gap`, không bị "loãng" dù border mờ hơn trước.

Quy tắc hình dạng nút (Button, `components/ui/button.tsx`) — KHÔNG đổi default toàn cục:
- Default của `<Button>` GIỮ NGUYÊN `rounded-md` — không đổi sang pill toàn cục, vì phần lớn nút trong Quiz/Essay/Dashboard là nút nhỏ lặp lại nhiều lần (đáp án, "Thử lại", "Ôn tập", "Câu hỏi tiếp theo") — pill hoá hàng loạt sẽ rối mắt hơn là editorial.
- Pill (`rounded-full`) chỉ áp qua `className` cho các CTA chính, xuất hiện đúng 1 lần trên màn hình đó: nút "Hội thoại mới" (Sidebar), "Hỏi trợ lý AI" (Dashboard), "Nộp bài" (Quiz + Essay). Ô nhập chat và nút gửi trong Chat vốn đã là pill từ trước, không cần đổi.
- Khi thêm CTA chính mới (1 nút nổi bật/màn hình, hành động trọng tâm): thêm `className="rounded-full"`. Khi thêm nút phụ/lặp lại nhiều lần: để nguyên default `rounded-md`, không tự ý pill hoá.

Quy tắc serif — MẬT ĐỘ-AWARE (density-aware), đây là quy tắc dễ áp sai nhất, đọc kỹ trước khi thêm heading mới:
- ĐƯỢC dùng `font-serif`: brand mark (logo Sidebar — `font-light`, dùng làm mốc "nhẹ nhất"), tiêu đề trang trong TopBar (`font-normal` — cố ý đậm hơn logo Sidebar 1 nấc để 2 chữ serif nằm sát nhau ở cùng vùng đầu trang không bị đọc thành cặp song sinh trùng lặp), heading chào mừng + `CardTitle` ở Dashboard (`font-light`, vì đây là heading xuất hiện ĐÚNG 1 LẦN/màn hình), heading phụ in đậm bên trong câu trả lời Chat dài (`FormattedAnswer.tsx`, `font-medium` — đậm hơn heading điều hướng vì đây là heading NỘI DUNG cần nổi bật giữa văn bản sans dài, không phải chrome UI).
- TUYỆT ĐỐI KHÔNG dùng serif trong: nội dung câu hỏi/đáp án Quiz (kể cả nhãn "Câu 1", "Câu 2"... dù về mặt kỹ thuật đó cũng là `CardTitle`), nội dung câu hỏi/rubric/textarea Essay, `CardTitle` của các card kết quả Essay ("Ý đã trả lời đúng", "Ý còn thiếu / sai", "Nhận xét"), nội dung bong bóng chat (cả user và AI, trừ heading phụ nói trên). Lý do: đây đều là nhãn/nội dung LẶP LẠI NHIỀU LẦN trên cùng 1 màn hình hoặc cần quét nhanh khi làm bài có giới hạn — serif (đặc biệt font-light) làm chậm tốc độ đọc hơn sans, chỉ chấp nhận được cho heading xuất hiện 1 lần.
- Quy tắc rút gọn khi thêm UI mới: heading/nhãn xuất hiện ĐÚNG 1 LẦN trên màn hình → cân nhắc serif. Heading/nhãn LẶP LẠI (item trong danh sách, câu hỏi trong bộ đề, mỗi tin nhắn chat) → luôn sans.

Quy tắc gradient wash nền (background texture):
- Bản gốc trên Welcome/Sign-in/Sign-up (`components/brand/BackgroundOrbs.tsx`) dùng `position: fixed`, không bị ancestor nào clip — dùng được nguyên bản cho các trang không có sidebar/topbar.
- Trang có Sidebar/TopBar (Dashboard) KHÔNG dùng `fixed` + component đó — phải tự khai báo 2 div `absolute` trong 1 wrapper `relative isolate` (bắt buộc có `isolate`, xem lưu ý kỹ thuật bên dưới), định vị bằng `top-0`/`right-0`/`bottom-0`/`left-0` (KHÔNG dùng offset âm lớn kiểu `-top-40 -right-32` nếu wrapper có `overflow-hidden` — sẽ bị clip mất hoàn toàn, xem lưu ý kỹ thuật).
- Cường độ chuẩn đã đo bằng pixel thật (không chỉ ước lượng opacity trong code): tại tâm hình tròn của orb gốc trên Welcome, delta so với nền là **~25 điểm RGB** (đo bằng `page.screenshot()` + đọc pixel qua `pngjs`, không phải nhìn mắt trên ảnh nén). Giá trị rgba dùng ở Dashboard (`rgba(30,36,96,0.17)` cho navy, `rgba(184,154,82,0.14)` cho gold, blur 64px/56px, kích thước 420px/360px) cho delta thực đo **~28 điểm RGB** — coi đây là mức chuẩn tham chiếu khi thêm gradient wash ở trang chức năng khác, KHÔNG suy luận độ đậm chỉ bằng cách đọc số opacity trong code (blur + gradient "transparent 70%" làm giảm alpha hiệu dụng rất nhiều so với con số danh nghĩa, xem lưu ý kỹ thuật).
- Trang có mật độ đọc/thao tác cao (Quiz, Essay) và Chat (cuộn nội dung dài liên tục) — KHÔNG dùng gradient wash, giữ nền phẳng theo token màu. Chỉ Dashboard (nội dung ngắn, không cần tập trung cao) mới có wash.
- **Lưu ý kỹ thuật quan trọng (đã tốn nhiều vòng debug để phát hiện, đọc kỹ trước khi tái tạo hiệu ứng này ở trang khác):**
  1. Wrapper chứa orb phải có class `isolate` (tạo stacking context cục bộ). Thiếu `isolate`, `-z-10` của orb sẽ bubble lên tận root stacking context, và `<body>`'s `bg-background` (solid) sẽ vẽ đè lên trên orb ở MỌI nơi trên trang — orb render đúng, đúng màu, đúng vị trí trong DOM, nhưng hoàn toàn vô hình, kể cả ở opacity rất cao. Đây không phải lỗi "mờ quá", mà là lỗi paint-order — dễ nhầm là "chỉnh opacity chưa đủ" và chỉnh sai hướng.
  2. Wrapper KHÔNG được set `overflow-hidden` nếu orb định vị bằng offset âm lớn (kiểu `-top-40`) — phần orb nằm ngoài biên wrapper sẽ bị cắt mất hoàn toàn trước khi tính tới opacity. Định vị bằng `top-0`/`right-0` (nằm trong biên) là cách an toàn hơn nếu vẫn muốn giữ `overflow-hidden`.
  3. Tâm hình tròn thật sự nằm ở GIỮA bounding box (`top`/`right` + width/2, không phải ở góc `top-0 right-0` như đọc code tưởng) — khi đo/kiểm tra bằng mắt hoặc bằng pixel, phải tính đúng toạ độ tâm mới đánh giá đúng độ đậm, nếu không sẽ đo nhầm vào vùng rìa gần-trong-suốt của gradient và kết luận sai là "vô hình".

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
- Card: nền be ấm nhạt (`bg-card`, không phải trắng tinh), border cực mảnh (`border-primary/[0.08]`), bo góc `rounded-xl`, shadow mềm, padding đồng nhất — đây là default hiện tại của `components/ui/card.tsx` (đã đổi từ `rounded-lg`/border rõ/không shadow, xem mục 1.5 để biết lý do và cách kiểm chứng)
- Progress bar: bo tròn, màu theo ngưỡng — navy/primary khi tốt (≥75%), amber-400 khi trung bình (50-74%), red-400 khi cần chú ý (dưới 50%) — 2 mốc dưới luôn hardcode Tailwind, không đổi theo re-theme
- Nút hành động phụ (VD "Ôn tập ngay"): outline hoặc nền nhạt, `rounded-md` (default), không cạnh tranh thị giác với nút hành động chính (VD "Hỏi trợ lý AI", luôn `rounded-full` qua `className` — xem quy tắc pill chọn lọc ở mục 1.5)


5. Nguyên tắc khi build (cho Claude Code)
- Luôn build UI dựa trên field thật mà backend trả về (theo đúng response shape trong requirements.md Phase 4/5/6/7) — không tự thêm field hiển thị mà backend chưa có.
- Nếu 1 chi tiết trong file này đánh dấu "ĐỐI CHIẾU SCOPE" hoặc "rút gọn", ưu tiên bản rút gọn cho deadline 05/09, trừ khi được yêu cầu rõ ràng làm bản đầy đủ.
- Không hardcode dữ liệu mẫu tĩnh vào production code trừ khi được đánh dấu rõ là mock/demo data tạm thời.