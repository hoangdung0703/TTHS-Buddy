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

GHI CHÚ NGOẠI LỆ VỀ THỨ TỰ: Phase 8 (Frontend) đã được build sớm hơn thứ tự gốc (hoàn thành trước Phase 3), chạy song song trong lúc chờ nhóm sinh viên luật cung cấp văn bản BLTTHS cho Phase 3. Toggle qua NEXT_PUBLIC_USE_MOCK_DATA trong frontend/.env.local, logic mock tập trung tại lib/api.ts + lib/mockData.ts. Khi Phase 3-7 hoàn thành với dữ liệu thật, chỉ cần đổi NEXT_PUBLIC_USE_MOCK_DATA=false, không cần sửa lại component. LƯU Ý: Phase 8 dùng tạm 2 helper mock-only không map với route nào trong 8 route gốc — getDashboardStats và getRelatedArticles (xem lib/types.ts/api.ts, có comment đánh dấu non-canonical). Đã bổ sung route/field thật để thay thế 2 helper này: related_articles giờ là field trong response của POST /api/chat/query (Phase 4), và GET /api/dashboard/stats mới (Phase 7). Khi build Phase 4 và Phase 7, PHẢI xóa/thay 2 helper mock-only này bằng gọi API thật tương ứng, không được để tồn tại song song. Không coi Phase 8 là "đã xong" theo Định nghĩa hoàn thành ở Mục 8 cho đến khi đã verify lại với dữ liệu thật từ backend VÀ 2 helper mock-only này đã được thay thế.

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

Việc cần làm thủ công khi setup lại từ đầu (dự án không dùng ORM/migration runner): chạy 1 lần file backend/migrations/0001_chat_query_logs.sql trong Supabase SQL Editor để tạo bảng chat_query_logs trước khi logging hoạt động — lỗi log bị catch nên không crash API nếu bảng chưa tồn tại, nhưng log sẽ không được ghi.

Phase 3 Extension — Trích xuất Chương/Mục + Câu hỏi tổng hợp (sau deadline 05/09)
Bối cảnh: Phase 6 gốc cố tình bỏ qua việc trích Chương/Mục (dùng vector similarity thay thế cho suggested_followups, chấp nhận làm accepted-limitation). Phát sinh nhu cầu mới: user hỏi câu tổng hợp kiểu "Bộ luật TTHS có bao nhiêu chương, bao nhiêu điều?" — không chunk nào retrieve được vì đây không phải câu hỏi tra cứu nội dung 1 chỗ cụ thể, bot từ chối đúng theo grounding nhưng trải nghiệm kém. Giải quyết tận gốc bằng cách trích Chương/Mục thật, giải quyết đồng thời cả 2 vấn đề.

[ ] Mở rộng chunking.py (chỉ áp dụng cho legal_text, KHÔNG động vào academic_reference): thêm bước nhận diện heading "Chương [số La Mã]" và "Mục [số]" trong lúc parse, gắn chuong_number, chuong_title, muc_number (nullable), muc_title (nullable) vào metadata của mọi chunk thuộc chương/mục đó
[ ] BƯỚC TEST BẮT BUỘC trước khi re-parse toàn bộ: viết test case cụ thể xác nhận việc thêm nhận diện Chương/Mục KHÔNG phá vỡ logic tách title đã fix kỹ ở Phase 3 gốc (37 case bảng tra cứu tường minh, rule Khoản-aware) — chạy lại toàn bộ test case cũ đã có, xác nhận không hồi quy, trước khi thêm test case mới cho Chương/Mục
[ ] Re-parse CHỈ 3 văn bản legal_text có cấu trúc Chương/Mục thật (BLTTHS, BLHS — kiểm tra Nghị định 250/Thông tư liên tịch có cấu trúc Chương/Mục hay không, nếu không có thì bỏ qua, không ép cấu trúc không tồn tại). Không re-parse academic_reference (không liên quan)
[ ] Re-embed + re-upsert đúng các chunk legal_text bị ảnh hưởng (không chạy lại toàn batch 12 file)
[ ] Payload index mới trên Qdrant: chuong_number (cho phép filter/group theo chương)
[ ] Xử lý câu hỏi tổng hợp (aggregate query) — KHÔNG qua LLM generate từ context retrieve được (dễ bịa/đếm sai), mà đếm trực tiếp bằng query có cấu trúc lên Qdrant:
    - Phát hiện intent câu hỏi dạng "bao nhiêu chương/điều/khoản" (có thể dùng chính bước Query Understanding đã có ở Phase 4 Extension để nhận diện intent này)
    - Nếu phát hiện, đếm distinct chuong_number và distinct dieu_number cho đúng văn bản (source_document) được hỏi, trả lời trực tiếp từ con số đếm được trong Qdrant — kèm câu ghi chú rõ đây là số liệu tính từ dữ liệu đã ingest (không phải trích dẫn 1 nguồn văn bản cụ thể, và có thể lệch nếu văn bản có sửa đổi bổ sung sau thời điểm ingest)
