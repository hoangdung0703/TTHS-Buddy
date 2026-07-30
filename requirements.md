TTHS Buddy — Trợ lý AI học tập Luật Tố tụng Hình sự
File ngữ cảnh gốc — đọc trước khi thực hiện bất kỳ tác vụ nào.

1. Thông tin dự án
Tên: TTHS Buddy — Trợ lý AI học tập Luật Tố tụng Hình sự (Bộ luật Tố tụng Hình sự 2015)
Mục đích: Chatbot ứng dụng RAG (Retrieval-Augmented Generation) giúp sinh viên luật học tập Luật Tố tụng Hình sự. Người dùng đặt câu hỏi về luật (điều luật, quy trình, tình huống) và nhận câu trả lời có căn cứ, luôn kèm trích dẫn Điều/Khoản cụ thể, chỉ dựa trên nguồn dữ liệu pháp luật đã nạp vào hệ thống. Bao gồm module trắc nghiệm (MCQ), module tự luận (câu hỏi mở, hệ thống chấm và chỉ ra lỗi sai dựa trên rubric), và dashboard học tập cá nhân. Đây là dự án NCKH cấp trường, hướng tới đăng bài báo — độ chính xác, tính có căn cứ (groundedness) và khả năng đo lường quan trọng ngang với trải nghiệm người dùng.
Deadline: Hạn chót cứng 05/09/2026. Xây dựng đúng thứ tự các Phase bên dưới, cắt scope trước khi cắt deadline.
Đối tượng người dùng:

Sinh viên (chỉ 1 vai trò): Đăng ký, đăng nhập, hỏi đáp qua chat, làm trắc nghiệm, xem dashboard cá nhân.
Không cần trang quản trị (admin panel) cho deadline này — việc nạp văn bản luật do developer chạy qua CLI/script, không qua giao diện.


2. Tech Stack
Layer | Công nghệ
Frontend Runtime | Node.js (v20+)
Frontend Framework | Next.js (App Router, TypeScript)
Styling | Tailwind CSS + shadcn/ui
Backend Runtime | Python 3.11+
Backend Framework | FastAPI
Relational DB + Auth | Supabase (Postgres + Supabase Auth, email/password)
Vector Database | Qdrant Cloud (free tier)
LLM | Google Gemini API — model cấu hình qua biến môi trường, mặc định gemini-3.1-flash-lite (đổi sang gemini-3.6-flash cho ngày demo nếu cần)
Embeddings | Google gemini-embedding-001 qua REST API
Xử lý văn bản luật | pdfplumber (trích xuất text từ PDF) + bộ tách Điều/Khoản/Điểm bằng regex tự viết
Backend Package Manager | uv hoặc pip + requirements.txt
Frontend Package Manager | npm
API Style | RESTful


3. Kiến trúc thư mục
frontend/                          # Next.js app
  src/
    app/                           # App Router pages (chat, quiz, essay, dashboard, login)
    components/
    lib/
      supabaseClient.ts
      api.ts                       # centralized fetch wrappers gọi backend
    hooks/

backend/                           # FastAPI app
  app/
    api/                           # route modules: chat, quiz, dashboard, health
    core/
      config.py                    # validate env (pydantic-settings)
      security.py                  # verify Supabase JWT
    services/
      rag_service.py               # retrieval + build prompt + gọi LLM
      embedding_service.py         # embed text qua Gemini API
      vector_store_service.py      # adapter cho Qdrant
      quiz_service.py              # sinh + validate trắc nghiệm (MCQ)
      essay_service.py             # chấm câu trả lời tự luận theo rubric (LLM-as-judge) + phản hồi lỗi sai
      question_bank_service.py     # chọn câu hỏi luân phiên (tránh trùng lặp gần đây, cân bằng chủ đề) dùng chung cho MCQ và tự luận
      dashboard_service.py         # lịch sử từ khóa, phát hiện chủ đề yếu
    models/                        # Pydantic schemas
    main.py

ingestion/                         # Script CLI, chạy độc lập / chạy lại được
  parse_law.py                     # PDF BLTTHS -> chunks có cấu trúc Điều/Khoản/Điểm (JSON)
  embed_and_upsert.py              # chunks.json -> Qdrant

.env
requirements.md                    # File này


4. Nguyên tắc kiến trúc (Quy tắc bắt buộc)
Các quy tắc dưới đây không được thay đổi.