[ ] Cập nhật Phase 6 (suggested_followups): ưu tiên gợi ý Điều CÙNG chuong_number trước (chính xác cấu trúc), chỉ fallback về vector similarity nếu không tìm đủ Điều cùng chương — cải thiện đúng giới hạn "gợi ý liên quan về nội dung nhưng không đảm bảo cùng Chương/Mục" đã ghi nhận ở Phase 6 gốc

Phase 4 Extension — Streaming + Multi-turn Context + Query Understanding (sau deadline 05/09, cải thiện trải nghiệm, không còn giới hạn ngân sách API)
Bối cảnh: Phase 4 gốc chỉ xử lý 1 câu hỏi độc lập, không có ngữ cảnh hội thoại, không viết tắt được, không streaming. Mở rộng theo 3 yêu cầu đã chốt.

[ ] Query Understanding — 1 lượt Gemini nhẹ chạy TRƯỚC retrieval, làm 2 việc trong cùng 1 lần gọi:
    (a) Mở rộng viết tắt luật phổ biến (CQĐT, VKS, TA, BLTTHS...) thành đầy đủ
    (b) Nếu có lịch sử hội thoại: giải quyết ngữ cảnh ngầm hiểu từ câu hỏi trước (đại từ, câu hỏi nối tiếp không đủ chủ ngữ) thành câu hỏi độc lập đầy đủ
    RÀNG BUỘC BẮT BUỘC: chỉ diễn giải lại/mở rộng dựa trên ngữ cảnh đã có trong hội thoại hoặc bảng viết tắt luật chuẩn — KHÔNG được tự suy đoán/thêm nội dung pháp lý mới vào câu hỏi (đúng nguyên tắc grounding đã áp dụng xuyên suốt dự án, áp dụng cả cho bước tiền xử lý, không chỉ bước sinh câu trả lời cuối)
    Lưu cả question gốc và rewritten_question vào chat_query_logs (thêm cột) — để tính minh bạch, biết retrieval sai là do viết lại sai hay do retrieval sai
    Retrieval dùng rewritten_question, không dùng question gốc

[ ] Multi-turn context: thêm conversation_id (client tạo/giữ theo phiên chat), migration mới thêm cột conversation_id vào chat_query_logs. Khi sinh câu trả lời cuối, đưa 2-3 lượt hỏi-đáp gần nhất (không phải toàn bộ lịch sử) vào prompt — tránh phình token khi hội thoại dài

[ ] Streaming response: POST /api/chat/query chuyển sang SSE (Server-Sent Events). Thứ tự event:
    1. event "citations" — gửi ngay khi retrieval xong (citations + related_articles đã có sẵn trước khi generation bắt đầu, không cần đợi)
    2. event "answer_delta" — token chảy dần trong lúc generation
    3. event "suggested_followups" — gửi khi generation xong
    4. event "done" — đóng stream
    Fallback (không tìm thấy): vẫn qua đúng luồng SSE, citations rỗng, answer_delta chứa câu fallback

[ ] Frontend: chuyển sang đọc SSE (EventSource hoặc fetch + ReadableStream), FormattedAnswer.tsx render tăng dần theo answer_delta. LƯU Ý RỦI RO: react-markdown parse markdown chưa hoàn chỉnh giữa chừng (ví dụ list chưa đóng) có thể render lệch tạm thời trong lúc stream — cần test kỹ, chấp nhận nhấp nháy nhẹ hoặc xử lý buffer hợp lý (ví dụ chỉ re-render markdown mỗi N ký tự/khi gặp ranh giới dòng, không re-render mỗi token)

[ ] QUAN TRỌNG — cập nhật backend/evaluation/run_evaluation.py: script hiện gọi thẳng POST /api/chat/query dạng request/response thường, giờ endpoint là SSE — cần sửa để đọc hết stream, ghép lại thành answer + citations đầy đủ trước khi tính metric, không được để Phase 9 evaluation bị hỏng bởi thay đổi kiến trúc này. Chạy lại toàn bộ 29 câu test sau khi sửa, xác nhận số liệu không đổi so với trước (vì bản chất câu trả lời không đổi, chỉ đổi cách truyền tải).

Phase 4 Extension 2 — Lưu/khôi phục lịch sử hội thoại — ĐÃ HOÀN THÀNH (sau deadline 05/09)
Bối cảnh: phát hiện Sidebar vẫn hiển thị 3 conversation hardcode từ Phase 8 (mock, chưa từng thay bằng dữ liệu thật), chat/page.tsx không lưu/tải lại lịch sử — rời trang là mất hội thoại hiện tại, kể cả trong cùng phiên trình duyệt. Đây là tính năng CHƯA TỪNG được build phần đọc (không phải bug) — dữ liệu để dựng lại lịch sử đã có sẵn trong chat_query_logs (conversation_id đã thêm từ Phase 4 Extension), chỉ thiếu tầng đọc + hiển thị.

[x] GET /api/chat/conversations — liệt kê danh sách conversation của user, group theo conversation_id, mỗi group trả về id, tiêu đề (lấy từ câu hỏi đầu tiên của conversation đó, cắt ngắn tối đa 60 ký tự), thời gian cập nhật gần nhất — sắp xếp mới nhất trước.
    QUYẾT ĐỊNH: group trong Python từ 1 lượt select đã filter theo user_id (chat_log_service.list_conversations), KHÔNG dùng Postgres GROUP BY/RPC — codebase này chưa từng có custom Postgres function nào, dashboard_service.py cũng aggregate-on-read theo đúng cách này (xem get_keywords_yesterday). An toàn ở quy mô demo NCKH (1 sinh viên, không phải hàng nghìn conversation/user).
[x] GET /api/chat/conversations/{conversation_id} — toàn bộ turns (câu hỏi + câu trả lời) của 1 conversation cụ thể, theo đúng thứ tự thời gian.
    BẢO MẬT (chat_log_service.get_conversation_detail): filter .eq("user_id", user_id) NGAY TRONG CÙNG 1 query Supabase với .eq("conversation_id", ...) — vì backend dùng service-role key (bypass RLS, xem comment migrations/0001), đây là chốt chặn DUY NHẤT ngăn user A đọc được conversation của user B. Conversation không tồn tại VÀ conversation tồn tại nhưng thuộc user khác đều trả về None → route trả 404 (không phải 403) để không xác nhận với caller rằng id đó có tồn tại dưới quyền người khác.