Không viết logic dồn hết vào controller/route. Business logic nằm trong services/, các route API chỉ xử lý request/response và gọi service.
Chỉ dùng biến môi trường. Không hardcode API key hay secret ở bất kỳ đâu. Mọi secret qua .env, được validate lúc khởi động trong core/config.py.
RAG grounding là bắt buộc. LLM chỉ được trả lời dựa trên context đã retrieve (văn bản luật + tài liệu hỗ trợ). System prompt phải cấm rõ ràng việc dùng kiến thức nội tại (parametric knowledge) của model. Nếu retrieval không tìm được chunk phù hợp vượt ngưỡng similarity, trả lời bằng thông báo fallback rõ ràng "không tìm thấy trong dữ liệu pháp luật" — tuyệt đối không tự bịa trích dẫn.
Mọi nội dung pháp lý phải có trích dẫn Điều/Khoản. Bất kỳ câu trả lời nào đề cập nội dung luật đều phải kèm Điều/Khoản cụ thể làm nguồn. Câu trả lời không có chunk nguồn tương ứng thì không được khẳng định nội dung pháp lý.
Phân biệt rõ nguồn pháp lý chính thức và nguồn tham khảo học thuật. Corpus gồm cả văn bản luật (source_type = legal_text, có giá trị pháp lý bắt buộc) và tài liệu học thuật như giáo trình/bài báo (source_type = academic_reference, chỉ mang tính tham khảo/phân tích). System prompt và phần hiển thị citation phải nêu rõ loại nguồn — không để câu trả lời trình bày ý kiến học thuật ngang hàng hoặc lẫn lộn với quy định pháp luật bắt buộc.
Chiến lược chunking: tách BLTTHS và văn bản liên quan theo từng Điều, không tách theo số token cố định. Mỗi chunk = một Điều (hoặc một Khoản nếu Điều đó quá dài). Không dùng RecursiveCharacterTextSplitter cho văn bản luật — phải giữ nguyên cấu trúc pháp lý.
Metadata cho vector. Mỗi chunk khi embed phải lưu: source_document, dieu_number, dieu_title, khoan_number (có thể null), law_version, chunk_text.
Auth cho mọi route không public. Mọi route /api trừ /health và /auth/* đều yêu cầu Supabase JWT hợp lệ trong header Authorization: Bearer <token>, được verify ở phía server.
Xử lý lỗi tập trung. Mọi lỗi trả về theo 1 format JSON thống nhất — không để lộ raw stack trace hay thông báo lỗi nội bộ ra client.
CORS. Giới hạn ở http://localhost:3000 trong môi trường development.
Type safety. Frontend: TypeScript strict mode, không dùng any. Backend: Pydantic models cho mọi request/response, type hint cho mọi function.
Không được "chữa cháy" bằng cách để model tự đoán. Không bao giờ để LLM tự "điền" một số điều luật nghe có vẻ hợp lý nếu nó không có trong context được cung cấp.


5. Deliverables & Thứ tự triển khai
Thực hiện đúng thứ tự Phase. Không bắt đầu Phase sau khi Phase hiện tại chưa được verify. Thứ tự này phản ánh scope MVP đã cắt gọn cho deadline 05/09/2026 — các tính năng đánh dấu (v2) nằm ngoài scope của bản build này (xem Mục 9).

GHI CHÚ NGOẠI LỆ VỀ THỨ TỰ: Phase 8 (Frontend) đã được build sớm hơn thứ tự gốc (hoàn thành trước Phase 3), chạy song song trong lúc chờ nhóm sinh viên luật cung cấp văn bản BLTTHS cho Phase 3. Toggle qua NEXT_PUBLIC_USE_MOCK_DATA trong frontend/.env.local, logic mock tập trung tại lib/api.ts + lib/mockData.ts. Khi Phase 3-7 hoàn thành với dữ liệu thật, chỉ cần đổi NEXT_PUBLIC_USE_MOCK_DATA=false, không cần sửa lại component. LƯU Ý: Phase 8 dùng tạm 2 helper mock-only không map với route nào trong 8 route gốc — getDashboardStats và getRelatedArticles (xem lib/types.ts/api.ts, có comment đánh dấu non-canonical). Đã bổ sung route/field thật để thay thế 2 helper này: related_articles giờ là field trong response của POST /api/chat/query (Phase 4), và GET /api/dashboard/stats mới (Phase 7).
CẬP NHẬT (lúc làm Phase 7): getDashboardStats đã được thay bằng gọi GET /api/dashboard/stats thật, không còn tồn tại helper mock-only này trong lib/api.ts nữa (xem chi tiết ở note cuối Phase 7 bên dưới).
CẬP NHẬT (quyết định dọn dẹp cuối cùng sau Phase 7): getRelatedArticles ("Gợi ý học tập hôm nay" trên dashboard) đã bị XÓA HẲN khỏi codebase (lib/api.ts, lib/types.ts, lib/mockData.ts) thay vì thêm route mới để thay thế — card này bị bỏ khỏi dashboard vì không nằm trong danh sách route Phase 7 (chỉ có keywords-yesterday/weak-topics/stats) và card "Chủ đề cần ôn lại" (weak-topics) đã đủ đóng vai trò gợi ý nội dung cần ôn cho bản 05/09 (xem Mục 9 — Ngoài phạm vi). Đến đây, KHÔNG còn helper mock-only nào (getDashboardStats, getRelatedArticles) tồn tại trong codebase — điều kiện cuối cùng để Phase 8 được coi là "đã xong" theo Định nghĩa hoàn thành ở Mục 8 nay đã thỏa.

Phase 1 — Scaffold dự án
[ ] Khởi tạo repo: frontend/ (Next.js + TS + Tailwind + shadcn/ui) và backend/ (FastAPI) trong 1 root
[ ] Setup .env với đầy đủ key cần thiết (kèm .env.example)
[ ] Kết nối Supabase (Postgres client + Auth), xử lý lỗi kết nối
[ ] Kết nối Qdrant client, tạo collection nếu chưa có
[ ] FastAPI app cơ bản với route health check GET /api/health
[ ] CORS, error middleware thống nhất đã setup xong

Phase 2 — Hệ thống Auth
[ ] Supabase Auth: đăng ký/đăng nhập bằng email/password, tích hợp ở frontend
[ ] Backend middleware: verify Supabase JWT, gắn vào request.user
[ ] Smoke test route bảo vệ: token hợp lệ thì pass, token thiếu/sai trả về 401

Phase 3 — Pipeline nạp văn bản luật (CLI, không qua API)
Nguồn dữ liệu thật: 12 file PDF, tổng ~1256 trang, gồm 2 nhóm cấu trúc khác nhau — cần dispatch theo source_type, không dùng 1 parser đơn cho tất cả:
  - legal_text (có cấu trúc Điều/Khoản/Điểm rõ ràng): Bộ luật TTHS, văn bản hợp nhất BLHS, Nghị định 250, Thông tư liên tịch
  - academic_reference (văn xuôi, không có cấu trúc Điều): giáo trình Luật TTHS, bài báo khoa học, tài liệu "nguồn bào chữa trong LTTHS"

[ ] parse_law.py — nhận vào 1 file, tự nhận diện hoặc nhận tham số source_type, dispatch sang đúng chiến lược tách chunk:
    - Chiến lược legal_text: tách theo Điều (giữ nguyên logic gốc — regex theo "Điều X.", không dùng fixed-token splitter)
    - Chiến lược academic_reference: tách theo heading/section/đoạn (dùng thư viện parse cấu trúc PDF hoặc heuristic theo font-size/heading pattern), chunk size linh hoạt theo đoạn văn hoàn chỉnh, không cắt giữa câu
[ ] Metadata mở rộng: mọi chunk (cả 2 loại) đều có thêm field source_type (legal_text | academic_reference) và source_document (tên file gốc) — dùng để phân biệt rõ trong prompt RAG và trong UI citation (tránh lẫn ý kiến học thuật với quy định pháp luật bắt buộc)
[ ] BƯỚC TEST BẮT BUỘC trước khi chạy full batch: chọn 1 file đại diện cho legal_text (ví dụ Bộ luật TTHS) và 1 file đại diện cho academic_reference (ví dụ 1 bài báo hoặc chương giáo trình ngắn nhất), chạy parser, kiểm tra thủ công chất lượng chunk (không cắt giữa câu/Điều, không lẫn header/footer lặp lại, text extract sạch không lỗi ký tự) trước khi áp dụng cho toàn bộ 12 file
[ ] Sau khi test pass, chạy full batch cho cả 12 file trong 1 lần, output ra JSON có cấu trúc thống nhất bất kể source_type
[ ] Kiểm tra thủ công: verify ít nhất 10 chunk ngẫu nhiên cho MỖI loại source_type (không chỉ 10 chunk tổng) — vì 2 loại có tiêu chí "đúng" khác nhau
[ ] embed_and_upsert.py — embed từng chunk qua Gemini embedding API, upsert vào Qdrant kèm đầy đủ metadata (bao gồm source_type mới)
[ ] Re-runnable: script có thể chạy lại an toàn nếu nguồn cập nhật (idempotent upsert theo dieu_number + law_version cho legal_text, theo source_document + chunk_index cho academic_reference)
[ ] OCR fallback (bắt buộc, không được bỏ sót tài liệu): với file/trang mà text-layer extraction thất bại hoặc cho ra kết quả rác (0 ký tự trích được, hoặc heuristic phát hiện tỷ lệ ký tự không hợp lệ/không giống tiếng Việt chuẩn cao bất thường), render trang đó thành ảnh và gửi qua Gemini Vision API (dùng lại GOOGLE_API_KEY, GEMINI_CHAT_MODEL đã có — KHÔNG thêm thư viện OCR mới như pytesseract vào tech stack) để trích xuất text. Áp dụng cho cả 2 trường hợp: PDF scan ảnh thuần (0 ký tự) và PDF có text-layer nhưng lỗi CMap font (text rác). Chunk kết quả OCR có thêm metadata extraction_method: "ocr_fallback" để phân biệt với extraction_method: "text_layer" — dùng để spot-check chất lượng riêng và để loại trừ nếu phát hiện lỗi OCR nghiêm trọng sau này.
[ ] Xử lý RECITATION filter (Gemini Vision có thể chặn OCR trên trang trùng nội dung xuất bản/bản quyền, trả finishReason: RECITATION): KHÔNG cố né bộ lọc bằng cách đổi prompt/temperature/retry liên tục — đây là chặn cứng theo nội dung. Khi gặp, fallback về text-layer gốc của chính trang đó, đánh dấu extraction_method: "text_layer_fallback_after_ocr_blocked". Nếu text-layer gốc của trang đó cũng là rác (trường hợp file vốn đã lỗi CMap toàn bộ như giáo trình), vẫn giữ chunk với metadata extraction_quality: "unusable" để có thể lọc ra xử lý thủ công riêng sau (không dừng batch, không bỏ sót record dù chất lượng kém).
[ ] Tầng fallback thứ 2 cho chunk "unusable" — Tesseract OCR (chỉ áp dụng có mục tiêu, KHÔNG chạy lại toàn batch): với riêng các trang đã rơi vào extraction_quality "unusable" sau Gemini Vision (do RECITATION block hoặc lỗi khác), thử thêm Tesseract (pytesseract + gói ngôn ngữ vie) làm tầng OCR cuối — vì Tesseract không áp content/copyright policy nên không bị chặn theo nội dung như Gemini Vision. Đây là ngoại lệ có chủ đích với nguyên tắc "tech stack gọn" ban đầu, chỉ vì Gemini Vision không giải quyết được nhóm lỗi RECITATION. Chunk nào Tesseract đọc được, cập nhật extraction_method: "tesseract_fallback", extraction_quality: "ok" hoặc "degraded" tùy chất lượng đọc thực tế (Tesseract tiếng Việt có dấu thường kém chính xác hơn Gemini Vision, cần spot-check kỹ hơn). Chunk vẫn không đọc được sau cả 2 tầng OCR thì giữ nguyên "unusable", để dành cho phương án bổ sung thủ công (gõ tay) nếu nhóm xác định đó là nội dung quan trọng.
[ ] Áp dụng OCR fallback nhất quán cho MỌI file cần đến nó (bao gồm cả file lỗi nhẹ như "Bảo vệ quyền con người bằng TTHS") — không đặc cách bỏ qua OCR cho file có lỗi nhẹ nếu OCR cho chất lượng tốt hơn text-layer gốc, để giữ 1 cơ chế xử lý thống nhất cho toàn corpus thay vì nhớ ngoại lệ riêng theo từng file.

Ghi chú chất lượng dữ liệu nguồn (phát hiện lúc chạy thật, giữ lại để tránh mất context nếu ingest lại sau này):
- Nếu 1 file legal_text là PDF scan ảnh thuần (0 ký tự trích xuất được): dùng OCR fallback qua Gemini Vision như mô tả ở trên — KHÔNG loại bỏ, KHÔNG cần thêm thư viện OCR mới.
- Nếu 1 file bị lỗi encoding font (text trích ra là ký tự rác): thử extract bằng thư viện khác (pypdfium2) trước; nếu vẫn rác, dùng OCR fallback qua Gemini Vision thay vì loại bỏ file — KHÔNG bao giờ ingest text rác vào corpus, nhưng cũng KHÔNG bỏ sót tài liệu nếu OCR fallback đọc được.
- File academic có layout nhiều cột: trích theo bounding-box/cột (dựa vào gutter gap giữa 2 cột theo từng dòng, không theo toàn trang) thay vì extract_text() mặc định, tránh xáo trộn thứ tự câu giữa các cột.
- Kết quả thực tế: Nghị định 250 và Thông tư liên tịch 01/2026 — đã thay bằng bản PDF chuẩn có text-layer sạch, không cần OCR. "Giáo trình Luật TTHS" (576 trang, lỗi CMap font nặng) — 278 trang cứu được qua Gemini Vision OCR, 297 trang còn lại (bị RECITATION filter chặn hoặc lỗi rate-limit) cứu thành công 100% qua tầng fallback thứ 2 (Tesseract). "Bảo vệ quyền con người bằng TTHS" (17 trang) — dùng OCR fallback, chất lượng tốt hơn text-layer gốc. Toàn bộ giáo trình cuối cùng đọc được, không còn phần nào unusable.
- RECITATION filter (Gemini Vision chặn nội dung trùng khớp tài liệu đã xuất bản): không cố né bằng đổi prompt/temperature — chấp nhận là giới hạn khách quan, dùng Tesseract làm tầng fallback thứ 2 cho các trang bị chặn, không cố lách filter bằng bất kỳ cách nào khác.

3 bug phát hiện trong lúc cross-check số lượng chunk trước khi upsert (đáng lưu ý — không lộ ra qua spot-check 10 chunk/loại ban đầu, chỉ phát hiện được nhờ đối chiếu tổng số point Qdrant với số chunk dự kiến):
1. Điều có hậu tố chữ cái (ví dụ "Điều 217a", "Điều 506a" — luật sửa đổi chèn thêm điều mới) bị regex cũ nuốt nhầm vào điều số gốc do chỉ khớp số, không khớp hậu tố chữ. Đã sửa regex để nhận diện đúng hậu tố.
2. Phần "PHỤ LỤC" trong Nghị định 250 chứa mẫu văn bản có cấu trúc giả "Điều 1, 2, 3, 4" bị regex bắt nhầm thành điều luật thật, gây nhân bản chunk. Đã thêm logic cắt bỏ nội dung sau heading "PHỤ LỤC".
3. Lỗi font khiến ký tự "Điều" bị biến dạng (mất dấu "ề"→"ê" thành "Điêu", hoặc dùng nhầm ký tự Latin "Ð" thay vì "Đ" tiếng Việt) khiến header không khớp regex, làm mất nội dung Điều liên quan (nuốt vào điều liền trước). Cần kiểm tra kỹ theo mã Unicode trực tiếp, không chỉ nhìn bằng mắt, vì 2 ký tự trông giống hệt nhau khi hiển thị.

Số liệu cuối cùng Phase 3 (dùng cho phần Methodology/Data Collection của bài báo):
- Tổng chunk trong chunks.json: 2588 (legal_text: 1395, academic_reference: 1193)
- extraction_quality "ok": 2587, "unusable": 1 (trang chữ ký/con dấu cuối Thông tư liên tịch 01/2026, không mang nội dung pháp lý)
- Đã embed + upsert vào Qdrant: 2586 (1 chunk mất do trùng lặp thật trong chính văn bản nguồn — BLHS Điều 189 Khoản 3, 2 đoạn gần giống hệt nhau trong file gốc, không phải lỗi parser)
- extraction_method breakdown: text_layer 1555, ocr_fallback 417, tesseract_fallback 613, mixed 3

Phase 4 — Pipeline RAG hỏi đáp (Tính năng lõi) — ĐÃ HOÀN THÀNH
[x] rag_service.py — với 1 câu hỏi của user: embed câu hỏi → similarity search Qdrant (top-k, cấu hình được) → build prompt có căn cứ → gọi Gemini → trả về câu trả lời + nguồn trích dẫn
[x] Nhận diện intent câu hỏi: nếu câu hỏi nêu rõ số Điều, ưu tiên match chính xác theo metadata (Qdrant scroll + filter theo dieu_number) thay vì chỉ semantic search
[x] POST /api/chat/query — nhận { question: string }, trả về { answer: string, citations: [{dieu_number, dieu_title, law_version}], related_articles: [{dieu_number, dieu_title}] }
[x] System prompt bắt buộc: chỉ trả lời từ context, luôn trích dẫn Điều/Khoản, có thông báo fallback rõ ràng khi context không đủ
[x] Log mọi câu hỏi + chunk đã retrieve + câu trả lời vào Postgres (bảng chat_query_logs)

Retrieval phân tầng thật đã áp dụng (bổ sung so với thiết kế gốc):
- Ưu tiên legal_text trước — exact-match theo dieu_number khi câu hỏi nêu rõ số Điều, sau đó mới đến semantic search.
- academic_reference chỉ được kéo vào khi câu hỏi mang tính phân tích (phát hiện qua từ khóa "phân tích/tại sao/ý nghĩa"...) hoặc khi legal_text không đủ điểm số liên quan.
- Câu trả lời có dùng academic_reference luôn tách rõ 2 phần "Về mặt quy định pháp luật" và "Về mặt học thuật", không trình bày ngang hàng.
- Citations/related_articles dedup theo (dieu_number, law_version) để không trùng khi 1 Điều bị tách nhiều Khoản.
- Khi model trả lời fallback (không tìm thấy), citations/related_articles bị ép về rỗng — tránh trường hợp gắn "nguồn" cho câu trả lời tự nhận là không có căn cứ (bug đã phát hiện và sửa lúc test).
- Payload index source_type và dieu_number đã tạo trên Qdrant collection (bắt buộc để filter hoạt động, thiếu sẽ lỗi 400).

Bug phát hiện lúc test end-to-end thật trên trình duyệt ở Phase 9 (trích dẫn chéo văn bản khi trùng số Điều): hỏi "Điều 13 Bộ luật Tố tụng hình sự quy định như thế nào về nguyên tắc suy đoán vô tội?" trả về citations gồm CẢ Điều 13 BLTTHS (đúng) LẪN Điều 13 Nghị định 250/NĐ-CP và Điều 13 Thông tư liên tịch 05 (hoàn toàn không liên quan - một cái về Hội đồng định giá tài sản, một cái về xử lý người bị tạm giam chết) - vì 5 văn bản legal_text đã ingest đều tự đánh số Điều từ 1, và `_retrieve_legal_exact()` chỉ filter theo `dieu_number` + `source_type=legal_text`, không giới hạn theo văn bản nào, nên mọi văn bản có cùng số Điều đều bị coi là "exact match" ngang nhau. Root cause fix: thêm `detect_source_document()` trong rag_service.py - nhận diện tên văn bản được nêu rõ trong câu hỏi (BLTTHS/BLHS/Nghị định 250/Thông tư liên tịch 05/01, qua `LAW_NAME_TO_SOURCE_DOCUMENT`) và truyền vào `_retrieve_legal_exact()` để lọc thêm theo đúng `source_document` đó. Trường hợp câu hỏi không nêu rõ văn bản nào thì giữ nguyên hành vi cũ (có thể trả về nhiều văn bản) - chưa xử lý, chấp nhận là giới hạn còn lại (xem thêm Mục 9). Verify: cùng câu hỏi test sau khi sửa chỉ còn trích Điều 13/15/26 của BLTTHS, không còn lẫn văn bản khác; đã chạy lại toàn bộ 29 câu ở backend/evaluation/test_set.json để xác nhận không có câu nào bị ảnh hưởng ngược (xem số liệu cập nhật ở Phase 9).
Giới hạn còn lại (chưa xử lý, ghi nhận as known issue): related_articles (gợi ý phụ, không phải trường trích dẫn chính) đôi khi vẫn lẫn Điều từ văn bản khác qua đường semantic search (không phải exact-match) khi các chunk có vector gần nhau một cách không mong muốn - ít nghiêm trọng hơn vì đây là field "gợi ý", không phải "căn cứ" như citations.

Việc cần làm thủ công khi setup lại từ đầu (dự án không dùng ORM/migration runner): chạy 1 lần file backend/migrations/0001_chat_query_logs.sql trong Supabase SQL Editor để tạo bảng chat_query_logs trước khi logging hoạt động — lỗi log bị catch nên không crash API nếu bảng chưa tồn tại, nhưng log sẽ không được ghi.

Phase 5a — Module trắc nghiệm (MCQ) — ĐÃ HOÀN THÀNH
Nguồn dữ liệu thật đã nhận từ nhóm luật: 2 file PDF —
  - "Câu hỏi trắc nghiệm.pdf": MCQ 4 đáp án, đã xác nhận đủ 5 bộ đề ("BỘ ĐỀ SỐ 01" đến 05, mỗi bộ ~15 câu). User chọn bộ đề muốn làm trên UI (xem frontend.md), không phải hệ thống tự trộn ngẫu nhiên toàn bộ ngân hàng.
  - "Tôi hỏi bạn trả lời.pdf": chứa 2 dạng câu hỏi khác nhau — (1) Nhận định Đúng/Sai (15 câu — câu khẳng định + đáp án Đúng/Sai + căn cứ pháp lý + giải thích, chấm khách quan), và (2) Tự luận mở (đáp án mẫu + "Từ khóa cho bài học" dạng bullet — nguồn cho Phase 5b)
  - Phân bổ Nhận định Đúng/Sai: KHÔNG tách thành bộ đề riêng — chia đều 15 câu vào 5 bộ MCQ hiện có, 3 câu/bộ (gán tuần tự: 3 câu đầu vào quiz_set 1, 3 câu tiếp vào quiz_set 2, v.v.), trộn chung với câu MCQ 4 đáp án trong cùng bộ. question_type vẫn phân biệt mcq_4choice vs mcq_true_false để UI render đúng số lượng lựa chọn, nhưng cùng thuộc 1 quiz_set, cùng 1 lượt làm bài.
  - Tin quan trọng: đáp án tự luận trong file gốc đã có sẵn "Từ khóa cho bài học" dạng bullet point (3-5 ý/câu) — gần như là essay_key_points có sẵn, CHỈ cần chuẩn hóa lại thành câu hoàn chỉnh (một số bullet quá cộc, ví dụ "Độc lập.", cần diễn giải đủ nghĩa), KHÔNG cần LLM tự phân rã từ đầu từ đoạn văn dài như kế hoạch ban đầu — giảm đáng kể rủi ro sai lệch ý.

[x] parse_question_bank.py (script CLI riêng trong ingestion/, tương tự tinh thần parse_law.py nhưng cho câu hỏi/đáp án):
    - Trích MCQ 4 đáp án từ "Câu hỏi trắc nghiệm.pdf", gắn field quiz_set (1-5) theo đúng "BỘ ĐỀ SỐ" chứa câu đó
    - Trích Nhận định Đúng/Sai từ "Tôi hỏi bạn trả lời.pdf", chuyển thành MCQ 2 lựa chọn (Đúng/Sai), phân bổ tuần tự 3 câu/quiz_set vào đúng 5 bộ đề đã có ở trên (không tạo quiz_set riêng)
    - Trích Tự luận mở từ cùng file, lấy đáp án mẫu (đoạn văn) VÀ bullet "Từ khóa cho bài học" có sẵn — chuẩn hóa bullet thành câu hoàn chỉnh (dùng LLM hỗ trợ diễn giải lại cho đủ nghĩa, KHÔNG tự bịa thêm ý ngoài bullet gốc) để tạo essay_key_points
    - topic_category: lấy từ heading/chương trong PDF nếu có tổ chức rõ ràng theo chủ đề; nếu không, suy luận từ dieu_number liên quan
    - Output: JSON theo schema (question_text, question_type: "mcq_4choice" | "mcq_true_false" | "essay", mcq_options, mcq_correct, essay_sample_answer, essay_key_points, dieu_number, topic_category, quiz_set — quiz_set chỉ áp dụng cho 2 loại mcq, tự luận không cần quiz_set vì Phase 5b không có khái niệm chọn bộ)
[x] BƯỚC KIỂM TRA BẮT BUỘC trước khi dùng cho Phase 5b: spot-check thủ công essay_key_points đã chuẩn hóa cho ít nhất 10-15 câu tự luận ngẫu nhiên, xác nhận không lệch ý so với bullet "Từ khóa cho bài học" gốc, trước khi coi ngân hàng đề là sẵn sàng dùng cho chấm điểm thật
[x] Ngân hàng đề sau khi qua parse + kiểm tra: dùng chung cấu trúc cho cả MCQ (Phase 5a, gồm cả mcq_4choice và mcq_true_false) và tự luận (Phase 5b), KHÔNG có nhiều bộ đề JSON tách rời không liên kết
[x] quiz_service.py — validate format câu hỏi MCQ (mcq_4choice: đúng 1 đáp án đúng trong 4 lựa chọn; mcq_true_false: đúng 1 đáp án Đúng/Sai). Nếu ngân hàng đề chưa đủ, có thể dùng LLM sinh thêm câu hỏi từ nội dung 1 Điều luật, nhưng ưu tiên câu hỏi do nhóm luật soạn sẵn trước
[x] question_bank_service.py — logic chọn câu hỏi luân phiên trong PHẠM VI 1 quiz_set đã chọn: không lặp lại câu user vừa làm trong N lượt gần nhất, cân bằng số câu giữa các topic_category trong bộ đề đó. Không luân phiên xuyên suốt toàn bộ ngân hàng vì user chủ động chọn bộ đề cụ thể
[x] POST /api/quiz/generate — nhận quiz_set (bắt buộc, 1-5) và filter chủ đề/Điều (tùy chọn), trả về bộ câu hỏi thuộc đúng quiz_set đó (gồm cả mcq_4choice và mcq_true_false trộn chung) đã qua logic luân phiên
[x] GET /api/quiz/sets — trả về danh sách 5 bộ đề MCQ kèm thông tin cơ bản (số câu, chủ đề chính) để hiển thị màn hình chọn bộ đề
[x] POST /api/quiz/submit — nhận đáp án, trả về điểm + đáp án đúng, lưu kết quả theo từng user kèm topic_category (để Phase 7 tính weak-topics theo đúng chủ đề, không chỉ theo Điều)

Field bổ sung ngoài schema tối thiểu ban đầu (có lý do, giữ lại):
- question_id: bắt buộc để POST /api/quiz/submit và POST /api/essay/submit (Phase 5b) tham chiếu đúng câu hỏi.
- explanation: giữ nguyên "Giải thích"/"Căn cứ pháp lý" gốc từ file nguồn — cần cho yêu cầu Phase 8 "làm bài, xem điểm + giải thích".

Kết quả thực tế: 90 câu ngân hàng đề (75 mcq_4choice + 15 mcq_true_false) → 18 câu/quiz_set × 5 bộ. Không implement fallback LLM sinh thêm câu hỏi vì ngân hàng đề đã đủ dùng.

Việc cần làm thủ công khi setup lại từ đầu (giống Phase 4): chạy 1 lần file backend/migrations/0002_quiz_attempts.sql trong Supabase SQL Editor để tạo bảng quiz_attempts trước khi rotation logic và lịch sử làm bài hoạt động đầy đủ — đọc/ghi tự động degrade an toàn (không crash API) nếu bảng chưa tồn tại, nhưng rotation sẽ luôn coi như "chưa có lịch sử" cho đến khi bảng được tạo.

Bug Phase 3 — lịch sử phát hiện và fix cuối cùng (title bị cắt cụt do wrap sang dòng 2/số trang dính vào title, dùng cho phần Methodology bài báo):
- Phát hiện lần 1 (lúc làm Phase 5a): 6 Điều trong Bộ luật TTHS.pdf (Điều 7, 135, 233, 243, 268, 382 — 10 chunk kể cả 5 Khoản của Điều 382) bị dính số trang vào cuối dieu_title/chunk_text. Sửa cơ học tạm thời bằng ingestion/fix_dieu_title_page_bleed.py (đã bị thay thế bởi root-cause fix bên dưới, không còn cần dùng script này nữa nhưng vẫn giữ lại trong repo để tham khảo lịch sử).
- Phát hiện lần 2 (lúc làm Phase 6, test suggested_followups với câu hỏi về Thẩm phán): phát hiện thêm Điều 41, 44 bị cắt cụt title GIỮA TỪ (không phải dính số trang ở cuối) — quét mở rộng phát hiện tổng cộng tới ~46 Điều trên 4 văn bản (Bộ luật TTHS, BLHS, Nghị định 250, Thông tư liên tịch 01/2026) bị cùng loại lỗi, phạm vi lớn hơn nhiều so với ước tính ban đầu.
- Root-cause fix cuối cùng (thay thế toàn bộ các lần vá tay ở trên): sửa `_merge_wrapped_title()` trong `ingestion/chunking.py` — thay vì đoán theo trigger-word (danh sách ~20 từ nối câu cố định, bỏ sót phần lớn case thực tế), dùng ranh giới thật của title:
  - Với Điều có cấu trúc Khoản: mọi văn bản giữa title (dòng 1) và marker Khoản đầu tiên ("1. ...") LUÔN LUÔN là phần title bị wrap, merge vô điều kiện (đã xác minh: không có Điều nào có cấu trúc Khoản mà lại có câu mở đầu trước Khoản 1 trong toàn bộ corpus) — trừ khi đoạn đó chứa dấu kết câu (. ! ? :), khi đó coi là câu dẫn nhập thật (ví dụ trước danh sách liệt kê Khoản) và KHÔNG merge.
  - Với Điều không có cấu trúc Khoản (đoạn văn ngắn, không tách Khoản): giữ nguyên logic trigger-word cũ (đã kiểm chứng an toàn) làm fallback, vì tín hiệu "dấu chấm câu đầu tiên" không phân biệt được continuation ngắn thật với câu nội dung ngắn thật (đã test và phát hiện false-positive cụ thể, xem test suite).
  - Số trang dính vào cuối dòng 1 của title (kiểu Điều 7) cũng được strip tự động ngay khi capture, không cần patch tay riêng từng Điều nữa.
  - 16 test case cụ thể (bao gồm case đã biết lỗi VÀ case dễ gây false-positive) được viết và pass 100% trước khi chạy lại batch thật.
- Kết quả sau khi chạy lại toàn bộ legal_text (chỉ re-parse text đã extract sẵn, KHÔNG chạy lại OCR/Gemini Vision — chỉ có 3 trang OCR fallback ngẫu nhiên không liên quan, ~4K token, không đáng kể):
  - Trước: 1395 chunk legal_text (bao gồm 23 chunk "intro" rác chỉ chứa mảnh title bị cắt, không mang nội dung pháp lý thật).
  - Sau: 1372 chunk legal_text (23 chunk rác trên biến mất vì phần continuation đã được merge đúng vào title, không còn "intro" thừa trước Khoản 1).
  - Số Điều có title bị cắt cụt thật sự (đã fix ở lần này): giảm từ ~46 Điều xuống còn 35 Điều ước tính (100% là các Điều KHÔNG có cấu trúc Khoản).
  - Đã re-embed + re-upsert toàn bộ 1372 chunk legal_text vào Qdrant, xóa 23 point mồ côi. Verify qua Phase 4 RAG với câu hỏi về Thẩm phán: citation Điều 44 và suggested_followups Điều 41 hiển thị title đầy đủ, chính xác.

TỔNG KẾT CUỐI CÙNG (dọn sạch toàn bộ phần còn sót — thay thế con số ước tính "35 Điều" ở trên bằng số liệu chính xác sau khi rà soát toàn bộ):
- Đã đọc thủ công TOÀN BỘ 152 Điều "không có cấu trúc Khoản và chưa được merge bởi logic cũ" trên cả 5 văn bản legal_text (quét bằng cách re-extract text gốc và chạy DIEU_PATTERN, không dựa vào ước tính) — con số thực tế sau khi phân loại từng Điều: 37 Điều thực sự bị cắt cụt title (31 BLTTHS, 5 BLHS, 1 Thông tư liên tịch 01/2026), 115 Điều còn lại đã có title hoàn chỉnh từ trước (không cần sửa).
- Đã thử mở rộng rule tổng quát (Khoản-aware) sang mọi Điều không phân biệt có/không có Khoản theo 2 hướng, CẢ HAI đều bị bác bỏ sau khi test cụ thể (không chỉ "có vẻ đúng"):
  1. "Merge đến dấu kết câu đầu tiên" (y hệt rule Khoản-aware): thất bại ngay ở Điều 15 ("Xác định sự thật của vụ án") — câu tiếp theo ("Trách nhiệm chứng minh tội phạm thuộc về cơ quan có thẩm quyền tiến hành tố tụng.") đủ ngắn để lọt qua mọi ngưỡng độ dài hợp lý, bị merge sai vào title.
  2. "Merge trừ khi câu tiếp theo chứa động từ độc lập" (là/có/được/thuộc/...): bắt được Điều 15 nhưng vẫn merge sai ở Điều 1, 24, 26, 96, 212, 216, 220, 306, 327, 366, 408, 455, 458, 468 — câu thật của các Điều này không chứa từ nào trong danh sách động từ đã thử trong phạm vi độ dài cho phép.
- Kết luận: KHÔNG dùng rule tổng quát cho phần còn lại này (rủi ro làm hỏng 115 title đang đúng, đã kiểm chứng cụ thể). Thay vào đó, dùng bảng tra cứu tường minh `KNOWN_NON_KHOAN_TITLE_CONTINUATIONS` trong `ingestion/chunking.py`, key theo (source_document, dieu_number) → đúng đoạn text tiếp nối lấy trực tiếp từ nguồn (đã đọc và xác minh tay từng Điều), so khớp bằng substring chính xác tại vị trí 0 (assert fail loudly nếu văn bản nguồn sau này bị trích xuất khác đi, thay vì âm thầm áp sai fix cũ). Vì corpus đã hữu hạn và được liệt kê đầy đủ, đây là lựa chọn an toàn hơn một rule tổng quát có rủi ro hồi quy.
- Đã viết 45 test case (37 case xác nhận đúng title sau merge + 8 case hồi quy xác nhận các Điều đã đúng từ trước — gồm cả 2 case đã làm rule tổng quát thất bại ở trên — không bị merge sai) và chạy pass 100% trước khi re-parse batch thật, cùng với 16 test case gốc từ lần fix trước (Khoản-aware) chạy lại xác nhận không hồi quy.
- Re-parse chỉ 3 văn bản bị ảnh hưởng (Bộ luật TTHS, BLHS, Thông tư liên tịch 01/2026 — Nghị định 250 và Thông tư liên tịch 05 không có case nào), không re-parse toàn bộ 5 văn bản vì chỉ cần thiết cho 3 văn bản này: số chunk trước/sau không đổi (1294 chunk mỗi bên), 0 point thêm/mất (không có chunk "intro" rác nào phát sinh hay biến mất lần này, khác với đợt fix Khoản-aware trước), đúng 37 chunk đổi dieu_title — khớp chính xác 100% với danh sách 37 Điều đã xác nhận, không có thay đổi ngoài dự kiến nào khác.
- Re-embed + re-upsert đúng 37 chunk bị ảnh hưởng vào Qdrant (không cần xóa orphan lần này).
- Quét lại TOÀN BỘ corpus lần cuối bằng logic mới (không chỉ kiểm tra lại 37 case cũ): xác nhận toàn bộ 115 Điều "không có cấu trúc Khoản" còn lại vẫn giữ nguyên title như trước (đã xác minh đúng), và không phát hiện thêm Điều nào khác bị cắt cụt ngoài 37 case đã sửa.
- Verify qua Phase 4 RAG với 3 Điều đại diện (Điều 12, 356 BLTTHS; Điều 41 BLHS): cả 3 đều trả về citation với title đầy đủ, chính xác, không còn dấu vết cắt cụt.
- Số liệu cuối cùng: 0 Điều còn bị cắt cụt title trong toàn bộ corpus đã ingest (tính đến thời điểm này) — đóng hẳn vấn đề title-truncation đã theo dõi xuyên suốt Phase 3/5a/6/9.

Phase 5b — Module tự luận (câu hỏi mở)
[ ] essay_service.py — nhận câu trả lời tự do (free-text) của user cho 1 câu hỏi trong ngân hàng đề, chấm điểm bằng LLM-as-judge dựa trên essay_key_points (rubric) đã có sẵn trong ngân hàng đề — KHÔNG để LLM tự đánh giá đúng/sai theo cảm tính, phải grounding vào rubric cụ thể
[ ] Prompt chấm điểm bắt buộc trả về theo cấu trúc: (1) các ý đã trả lời đúng, (2) các ý còn thiếu/sai so với essay_key_points, (3) gợi ý Điều/Khoản nên ôn lại
[ ] POST /api/essay/question — lấy 1 câu hỏi tự luận (qua question_bank_service, cùng logic luân phiên với 5a)
[ ] POST /api/essay/submit — nhận { question_id, user_answer: string }, trả về { matched_points: [], missing_points: [], feedback: string, suggested_dieu: [] }
[ ] Lưu lịch sử bài làm tự luận theo từng user (dùng cho Phase 7 weak-topics và Phase 9 evaluation)

Phase 6 — Gợi ý câu hỏi & chủ đề liên quan (cập nhật theo yêu cầu thực tế từ nhóm luật — gợi ý động theo câu hỏi vừa hỏi, không chỉ list tĩnh) — ĐÃ HOÀN THÀNH
[x] Trạng thái cold-start (chưa hỏi gì, mới vào trang chat): dùng danh sách câu hỏi/tình huống thường gặp do nhóm sinh viên luật cung cấp (dạng file JSON seed) — giữ nguyên thiết kế gốc cho trường hợp này. LƯU Ý: ingestion/chat_suggestions_seed.json hiện là PLACEHOLDER (6 câu mẫu tự soạn), chưa phải bản chính thức từ nhóm luật — TODO thay bằng file thật khi có, cùng path/schema {id, text}, không cần sửa code.
[x] GET /api/chat/suggestions — trả về danh sách soạn sẵn để hiển thị dạng chip bấm nhanh khi chưa có hội thoại nào
[x] Gợi ý động sau khi có câu trả lời: sau khi RAG trả lời và trích dẫn dieu_number chính, lấy vector đã lưu sẵn của chunk đó trong Qdrant (không embed lại), tìm top-3 chunk legal_text khác gần nhất (cùng source_document, loại trừ chính chunk đang xét và các dieu_number đã có trong citations), sinh câu hỏi gợi ý bằng template hóa từ dieu_title (không gọi LLM thêm — tiết kiệm chi phí/độ trễ mỗi lượt chat). Trả trong POST /api/chat/query: suggested_followups: [{dieu_number, suggested_question}]
[x] Giới hạn đã biết (accepted limitation, không phải bug): suggested_followups dùng vector similarity nên gợi ý liên quan về nội dung/chức năng (ví dụ cùng là "chức danh tố tụng") nhưng KHÔNG đảm bảo cùng Chương/Mục trong luật — test thực tế với câu hỏi về Thẩm phán (Điều 45) cho gợi ý Kiểm sát viên/Viện trưởng VKS (khác Chương) thay vì ưu tiên Thư ký Tòa án (cùng Chương) do văn phong "Nhiệm vụ, quyền hạn..." lặp khuôn mẫu gần giống nhau giữa các Chương khác nhau. Chấp nhận cho bản 05/09 vì gợi ý vẫn liên quan hợp lý về nội dung; có thể nâng cấp lên group theo Chương/Mục ở v2 nếu cần độ chính xác cấu trúc cao hơn (cần bổ sung metadata Chương/Mục, re-parse + re-embed).
[x] Liên kết chủ đề liên quan trong related_articles (Phase 4): giữ nguyên như đã có — 1-2 Điều liên quan retrieve cùng lượt tìm kiếm, không trộn lẫn với cơ chế suggested_followups mới (2 field khác mục đích: related_articles là nguồn phụ hỗ trợ câu trả lời hiện tại, suggested_followups là gợi ý cho câu hỏi TIẾP THEO)

Bug phát hiện lúc test Phase 6 (payload index thiếu + title truncation) — xem chi tiết ở ghi chú "Bug Phase 3" phía trên (Phase 5a). Tóm tắt riêng phần Phase 6: thiếu payload index cho source_document trên Qdrant gây lỗi 400 khi filter theo cùng source_document — đã sửa bằng cách tự động đảm bảo đủ 3 index (source_type, dieu_number, source_document) mỗi lần ensure_collection chạy (cả ingestion/vector_store.py và backend/app/core/config.py), không cần tạo tay nữa.

Phase 7 — Dashboard cá nhân (bản rút gọn cho 05/09, xem frontend.md để biết bản đầy đủ dành cho v2) — ĐÃ HOÀN THÀNH
[x] GET /api/dashboard/keywords-yesterday — query các câu hỏi user đã log trong ngày hôm trước, group theo dieu_number, trả về dạng danh sách (hiển thị tĩnh trên dashboard, không push notification)
[x] GET /api/dashboard/weak-topics — rule đơn giản: chủ đề (topic_category) có điểm trung bình (gộp cả MCQ và tự luận) < 50% hoặc bị hỏi lại/làm sai nhiều lần, hiển thị dạng "gợi ý ôn lại". KHÔNG cần breakdown chi tiết theo range Điều hay số lần làm, chỉ cần tên chủ đề + % điểm + nút ôn tập
[x] GET /api/dashboard/stats — trả về { total_quiz_attempts, average_score, dieu_studied_count } tính từ dữ liệu quiz/essay submissions đã lưu ở Phase 5a/5b — thay thế hẳn helper mock getDashboardStats đã dùng tạm ở Phase 8, tính 1 lần ở backend, không tính lại phía frontend
[x] Không làm: streak ngày học liên tiếp, circular progress breakdown theo 4+ nhóm chủ đề riêng biệt, gợi ý cá nhân hóa có lý do ngữ cảnh — các phần này để dành v2 (xem Mục 9)

Chi tiết triển khai:
- dashboard_service.py — 3 hàm đọc trực tiếp từ 3 bảng đã có sẵn (chat_query_logs, quiz_attempts, essay_attempts), không thêm bảng/log mới. keywords-yesterday: khung giờ "hôm qua" tính theo giờ VN (Asia/Ho_Chi_Minh, UTC+7, không có DST) rồi convert sang UTC để so sánh với timestamptz, tránh lệch ngày so với UTC. weak-topics: gộp điểm theo topic_category từ quiz_attempts.answers (đã có is_correct + topic_category per-question, lưu từ Phase 5a) và essay_attempts.matched_points/missing_points (đếm số ý đúng/tổng số ý), % = (quiz đúng + essay matched) / (quiz tổng + essay tổng ý) × 100, chỉ trả về chủ đề < 50%. stats: total_quiz_attempts đếm cả 2 bảng quiz_attempts + essay_attempts; average_score = trung bình % của từng lượt làm (quiz: score/total, essay: matched/(matched+missing)); dieu_studied_count = số dieu_number distinct trong citations của chat_query_logs.
- Đã dọn getDashboardStats trong frontend/src/lib/api.ts: gọi thật GET /api/dashboard/stats khi NEXT_PUBLIC_USE_MOCK_DATA=false, giữ nhánh mock khi bật cờ. Đồng bộ lại DashboardStats trong lib/types.ts (đổi field quizzes_completed/dieu_studied/conversations_count/average_quiz_score_percentage cũ sang đúng field thật total_quiz_attempts/average_score/dieu_studied_count từ response backend) và cập nhật lib/mockData.ts + app/dashboard/page.tsx theo field mới (3 quick-stat card + card "Tiến độ trắc nghiệm" dùng chung average_score/total_quiz_attempts).
- getKeywordsYesterday/getWeakTopics cũng đổi từ gọi trả mảng thẳng sang unwrap {keywords: [...]}/{weak_topics: [...]} cho khớp response shape thật (đồng bộ với cách GET /api/quiz/sets và GET /api/chat/suggestions đã làm ở các Phase trước — wrap list trong object thay vì trả mảng trần).
- Bug phát hiện lúc verify: lib/api.ts::apiFetch chưa từng gắn Authorization header (JWT) vào request thật — không riêng route Phase 7, toàn bộ route thật (chat/quiz/essay) trước giờ chỉ được test qua curl với token thủ công, chưa test qua chính frontend nên chưa lộ ra. Sửa bằng cách thêm getAuthHeader() lấy access_token từ session Supabase hiện tại (getSupabaseClient().auth.getSession()) và gắn vào mọi request trong apiFetch — sửa 1 chỗ, áp dụng chung cho toàn bộ route thật, không riêng Phase 7.
- Verify qua API thật (JWT thật, user test-ttths-phase4@example.com đã có dữ liệu từ Phase 4/5a/5b): làm 1 bài quiz_set 1 (10 câu, cố ý trả lời sai 1 nửa) qua POST /api/quiz/submit, nộp 1 câu tự luận lạc đề hoàn toàn qua POST /api/essay/submit (toàn bộ ý → missing, đúng hành vi đã verify ở Phase 5b) → GET /api/dashboard/stats trả {"total_quiz_attempts":2,"average_score":25,"dieu_studied_count":4} khớp tính tay (quiz 50% + essay 0%, trung bình 25%); GET /api/dashboard/weak-topics trả đúng 4 chủ đề có điểm 0% (gồm cả chủ đề từ câu quiz sai và chủ đề câu tự luận lạc đề). keywords-yesterday: chèn tạm 3 dòng chat_query_logs giả với created_at = hôm qua giờ VN (2 dòng cùng Điều 45, 1 dòng Điều 119) → API trả đúng group + count ({"dieu_number":"45",...,"count":2} và Điều 119 count 1) → đã xoá 3 dòng giả ngay sau khi verify xong, không để lại dữ liệu rác trong Postgres.
- Verify qua frontend thật (npm run dev, NEXT_PUBLIC_USE_MOCK_DATA=false tạm thời, dùng Playwright vì môi trường không có trình duyệt tương tác): đăng nhập bằng tài khoản test-ttths-phase4@example.com → /dashboard hiển thị đúng số liệu thật khớp 100% với kết quả test API ở trên (2 bài đã làm, 4 Điều đã học, 25% điểm trung bình, đúng 4 chủ đề cần ôn lại với đúng tên/% từng chủ đề), không có lỗi console. Đã trả .env.local về NEXT_PUBLIC_USE_MOCK_DATA=true sau khi verify xong.

Phase 8 — Frontend — ĐÃ HOÀN THÀNH (build sớm hơn thứ tự gốc, xem GHI CHÚ NGOẠI LỆ VỀ THỨ TỰ ở Mục 5; điều kiện cuối cùng để coi là "đã xong" — không còn helper mock-only — đã thỏa sau khi dọn dẹp cuối Phase 7)
[x] Đọc frontend.md và các ảnh reference trong design/ trước khi build — bám theo design system (màu, spacing, component) nhưng áp dụng đúng các điểm "rút gọn" đã note, không build theo đúng 100% mockup nếu mockup vượt scope backend thật
[x] Sidebar: thêm nav item "Trắc nghiệm" và "Tự luận" (2 trang riêng), cạnh "Tổng quan" và "Trợ lý AI" hiện có
[x] Trang đăng nhập / đăng ký
[x] Giao diện chat: ô nhập, lịch sử hội thoại, hiển thị câu trả lời kèm danh sách trích dẫn có thể thu gọn
[x] Trang trắc nghiệm (MCQ): làm bài, xem điểm + giải thích. Bug phát hiện lúc test end-to-end thật ở Phase 9: trang Quiz gọi POST /api/quiz/generate với body rỗng {} (thiếu quiz_set bắt buộc) → luôn lỗi 422 "Không tải được bộ câu hỏi" - bước "chọn bộ đề" mô tả ở frontend.md (mục 2, Bước 1) chưa từng được cài. Đã sửa: thêm màn hình chọn 1 trong 5 "BỘ ĐỀ SỐ" (gọi GET /api/quiz/sets qua getQuizSets() mới trong lib/api.ts) trước khi vào làm bài, sau khi chọn mới gọi getQuiz(quizSet) → POST /api/quiz/generate với đúng quiz_set; submitQuiz cũng bổ sung quiz_set vào QuizSubmitRequest cho khớp backend. Verify lại qua E2E thật: luồng chọn bộ đề → làm 10 câu → nộp bài → xem điểm chạy trọn vẹn, không lỗi console.
[x] Trang tự luận: hiển thị câu hỏi, ô nhập câu trả lời tự do, sau khi submit hiển thị matched_points/missing_points/feedback/suggested_dieu rõ ràng, dễ đọc
[x] Trang dashboard: từ khóa hôm qua, gợi ý chủ đề cần ôn (bản rút gọn theo Phase 7) — không còn card "Gợi ý học tập hôm nay" (đã bỏ hẳn, xem note ở Mục 5 và Mục 9)
[x] Loading state và thông báo lỗi cho mọi tác vụ async

Phase 9 — Đánh giá & Hoàn thiện (phục vụ bài báo) — ĐÃ HOÀN THÀNH
[x] Xây bộ test cố định (20-30 cặp câu hỏi - đáp án kèm Điều luật chuẩn): 29 câu tự soạn nội bộ (không chờ nhóm luật, UAT làm sau), backend/evaluation/test_set.json - 12 direct_citation + 10 analytical + 7 out_of_scope, ground truth đối chiếu trực tiếp với ingestion/chunks.json trước khi dùng (không tự bịa), trải đều cả 5 nguồn legal_text đã ingest (BLTTHS, BLHS, Nghị định 250, Thông tư liên tịch 05, Thông tư liên tịch 01/2026)
[x] Script đánh giá backend/evaluation/run_evaluation.py: gọi thật POST /api/chat/query cho từng câu (JWT thật, không mock), đo citation accuracy (exact_match_rate/recall/precision), groundedness (citations HOẶC đúng fallback - không bao giờ thiếu cả hai), correct-refusal rate (câu out_of_scope có bị từ chối đúng không), và academic-reference-usage cho 2 câu phân tích liên ngành. Đọc is_fallback/used_academic_reference từ chat_query_logs (service-role) vì 2 field này không lộ ra response API công khai.
[x] .env.example: bổ sung phần biến môi trường cho run_evaluation.py (EVAL_API_BASE_URL/EVAL_USER_EMAIL/EVAL_USER_PASSWORD, không lưu credential thật)
[x] README.md: viết lại hoàn chỉnh - tổng quan, cấu trúc thư mục, setup, cách chạy migrations/ingestion/app/evaluation, bảng API reference đầy đủ 11 route
[x] Test end-to-end đầy đủ trên trình duyệt thật (Playwright, không mock): đăng ký tài khoản mới hoàn toàn (không bị chặn bởi xác nhận email) → đăng nhập → hỏi chat → làm trắc nghiệm (chọn bộ đề → làm bài → nộp) → làm tự luận → xem dashboard - chạy trọn vẹn, 0 lỗi console. Lần chạy đầu tiên phát hiện 2 bug thật (xem chi tiết ở Phase 8 và Phase 4), đã sửa cả 2 và chạy lại E2E lần 2 để xác nhận.

Kết quả evaluation cuối cùng (backend/evaluation/results.json, sau khi đã sửa bug trích dẫn chéo văn bản ở Phase 4):
- Citation accuracy (n=20): exact_match_rate 95% (19/20), mean_recall 95%, mean_precision 38%. 1 câu fail: Nghị định 250 Điều 7 "Thành lập Hội đồng định giá tài sản" - hệ thống trả lời đúng nội dung nhưng trích Điều 1/8/9 (các Điều con) thay vì Điều 7 gốc - lỗi retrieval, không phải lỗi nội dung, chưa xử lý (known issue).
- Groundedness (n=29): 100% - không câu nào thiếu cả citations lẫn fallback.
- Correct-refusal rate (n=7, out_of_scope): 100%.
- Academic-reference usage (n=2, câu phân tích liên ngành): 100%.
- mean_precision thấp không phải dấu hiệu xấu: nhiều câu Nhóm B (analytical) được thiết kế để hệ thống trích thêm Điều liên quan ngoài Điều kỳ vọng tối giản trong ground truth (đúng ý đồ test độ sâu phân tích) - recall mới là chỉ số phản ánh đúng "có bỏ sót Điều quan trọng không".


6. Tiêu chuẩn code

Ngôn ngữ frontend: TypeScript (strict mode). Ngôn ngữ backend: Python 3.11+ có type hint đầy đủ.
Comment: bắt buộc bằng tiếng Anh. Chỉ comment phần logic không hiển nhiên (đặc biệt là regex tách luật và phần build prompt RAG) — không comment code đã tự giải thích rõ.
Đặt tên:
  File frontend: camelCase.ts cho utilities/services, PascalCase.tsx cho React components
  File/function/biến backend: snake_case.py
  Hằng số: UPPER_SNAKE_CASE
Import: nhóm theo thứ tự 3rd-party → internal services → utils.
Không dùng console.log / print trong production. Dùng logger utility đơn giản, có thể tắt qua biến ENVIRONMENT.
React: chỉ dùng functional components. Không dùng class components. Custom hooks cho logic tái sử dụng.
Tailwind: ưu tiên utility-first. Không dùng inline style={} trừ khi giá trị thực sự động.
Mọi prompt cho LLM đặt trong module prompts/ riêng, dạng hằng số đặt tên hoặc template function — không viết raw prompt string trực tiếp trong service logic.


7. Biến môi trường cần thiết
# Backend
ENVIRONMENT=development
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_JWT_SECRET=your_supabase_jwt_secret

# Google AI (Gemini)
GOOGLE_API_KEY=your_google_api_key_here
GEMINI_CHAT_MODEL=gemini-3.1-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

# Qdrant
QDRANT_URL=your_qdrant_cloud_url
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_COLLECTION=ttths_law_chunks

# Frontend (.env.local)
NEXT_PUBLIC_SUPABASE_URL=your_supabase_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000


8. Tiêu chí nghiệm thu (Definition of Done)
Một Phase chỉ được coi là xong khi TẤT CẢ tiêu chí dưới đây đạt.
Phase 1 — Scaffold: GET /api/health trả về { status: "ok" }. Log kết nối Supabase và Qdrant thành công khi khởi động.
Phase 2 — Auth: Đăng ký + đăng nhập chạy được end-to-end. Route bảo vệ trả về 401 khi không có token hợp lệ.
Phase 3 — Ingestion: Chạy script ingestion trên toàn bộ 12 file nguồn (cả legal_text và academic_reference) ra chunks đúng cấu trúc cho từng loại (spot-check ít nhất 10 chunk mỗi loại) và upsert thành công vào Qdrant kèm đầy đủ metadata bao gồm source_type.
Phase 4 — RAG: Câu hỏi nêu rõ 1 Điều cụ thể trả về câu trả lời trích đúng Điều đó. Câu hỏi ngoài phạm vi dữ liệu trả về thông báo fallback "không tìm thấy", không bịa câu trả lời. Mọi câu trả lời đều có ít nhất 1 trích dẫn hoặc thông báo fallback — không bao giờ thiếu cả hai.
Phase 5a — Quiz (MCQ): Trắc nghiệm sinh ra có đúng 1 đáp án đúng mỗi câu, đáp án nhiễu hợp lý, việc nộp bài được lưu theo từng user kèm topic_category, và logic luân phiên không lặp lại câu vừa làm trong lượt kế tiếp.
Phase 5b — Tự luận: Nộp câu trả lời tự do trả về đúng cấu trúc matched_points/missing_points/feedback/suggested_dieu, feedback bám theo essay_key_points có sẵn (không phải LLM tự phán đoán tự do), và câu hỏi tự luận cũng tuân theo logic luân phiên như 5a.
Phase 6 — Gợi ý: Chip gợi ý hiển thị đúng, bấm vào thì tự điền/gửi câu hỏi vào ô chat.
Phase 7 — Dashboard: Danh sách từ khóa phản ánh đúng câu hỏi đã log ngày hôm trước; danh sách chủ đề yếu cập nhật sau khi nộp bài trắc nghiệm hoặc bài tự luận.
Phase 8 — Frontend: Chạy được đầy đủ luồng trên trình duyệt: đăng ký → đăng nhập → chat → trắc nghiệm → tự luận → dashboard, điều hướng qua sidebar đúng như frontend.md.
Phase 9 — Đánh giá: Script đánh giá chạy được trên bộ test cố định, xuất ra số liệu độ chính xác trích dẫn / groundedness / tỷ lệ từ chối đúng, dùng được cho bài báo.


9. Ngoài phạm vi (Không triển khai — để dành cho v2 / hướng phát triển)

Chụp/tải ảnh và phân tích nội dung ảnh
Push notification / job lên lịch gửi thông báo (mục từ khóa trên dashboard chỉ hiển thị tĩnh khi user load trang, xem Phase 7)
Gamification (điểm, xu, đổi thưởng)
Tự động theo dõi/nạp văn bản luật mới ban hành (ingestion là bước CLI thủ công, chạy lại khi dev quyết định)
OAuth / đăng nhập mạng xã hội (chỉ dùng email/password qua Supabase Auth)
Streaming câu trả lời real-time (WebSocket/SSE) — dùng HTTP request/response chuẩn
Giao diện admin quản lý văn bản (ingestion chỉ chạy qua CLI cho deadline này)
Multi-tenancy / quản lý tổ chức
Model reasoning liên luật phức tạp ngoài việc co-retrieval đơn giản (liên kết LTTHS ↔ LHS chỉ là "hiển thị thêm Điều liên quan từ cùng lượt tìm kiếm", không phải hệ thống reasoning riêng)
Card "Gợi ý học tập hôm nay" trên dashboard (tách biệt khỏi weak-topics) — không có route hỗ trợ, weak-topics đã đủ đóng vai trò tương tự, để dành v2 nếu cần tách riêng.
Disambiguation văn bản cho related_articles khi câu hỏi không nêu rõ tên luật: đã sửa exact-match citations (field citations, xem Phase 4) để lọc đúng source_document khi câu hỏi nêu rõ tên văn bản, nhưng related_articles (gợi ý phụ qua semantic search) đôi khi vẫn lẫn Điều từ văn bản khác trùng số - chấp nhận cho bản 05/09 vì đây là field gợi ý phụ, không phải căn cứ trích dẫn chính; nếu cần độ chính xác cao hơn ở v2, cân nhắc áp dụng cùng cơ chế lọc source_document cho related_articles hoặc bỏ hẳn việc gộp kết quả semantic đa văn bản.
Giao diện quản lý phiên bản văn bản (document versioning)
Streak ngày học liên tiếp, breakdown tiến độ trắc nghiệm chi tiết theo nhiều nhóm chủ đề với circular progress riêng, gợi ý học tập có lý do cá nhân hóa theo ngữ cảnh hội thoại (xem frontend.md để biết bản đầy đủ dự kiến cho v2)
Chấm tự luận hoàn toàn tự do không dựa trên rubric (essay_key_points) — module tự luận ở Phase 5b luôn phải grounding vào rubric có sẵn trong ngân hàng đề, không để LLM tự quyết định đúng/sai theo cảm tính