[x] Sidebar.tsx: xóa MOCK_CONVERSATION_HISTORY, gọi GET /api/chat/conversations thật (qua lib/api.ts getConversations(), tôn trọng NEXT_PUBLIC_USE_MOCK_DATA như mọi hàm khác trong api.ts), mỗi item là <Link href={`/chat/${conversation_id}`}> điều hướng vào đúng conversation đó, refetch lại danh sách mỗi khi pathname đổi (để hỏi xong 1 câu mới trên /chat thì conversation mới xuất hiện ngay trong danh sách mà không cần reload trang).
[x] Route/URL: chọn dynamic route /chat/[conversationId] (không dùng query string) — idiomatic hơn với App Router hiện có, cho phép bookmark/share 1 conversation cụ thể. Tách logic chat ra component dùng chung frontend/src/components/chat/ChatView.tsx (nhận prop conversationId: string | null), dùng lại cho cả app/chat/page.tsx (conversationId=null, hội thoại mới) và app/chat/[conversationId]/page.tsx (Server Component await params rồi truyền xuống, do Next.js 15 params là Promise).
[x] chat/page.tsx (nay là ChatView.tsx dùng chung): useEffect keyed theo prop conversationId gọi GET /api/chat/conversations/{id} tải lại toàn bộ messages trước khi cho phép hỏi tiếp, thay vì luôn khởi tạo rỗng — có loading state riêng (isLoadingHistory) trong lúc tải. Effect chạy lại đúng khi conversationId đổi (kể cả chuyển thẳng từ conversation A sang B qua Sidebar mà không qua trang trắng), không chỉ chạy 1 lần lúc mount.
[x] Nút "Hội thoại mới" ở Sidebar: xác nhận vẫn trỏ về /chat (không kèm conversationId) — app/chat/page.tsx luôn truyền conversationId=null cho ChatView, hành vi tạo conversation mới qua SSE citations event giữ nguyên như trước, không bị ảnh hưởng.
[x] Verify E2E: `npm run build` sạch (dynamic route /chat/[conversationId] lên đúng route map), `tsc --noEmit` sạch. Verify tầng API thật (không mock, không server thật chưa chạy) bằng backend/evaluation/test_conversation_history_e2e.py với tài khoản Supabase thật (tạo qua Admin API, sign-in bằng password grant thật — JWT thật do Supabase cấp, không tự ký): hỏi 2 câu cùng 1 conversation → conversation_id giữ nguyên; hỏi câu mới không kèm conversation_id → conversation_id MỚI, không trùng; GET /api/chat/conversations liệt kê đúng cả 2, mới nhất trước; GET /api/chat/conversations/{id} trả đúng thứ tự 2 turns kèm đúng nội dung câu trả lời đã stream. Dev server (uvicorn + next dev) khởi động sạch, GET /chat và /chat/{id} trả 200 không lỗi server.
    GIỚI HẠN ĐÃ CÔNG KHAI: môi trường hiện tại không có công cụ điều khiển trình duyệt thật (Playwright/tương tự) nên KHÔNG click-through bằng browser thật để chụp màn hình xác nhận "chuyển sang Dashboard rồi quay lại /chat không mất hội thoại" — verify thay thế bằng review code (ChatView.tsx effect logic + Next.js App Router remount semantics đã xác nhận qua build output) và verify đầy đủ hợp đồng API mà UI phụ thuộc vào. Đề xuất: nếu cần độ tin cậy tuyệt đối, tự tay verify thêm 1 lượt qua trình duyệt thật.
[x] TEST BẢO MẬT RIÊNG (ownership) — dùng 2 tài khoản Supabase thật khác nhau (tạo/xoá qua Admin API trong chính script test, không để lại rác): User B dùng ĐÚNG conversation_id thật của User A + token JWT thật của chính User B → 404 (không phải 200/403, không leak dữ liệu). GET /api/chat/conversations của User B xác nhận KHÔNG chứa bất kỳ conversation_id nào của User A. Gọi không kèm Authorization header → 401. TOÀN BỘ PASS, không có trường hợp nào lộ dữ liệu chéo user. Script lưu lại: backend/evaluation/test_conversation_history_e2e.py (tự tạo 2 tài khoản thật, chạy test, tự xoá tài khoản + log rows khi xong kể cả lúc fail).
    ĐÍNH CHÍNH ghi chú cũ ở dòng này (SAI, đã sửa lại): lúc viết xong Phase 4 Extension 2, ghi chú cũ ở đây kết luận nhầm "PyJWT thiếu leeway cho iat" là "bug môi trường, không liên quan code sản phẩm, không ảnh hưởng người dùng thật". Kết luận đó SAI. Đây LÀ bug thật trong code sản phẩm (backend/app/core/security.py), ảnh hưởng MỌI route có auth — không riêng gì 2 route conversation mới build ở Phase này. Phát hiện lại đúng bản chất khi user report 401 hàng loạt trên /api/dashboard/* với tài khoản mới tạo (xem mục sửa lỗi riêng ngay bên dưới) — đây chính xác là kịch bản dễ trúng bug nhất: tài khoản MỚI đăng nhập xong gọi API ngay lập tức, không có "độ trễ tự nhiên" nào cả trong một luồng UX bình thường (login xong tự động chuyển trang gọi API ngay). Bug này có thể xảy ra bất cứ lúc nào 2 server độc lập (backend và Supabase Auth) bị lệch đồng hồ dù chỉ vài giây — đây chính là lý do "leeway" là thực hành chuẩn bắt buộc khi verify JWT giữa các hệ thống phân tán, không phải trường hợp hiếm/giả định.

Phase 4 Extension 2 — ĐÃ HOÀN THÀNH. File thay đổi: backend/app/models/chat.py, backend/app/services/chat_log_service.py, backend/app/api/chat.py, frontend/src/components/layout/Sidebar.tsx, frontend/src/app/chat/page.tsx, frontend/src/lib/api.ts, frontend/src/lib/types.ts, frontend/src/lib/mockData.ts. File mới: frontend/src/components/chat/ChatView.tsx, frontend/src/app/chat/[conversationId]/page.tsx, backend/evaluation/test_conversation_history_e2e.py.

Sửa lỗi phát sinh — 401 Unauthorized hàng loạt trên /api/dashboard/* với tài khoản mới tạo — ĐÃ SỬA
Bối cảnh: user report Dashboard bị 401 hàng loạt ngay sau khi tạo tài khoản mới, kèm log cho thấy nhiều request lặp lại liên tục trên 3 route dashboard từ nhiều port khác nhau.
[x] Xác nhận nguyên nhân gốc bằng tái hiện thật (không đoán): backend/app/core/security.py's verify_supabase_jwt() gọi jwt.decode() (cả nhánh ES256 lẫn HS256) KHÔNG truyền leeway — mặc định PyJWT có leeway=0 cho claim "iat". Tái hiện trực tiếp: tạo tài khoản Supabase thật mới qua Admin API, sign-in thật, gọi cả 3 route dashboard NGAY LẬP TỨC (0 độ trễ chủ động) → cả 3 đều 401 "Invalid token". Bắt đúng exception gốc: jwt.exceptions.ImmatureSignatureError('The token is not yet valid (iat)'). Đo được lệch giờ thực tế giữa máy chạy backend và server thật (đối chiếu qua HTTP Date header của google.com) dao động TỪ VÀI GIÂY ĐẾN HÀNG CHỤC PHÚT tùy thời điểm trong môi trường sandbox này — xác nhận rõ đây là lệch đồng hồ thật giữa 2 hệ thống, không phải lỗi logic khác.
[x] Sửa: thêm leeway=30 (giây) vào cả 2 lệnh jwt.decode() trong verify_supabase_jwt (nhánh ES256 và HS256) — 30s là mức leeway tiêu chuẩn ngành cho lệch đồng hồ giữa 2 server bảo trì tốt (NTP sync bình thường), áp dụng cho toàn bộ claim thời gian (iat/exp/nbf), không tắt hẳn việc kiểm tra hết hạn token.
[x] XÁC NHẬN LẠI: đây LÀ vấn đề ảnh hưởng người dùng thật, không phải chỉ môi trường test — bất kỳ lúc nào backend server và Supabase Auth server lệch đồng hồ dù chỉ vài giây (hoàn toàn có thể xảy ra ở môi trường production thật, đây là lý do "leeway" là thực hành bắt buộc), tài khoản MỚI đăng nhập xong vào thẳng Dashboard (không có độ trễ tự nhiên nào giữa 2 hành động này trong luồng UX thật) sẽ dính lỗi y hệt. Đã đính chính lại ghi chú sai ở Phase 4 Extension 2 phía trên.
[x] Điều tra riêng vấn đề request lặp lại dày đặc, nhiều port: rà soát toàn bộ frontend (grep "retry"/"setInterval"/"401" trên frontend/src) — KHÔNG có logic tự động retry khi 401 ở đâu cả. dashboard/page.tsx chỉ gọi loadDashboard() 1 lần trong useEffect (dependency rỗng), retry duy nhất là nút "Thử lại" do user chủ động bấm. Không có component nào khác gọi 3 API dashboard này (grep xác nhận chỉ dashboard/page.tsx). Kết luận: "nhiều port khác nhau" trong log là hiện tượng BÌNH THƯỜNG của TCP (mỗi request/connection mới luôn có source port khác nhau, không phải dấu hiệu nhiều server/nhiều tiến trình) — không phải bug retry. "Lặp lại liên tục" nhiều khả năng do: (a) React StrictMode (frontend/next.config.ts có reactStrictMode: true) khiến React double-invoke effect lúc dev, gấp đôi số lần gọi mỗi lần mount trang (CHỈ xảy ra ở `next dev`, KHÔNG xảy ra ở production build/`next start`), và (b) với bug iat ở trên, mọi lượt gọi đều fail nên user/quá trình test phải bấm "Thử lại" nhiều lần hoặc chạy lại script test nhiều lần trong lúc debug — không phải vòng lặp tự động vô hạn.
[x] Test lại đúng kịch bản gây lỗi: tạo tài khoản MỚI hoàn toàn qua Admin API, sign-in thật, gọi cả 3 route dashboard NGAY LẬP TỨC — chạy lại 3 lần liên tiếp, tất cả đều trả 200 (trước khi sửa: 401 cả 3/3). Script lưu lại: backend/evaluation/test_jwt_iat_leeway.py (tự tạo + tự xoá tài khoản test).

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

Bug Phase 3 phát hiện thêm trong lúc làm Phase 5a: 6 Điều trong Bộ luật TTHS.pdf (Điều 7, 135, 233, 243, 268, 382 — 10 chunk kể cả 5 Khoản của Điều 382) bị dính số trang vào cuối dieu_title/chunk_text do lỗi extract PDF ở Phase 3. Đã sửa cơ học (cắt số trang thừa), re-embed + re-upsert đúng 10 chunk, verify qua Phase 4 RAG xác nhận citation sạch. Script ingestion/fix_dieu_title_page_bleed.py giữ lại để tái sử dụng nếu phát hiện thêm case tương tự.

Phase 5b — Module tự luận (câu hỏi mở)
[ ] essay_service.py — nhận câu trả lời tự do (free-text) của user cho 1 câu hỏi trong ngân hàng đề, chấm điểm bằng LLM-as-judge dựa trên essay_key_points (rubric) đã có sẵn trong ngân hàng đề — KHÔNG để LLM tự đánh giá đúng/sai theo cảm tính, phải grounding vào rubric cụ thể
[ ] Prompt chấm điểm bắt buộc trả về theo cấu trúc: (1) các ý đã trả lời đúng, (2) các ý còn thiếu/sai so với essay_key_points, (3) gợi ý Điều/Khoản nên ôn lại
[ ] POST /api/essay/question — lấy 1 câu hỏi tự luận (qua question_bank_service, cùng logic luân phiên với 5a)
[ ] POST /api/essay/submit — nhận { question_id, user_answer: string }, trả về { matched_points: [], missing_points: [], feedback: string, suggested_dieu: [] }
[ ] Lưu lịch sử bài làm tự luận theo từng user (dùng cho Phase 7 weak-topics và Phase 9 evaluation)

Phase 6 — Gợi ý câu hỏi & chủ đề liên quan (cập nhật theo yêu cầu thực tế từ nhóm luật — gợi ý động theo câu hỏi vừa hỏi, không chỉ list tĩnh)
[ ] Trạng thái cold-start (chưa hỏi gì, mới vào trang chat): dùng danh sách câu hỏi/tình huống thường gặp do nhóm sinh viên luật cung cấp (dạng file JSON seed) — giữ nguyên thiết kế gốc cho trường hợp này
[ ] GET /api/chat/suggestions — trả về danh sách soạn sẵn để hiển thị dạng chip bấm nhanh khi chưa có hội thoại nào
[ ] Gợi ý động sau khi có câu trả lời (tính năng chính, thay thế cách tiếp cận cũ): sau khi RAG trả lời và trích dẫn 1 hoặc nhiều dieu_number, lấy embedding của chunk đó, tìm top-3 chunk legal_text khác gần nhất trong Qdrant (cùng source_document, loại trừ chính chunk đang xét, có thể loại trừ các dieu_number đã xuất hiện trong citations của câu trả lời hiện tại để tránh gợi ý trùng), sinh câu hỏi gợi ý ngắn từ dieu_title của các chunk đó (ví dụ dieu_title "Nhiệm vụ, quyền hạn của Thư ký Tòa án" → chip "Thư ký Tòa án có nhiệm vụ, quyền hạn gì?"). Field này trả trong response của POST /api/chat/query, ví dụ suggested_followups: [{dieu_number, suggested_question}]
[ ] Lý do chọn vector similarity thay vì group theo Chương/Mục: tận dụng hạ tầng Qdrant có sẵn, không cần re-parse/re-embed lại Phase 3. Văn phong luật thường lặp khuôn mẫu cho các Điều cùng nhóm chức năng (ví dụ "Nhiệm vụ, quyền hạn của X") nên vector similarity vẫn bắt được đúng quan hệ "Điều liền kề chức năng" trong phần lớn trường hợp dù không có metadata Chương/Mục rõ ràng
[ ] Liên kết chủ đề liên quan trong related_articles (Phase 4): giữ nguyên như đã có — 1-2 Điều liên quan retrieve cùng lượt tìm kiếm, không trộn lẫn với cơ chế suggested_followups mới (2 field khác mục đích: related_articles là nguồn phụ hỗ trợ câu trả lời hiện tại, suggested_followups là gợi ý cho câu hỏi TIẾP THEO)

Phase 7 — Dashboard cá nhân (bản rút gọn cho 05/09, xem frontend.md để biết bản đầy đủ dành cho v2)
[ ] GET /api/dashboard/keywords-yesterday — query các câu hỏi user đã log trong ngày hôm trước, group theo dieu_number, trả về dạng danh sách (hiển thị tĩnh trên dashboard, không push notification)
[ ] GET /api/dashboard/weak-topics — rule đơn giản: chủ đề (topic_category) có điểm trung bình (gộp cả MCQ và tự luận) < 50% hoặc bị hỏi lại/làm sai nhiều lần, hiển thị dạng "gợi ý ôn lại". KHÔNG cần breakdown chi tiết theo range Điều hay số lần làm, chỉ cần tên chủ đề + % điểm + nút ôn tập
[ ] GET /api/dashboard/stats — trả về { total_quiz_attempts, average_score, dieu_studied_count } tính từ dữ liệu quiz/essay submissions đã lưu ở Phase 5a/5b — thay thế hẳn helper mock getDashboardStats đã dùng tạm ở Phase 8, tính 1 lần ở backend, không tính lại phía frontend
[ ] Không làm: streak ngày học liên tiếp, circular progress breakdown theo 4+ nhóm chủ đề riêng biệt, gợi ý cá nhân hóa có lý do ngữ cảnh — các phần này để dành v2 (xem Mục 9)

Phase 8 — Frontend
[ ] Đọc frontend.md và các ảnh reference trong design/ trước khi build — bám theo design system (màu, spacing, component) nhưng áp dụng đúng các điểm "rút gọn" đã note, không build theo đúng 100% mockup nếu mockup vượt scope backend thật
[ ] Sidebar: thêm nav item "Trắc nghiệm" và "Tự luận" (2 trang riêng), cạnh "Tổng quan" và "Trợ lý AI" hiện có
[ ] Trang đăng nhập / đăng ký
[ ] Giao diện chat: ô nhập, lịch sử hội thoại, hiển thị câu trả lời kèm danh sách trích dẫn có thể thu gọn
[ ] Trang trắc nghiệm (MCQ): làm bài, xem điểm + giải thích
[ ] Trang tự luận: hiển thị câu hỏi, ô nhập câu trả lời tự do, sau khi submit hiển thị matched_points/missing_points/feedback/suggested_dieu rõ ràng, dễ đọc
[ ] Trang dashboard: từ khóa hôm qua, gợi ý chủ đề cần ôn (bản rút gọn theo Phase 7)
[ ] Loading state và thông báo lỗi cho mọi tác vụ async

Phase 9 — Đánh giá & Hoàn thiện (phục vụ bài báo)
[ ] Xây bộ test cố định NỘI BỘ trước (20-30 cặp câu hỏi - đáp án kèm Điều luật chuẩn) — KHÔNG chờ nhóm sinh viên luật, tự xây dựng từ dữ liệu đã có (corpus Qdrant + question_bank.json đã qua parse/spot-check ở Phase 5a). UAT (User Acceptance Testing) với nhóm luật là hoạt động RIÊNG, làm sau, không phải input bắt buộc cho bước này.
    - Nguồn câu hỏi: có thể tái sử dụng câu hỏi essay/mcq đã có ground truth dieu_number từ question_bank.json (chuyển thành câu hỏi dạng "Điều X quy định gì?" hoặc dùng nguyên văn câu hỏi tự luận), bổ sung thêm câu hỏi tự soạn theo 3 nhóm bắt buộc: (a) câu hỏi trực tiếp nêu số Điều (đo citation accuracy), (b) câu hỏi phân tích cần academic_reference (đo khả năng phân tầng retrieval), (c) câu hỏi ngoài phạm vi corpus (đo tỷ lệ từ chối đúng — ví dụ hỏi về luật dân sự, luật hôn nhân)
    - Ground truth (dieu_number đúng, hoặc "should_refuse: true" cho câu ngoài phạm vi) do người xây bộ test tự xác định dựa trên corpus đã biết, không cần nhóm luật duyệt trước ở bước này
[ ] Script đánh giá: đo độ chính xác trích dẫn (Điều trích dẫn có khớp ground truth không), groundedness (câu trả lời có tránh khẳng định không có căn cứ không), tỷ lệ từ chối đúng lúc (bot có nói "không tìm thấy" đúng khi cần không)
[ ] .env.example với đầy đủ key và mô tả
[ ] README.md: tổng quan dự án, hướng dẫn setup, cách chạy ingestion, cách chạy app, API reference
[ ] Test end-to-end đầy đủ: đăng ký → đăng nhập → hỏi câu hỏi → nhận câu trả lời có căn cứ → làm trắc nghiệm → xem dashboard
[ ] Việc dành cho sau (không thuộc phạm vi Phase 9 nội bộ này): tổ chức UAT với nhóm sinh viên luật — họ tự trải nghiệm sản phẩm thật, phản hồi chất lượng câu trả lời/độ chính xác trích dẫn theo góc nhìn chuyên môn luật, có thể phát hiện thêm case sai mà bộ test nội bộ chưa bao phủ

Kết quả evaluation nội bộ (29 câu, dùng cho phần Evaluation/Results của bài báo):
- Groundedness: 100% (29/29) — mọi câu trả lời đều có citations hoặc đúng câu fallback, không câu nào thiếu cả hai
- Citation accuracy (20 câu direct_citation + analytical có expected_dieu_numbers): exact_match_rate 95% (19/20), mean_recall 95%, mean_precision 42% (precision thấp do câu hỏi phân tích thường trích thêm Điều liên quan ngoài ground truth tối giản — recall là chỉ số phản ánh đúng "có bỏ sót Điều quan trọng không")
- Correct-refusal rate (7 câu out_of_scope): 100% (7/7)
- Academic-reference usage (2 câu phân tích liên ngành, expected_dieu_numbers rỗng): 100% (2/2) kéo đúng academic_reference
- 1 case fail đáng chú ý (câu hỏi về Hội đồng định giá tài sản, Nghị định 250): hệ thống trích Điều 1/8/9 (các Điều cụ thể theo từng cấp) thay vì Điều 7 (Điều tổng quát) như ground truth kỳ vọng — nội dung câu trả lời vẫn đúng đầy đủ. Đánh giá đây là ambiguity trong lựa chọn ground truth đơn giản hóa hơn là bug retrieval thật sự (tương tự tình huống nhiều Điều cùng số ở các văn bản khác nhau đã gặp ở Phase 4) — không sửa retrieval logic vì 1 case, ghi nhận làm case study cho phần Discussion/Limitations của bài báo.


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
Giao diện quản lý phiên bản văn bản (document versioning)
Streak ngày học liên tiếp, breakdown tiến độ trắc nghiệm chi tiết theo nhiều nhóm chủ đề với circular progress riêng, gợi ý học tập có lý do cá nhân hóa theo ngữ cảnh hội thoại (xem frontend.md để biết bản đầy đủ dự kiến cho v2)
Chấm tự luận hoàn toàn tự do không dựa trên rubric (essay_key_points) — module tự luận ở Phase 5b luôn phải grounding vào rubric có sẵn trong ngân hàng đề, không để LLM tự quyết định đúng/sai theo cảm tính