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

BUG PHÁT HIỆN SAU (không phải lúc build ban đầu) — logic either/or giữa legal_text và academic_reference: điều kiện needs_academic ban đầu là short-circuit — nếu legal_primary có điểm max ≥ threshold thì KHÔNG BAO GIỜ gọi academic, kể cả khi điểm legal cao chỉ do trùng từ khóa ngẫu nhiên (ví dụ câu hỏi "phương pháp điều chỉnh của LTTHS" match nhầm "Điều 1. Phạm vi điều chỉnh" điểm 0.7+ dù nội dung không liên quan, trong khi chunk academic đúng có điểm 0.73-0.78 nhưng không bao giờ được query tới). Đã sửa: bỏ short-circuit, LUÔN query song song cả legal_text và academic_reference rồi merge theo điểm, không loại trừ lẫn nhau — vì 2 nguồn trả lời 2 loại câu hỏi khác nhau (quy định pháp luật vs lý luận/khái niệm), điểm cao ở 1 nguồn không có nghĩa nguồn kia không cần thiết. Rẻ hơn (chỉ thêm 1 query Qdrant mỗi lượt) và tổng quát hơn nhiều so với vá thêm từ khóa vào ANALYTICAL_INTENT_KEYWORDS (sẽ tiếp tục vỡ với câu hỏi lý thuyết mới chưa liệt kê — cùng loại lỗi heuristic đã gặp và từ bỏ ở Phase 3 title-truncation).

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

Phase 4 Extension 2 — Lưu/khôi phục lịch sử hội thoại (sau deadline 05/09)
Bối cảnh: phát hiện Sidebar vẫn hiển thị 3 conversation hardcode từ Phase 8 (mock, chưa từng thay bằng dữ liệu thật), chat/page.tsx không lưu/tải lại lịch sử — rời trang là mất hội thoại hiện tại, kể cả trong cùng phiên trình duyệt. Đây là tính năng CHƯA TỪNG được build phần đọc (không phải bug) — dữ liệu để dựng lại lịch sử đã có sẵn trong chat_query_logs (conversation_id đã thêm từ Phase 4 Extension), chỉ thiếu tầng đọc + hiển thị.

[ ] GET /api/chat/conversations — liệt kê danh sách conversation của user, group theo conversation_id (GROUP BY trên Postgres), mỗi group trả về id, tiêu đề (lấy từ câu hỏi đầu tiên của conversation đó, có thể cắt ngắn), thời gian cập nhật gần nhất — sắp xếp mới nhất trước
[ ] GET /api/chat/conversations/{conversation_id} — toàn bộ turns (câu hỏi + câu trả lời) của 1 conversation cụ thể, theo đúng thứ tự thời gian — tái sử dụng phần lớn logic của get_recent_turns (chat_log_service.py) nhưng bỏ giới hạn 3 turns, xác nhận chỉ trả về conversation thuộc đúng user đang gọi (không để user A đọc được lịch sử của user B — kiểm tra ownership theo user_id trong token JWT)
[ ] Sidebar.tsx: xóa MOCK_CONVERSATION_HISTORY, gọi GET /api/chat/conversations thật, mỗi item có onClick điều hướng vào đúng conversation đó
[ ] Route/URL: quyết định dùng /chat/[conversationId] (dynamic route) hoặc query string /chat?conversation=xxx — tự chọn cách phù hợp với cấu trúc App Router hiện có, miễn nhất quán
[ ] chat/page.tsx: khi có conversationId từ URL, gọi GET /api/chat/conversations/{id} để tải lại toàn bộ messages trước khi render, thay vì luôn khởi tạo rỗng
[ ] Nút "Hội thoại mới" ở Sidebar: xác nhận điều hướng về /chat không kèm conversationId, tạo conversationId mới cho lượt hỏi tiếp theo (đúng hành vi hiện có, chỉ cần xác nhận không bị ảnh hưởng bởi thay đổi này)
[ ] Verify E2E sạch (theo đúng quy tắc đã thêm ở mục 8 sau sự cố mock-data trước đây): tài khoản Supabase thật, NEXT_PUBLIC_USE_MOCK_DATA=false — hỏi 2-3 câu, chuyển sang Dashboard rồi quay lại /chat, xác nhận hội thoại vẫn còn (không mất), bấm vào conversation cũ trong Sidebar xác nhận tải đúng nội dung, tạo conversation mới xác nhận không lẫn với conversation cũ

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

Phase 5a/5b v2 — Tái cấu trúc theo yêu cầu mới từ nhóm luật (đang chờ ngân hàng đề mới, chưa có backend, chỉ build UI bằng mock trước)
Thay đổi so với Phase 5a/5b gốc đang chạy thật:
- Trắc nghiệm: bỏ 15 câu mcq_true_false ra khỏi quiz_set (chuyển hẳn sang thành ngân hàng "Bán trắc nghiệm" bên Tự luận). Còn lại 75 câu mcq_4choice thuần túy, mix ngẫu nhiên chia thành 15 bộ đề mới, mỗi bộ 5 câu (thay vì 5 bộ × 18 câu như hiện tại).
- Tự luận: không còn là 1 pool phẳng — chia thành 4 ngân hàng theo category: "Lý thuyết", "Vận dụng", "Bán trắc nghiệm" (nhận 15 câu mcq_true_false chuyển từ trắc nghiệm sang, đổi format từ chọn Đúng/Sai thành trả lời tự do + giải thích), "Tình huống". Mỗi ngân hàng làm riêng, 1 câu/lượt.
- Minigame "Tôi hỏi bạn trả lời": UI riêng, lấy ngẫu nhiên 1 câu từ toàn bộ pool tự luận (không giới hạn theo 1 category cụ thể), có nút "Câu khác" để bỏ qua không tính điểm — quyết định cần chốt: bấm "Câu khác" có ghi nhận vào lịch sử/thống kê hay hoàn toàn bỏ qua (nghiêng về hoàn toàn bỏ qua, không tính là 1 lượt làm bài).
- Số liệu chính xác từng ngân hàng (bao nhiêu câu Lý thuyết/Vận dụng/Tình huống) phụ thuộc ngân hàng đề mới nhóm luật đang tổng hợp — CHƯA CÓ, chỉ có ngân hàng "Bán trắc nghiệm" (15 câu, đã có sẵn từ dữ liệu cũ).

[x] Bước 1 (ĐÃ HOÀN THÀNH): build UI 3 màn hình mới (chọn bộ trắc nghiệm 15 bộ, chọn ngân hàng tự luận 4 loại, minigame Tôi hỏi bạn trả lời) dựa theo Figma export trong design/figma-export/, dùng mock data cục bộ (mockDataV2.ts, tách biệt hoàn toàn khỏi NEXT_PUBLIC_USE_MOCK_DATA/lib/api.ts/lib/mockData.ts) — CHƯA đụng vào backend/quiz_service.py/essay_service.py hiện có (vẫn chạy đúng, chỉ frontend tạm không trỏ vào)
[ ] QUYẾT ĐỊNH QUAN TRỌNG: việc build UI mock này tạm thời route /quiz và /essay khỏi backend thật đang chạy (đã verify hoạt động đúng qua UAT-readiness trước đó) — chỉ chấp nhận được vì UAT với nhóm luật CHƯA bắt đầu. Phải hoàn thành Bước 2 (backend thật) TRƯỚC khi bắt đầu UAT, không được để nhóm luật UAT trên bản mock

Phát hiện phụ khi verify Bước 1 (không phải lỗi của 3 trang mới, ghi lại để không quên): Sidebar không tự thu gọn ở mobile viewport (< tablet) — hạn chế có sẵn của AuthenticatedLayout toàn app (Chat/Dashboard cũng vậy), chưa từng được kiểm tra kỹ trên mobile thật. Đáng làm thành 1 việc QA riêng trước UAT (đã note nhu cầu QA mobile Quiz/Essay từ trước, giờ mở rộng thêm phạm vi sang cả khung Sidebar).
[x] Bước 2 — ĐANG LÀM, dữ liệu thật đã nhận: 
    - Ngân hàng đề mới "Tôi hỏi bạn trả lời(2).pdf" — đã có đủ 4 category (Lý thuyết/Vận dụng/Bán trắc nghiệm/Tình huống), gồm cả câu cũ lẫn câu mới trộn lẫn. Toàn bộ nội dung file này đi vào Tự luận (4 ngân hàng), thay thế hẳn cách tổ chức essay cũ (pool phẳng 30 câu + 15 mcq_true_false riêng biệt) — cần đối chiếu xem 15 câu Nhận định Đúng/Sai cũ và 30 câu tự luận cũ có bị trùng/đã được gộp vào file mới hay không trước khi quyết định giữ/bỏ dữ liệu cũ (không giả định, kiểm tra thật như đã làm mọi lần trước).
    - 8 file PDF mới bổ sung cho corpus RAG (Qdrant) — CHƯA rõ loại (legal_text hay academic_reference), cần phân loại bằng nội dung thật như đã làm ở Phase 3 gốc, không đoán theo tên file.
    - MCQ: quyết định cuối cùng — XÓA hẳn 15 câu mcq_true_false khỏi trắc nghiệm (không chuyển đổi qua lại nữa), chỉ giữ 75 câu mcq_4choice gốc (5 bộ × 15 câu ban đầu, KHÔNG phải 5 bộ × 18 câu đã trộn Nhận định trước đây). Xáo trộn ngẫu nhiên 75 câu này, chia lại thành 15 bộ đề mới, mỗi bộ 5 câu — khớp đúng thiết kế UI đã build ở Bước 1.
[ ] parse_question_bank.py viết lại: parse "Tôi hỏi bạn trả lời(2).pdf" theo 4 category, tận dụng bullet "Từ khóa cho bài học" như đã làm ở lần đầu nếu format tương tự (kiểm tra format thật trước, không giả định giống hệt file cũ). Reshuffle 75 câu MCQ thành 15 bộ × 5.
[ ] parse_law.py mở rộng: phân loại + ingest 8 file mới vào corpus, theo đúng pipeline OCR fallback 2 tầng (Gemini Vision → Tesseract) đã có nếu gặp file scan/lỗi font tương tự 12 file đầu
[ ] Redesign question_bank_service.py: quiz rotation chọn ngẫu nhiên 5/75 câu cho mỗi lượt tạo bộ (hoặc dùng 15 bộ cố định đã chia sẵn — quyết định lúc build dựa trên cách đã thiết kế UI Bước 1, ưu tiên khớp đúng "15 bộ cố định" vì UI đã hiển thị theo bộ số 01-15 có trạng thái lưu lại, không phải sinh động mỗi lần); essay rotation filter theo category
[ ] Migration: thêm cột category vào bảng câu hỏi tự luận
[ ] Nối backend thật vào UI Quiz v2/Essay v2 đã build ở Bước 1 (đang mock) — thay mockDataV2.ts bằng gọi API thật, xóa comment TODO đã đánh dấu
[ ] Cập nhật Phase 7 v2 dashboard: thay mock ở Khối 1 (MCQ progress ring) và Khối 2 (4 tracker tự luận) bằng data thật, xóa TODO tương ứng
[ ] Verify E2E sạch đầy đủ theo quy tắc đã có TRƯỚC khi coi Bước 2 xong — đây là điều kiện bắt buộc để bắt đầu UAT với nhóm luật

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

Phase 7 v2 — Redesign dashboard (logic đã chốt, đi kèm Quiz v2/Essay v2, một phần vẫn mock cho tới khi Bước 2 backend xong)
Vấn đề bản cũ: 3 stat card ngang hàng đều nhau, không có trọng tâm, không dẫn tới hành động cụ thể — "báo cáo số liệu" thay vì "định hướng học tập".

Cấu trúc mới đã chốt:
- Hero — Gợi ý hành động: nếu có weak-topic (dữ liệu THẬT từ GET /api/dashboard/weak-topics, không đổi), gợi ý chủ đề điểm thấp nhất + CTA dẫn vào ngân hàng tự luận liên quan (map topic_category → 1 essay bank chứa câu hỏi topic đó — mapping này tạm dùng mock vì Essay v2 category thật chưa có backend). Nếu chưa có weak-topic (user mới), CTA chung: "Bắt đầu với 1 bộ trắc nghiệm" (dẫn /quiz) hoặc "Hỏi trợ lý AI" (dẫn /chat).
- Khối 1 — MCQ tổng hợp: progress ring lớn (dùng lại đúng component ring đã build ở Quiz v2), % đúng tổng thể + số bộ đã chạm/15. Dữ liệu MOCK (chờ Bước 2 backend Quiz v2).
- Khối 2 — 4 tracker tự luận song song: thanh tiến độ nhỏ mỗi ngân hàng (Lý thuyết/Vận dụng/Bán trắc nghiệm/Tình huống), hiện số câu đã luyện, KHÔNG hiện %/điểm (tự luận chấm rubric, không phải đúng/sai tuyệt đối, tránh gây hiểu lầm như điểm MCQ). Dữ liệu MOCK (chờ Bước 2 backend Essay v2).
- Khối 3 — Từ khóa hôm qua: giữ nguyên, dữ liệu THẬT, không đổi.
- Khối 4 — Chủ đề cần ôn lại: giữ nguyên nguồn dữ liệu THẬT (weak-topics), nhưng mỗi chủ đề thêm nút CTA dẫn thẳng vào ngân hàng tự luận tương ứng (thay vì chỉ hiển thị tên tĩnh như trước).

[ ] Redesign frontend theo cấu trúc trên, dùng lại component đã có (progress ring từ Quiz v2, card style từ Essay v2) — không tạo mới từ đầu
[ ] Đánh dấu rõ trong code phần nào dùng mock (Khối 1, Khối 2, phần mapping topic→bank ở Hero) vs phần nào dùng data thật (Khối 3, Khối 4, phần weak-topic detection ở Hero) — nhất quán với comment TODO đã dùng ở Phase 5a/5b v2 Bước 1
[ ] Khi Bước 2 (backend Quiz v2/Essay v2) hoàn thành, quay lại thay mock ở Khối 1/2 bằng data thật — không quên, ghi vào checklist Bước 2 luôn

Phase 8 — Frontend
[ ] Đọc frontend.md và các ảnh reference trong design/ trước khi build — bám theo design system (màu, spacing, component) nhưng áp dụng đúng các điểm "rút gọn" đã note, không build theo đúng 100% mockup nếu mockup vượt scope backend thật
[ ] Sidebar: thêm nav item "Trắc nghiệm" và "Tự luận" (2 trang riêng), cạnh "Tổng quan" và "Trợ lý AI" hiện có
[ ] Trang đăng nhập / đăng ký
[ ] Giao diện chat: ô nhập, lịch sử hội thoại, hiển thị câu trả lời kèm danh sách trích dẫn có thể thu gọn
[ ] Trang trắc nghiệm (MCQ): làm bài, xem điểm + giải thích
[ ] Trang tự luận: hiển thị câu hỏi, ô nhập câu trả lời tự do, sau khi submit hiển thị matched_points/missing_points/feedback/suggested_dieu rõ ràng, dễ đọc
[ ] Trang dashboard: từ khóa hôm qua, gợi ý chủ đề cần ôn (bản rút gọn theo Phase 7)
[ ] Loading state và thông báo lỗi cho mọi tác vụ async

Feature nhỏ — Xem toàn văn Điều luật từ citation pill (sau deadline 05/09, không phụ thuộc ngân hàng đề mới)
Bối cảnh: citation pill trong chat hiện chỉ hiện dieu_number + dieu_title, muốn đọc toàn văn phải hỏi lại chat. Dữ liệu đã có sẵn trong Qdrant, chỉ cần thêm tầng đọc.
[ ] GET /api/legal/articles/{dieu_number} — nhận thêm query param law_version hoặc source_document để phân biệt (vì cùng dieu_number có thể tồn tại ở nhiều văn bản khác nhau, đã gặp nhiều lần — BLTTHS/BLHS/Nghị định 250/Thông tư liên tịch). Lấy toàn bộ chunk cùng dieu_number + law_version từ Qdrant (có thể nhiều Khoản = nhiều chunk), ghép lại theo đúng thứ tự chunk_index, trả về toàn văn Điều đó
[ ] Route yêu cầu auth (JWT), nhất quán với các route khác trong app — không public
[ ] Frontend: click vào citation pill mở panel/modal hiển thị toàn văn Điều (dùng lại Card component + typography editorial đã có), không điều hướng rời khỏi trang chat hiện tại
[ ] Verify với case đã biết có nhiều văn bản trùng dieu_number (ví dụ Điều 13/15/23) — xác nhận click đúng pill nào mở đúng văn bản đó, không lẫn lộn
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
~~OAuth / đăng nhập mạng xã hội~~ — ĐÃ CHUYỂN VÀO SCOPE, xem Feature — Google OAuth Login bên dưới
Streaming câu trả lời real-time (WebSocket/SSE) — dùng HTTP request/response chuẩn
Giao diện admin quản lý văn bản (ingestion chỉ chạy qua CLI cho deadline này)
Multi-tenancy / quản lý tổ chức
Model reasoning liên luật phức tạp ngoài việc co-retrieval đơn giản (liên kết LTTHS ↔ LHS chỉ là "hiển thị thêm Điều liên quan từ cùng lượt tìm kiếm", không phải hệ thống reasoning riêng)
Giao diện quản lý phiên bản văn bản (document versioning)
Streak ngày học liên tiếp, breakdown tiến độ trắc nghiệm chi tiết theo nhiều nhóm chủ đề với circular progress riêng, gợi ý học tập có lý do cá nhân hóa theo ngữ cảnh hội thoại (xem frontend.md để biết bản đầy đủ dự kiến cho v2)
Chấm tự luận hoàn toàn tự do không dựa trên rubric (essay_key_points) — module tự luận ở Phase 5b luôn phải grounding vào rubric có sẵn trong ngân hàng đề, không để LLM tự quyết định đúng/sai theo cảm tính

Feature nhỏ — Sidebar mobile responsive + Chat empty state (sau deadline 05/09)
[ ] Sidebar không tự thu gọn ở mobile viewport (< tablet) — hạn chế có sẵn của AuthenticatedLayout toàn app, phát hiện lần đầu lúc verify Phase 5a/5b v2 Bước 1, lần 2 lúc verify Phase 7 v2 dashboard mobile. Cần: hamburger menu hoặc drawer/overlay pattern chuẩn cho mobile, không hiển thị sidebar cố định chiếm màn hình nhỏ như hiện tại
[ ] Chat empty state: khi vào /chat lần đầu (chưa có tin nhắn nào), hiện hướng dẫn ngắn gọn thay vì màn hình trống hoàn toàn — ví dụ: "Hỏi trực tiếp về 1 Điều luật, hoặc hỏi phân tích sâu — mọi câu trả lời đều có trích dẫn", kết hợp với suggestion chips tĩnh đã có sẵn (GET /api/chat/suggestions) làm điểm bắt đầu rõ ràng cho người dùng mới (đặc biệt quan trọng cho UAT với nhóm luật — họ cần hiểu ngay khả năng thật của bot)

Feature nhỏ — Xóa/đổi tên hội thoại + Sao chép câu trả lời (sau deadline 05/09)
Bối cảnh: Sidebar hiển thị lịch sử hội thoại thật (Phase 4 Extension 2) nhưng chưa có cách dọn dẹp — danh sách sẽ phình to vô hạn theo thời gian. Đây là thiếu sót chức năng, không phải cải tiến trải nghiệm thuần túy.

[ ] DELETE /api/chat/conversations/{conversation_id} — xác nhận ownership theo đúng pattern đã dùng ở GET detail (404 nếu không tồn tại hoặc không thuộc user gọi, không phân biệt 2 trường hợp để tránh lộ thông tin qua response khác nhau — đã áp dụng nguyên tắc này ở Phase 4 Extension 2, giữ nhất quán). Xóa toàn bộ chat_query_logs rows thuộc đúng conversation_id đó.
[ ] Frontend: nút xóa nhỏ hiện khi hover vào item lịch sử trong Sidebar (cả bản desktop lẫn mobile drawer vừa build), có xác nhận trước khi xóa thật (không xóa ngay khi bấm 1 lần, tránh xóa nhầm). Nếu đang xem đúng conversation vừa xóa (đang ở /chat/[id]), điều hướng về /chat sau khi xóa.
[ ] PATCH /api/chat/conversations/{conversation_id} — nhận { title: string }, cập nhật tiêu đề tùy chỉnh. Cần thêm cột title (nullable) vào bảng — nếu null, tiếp tục fallback lấy từ câu hỏi đầu tiên như hiện tại; nếu có giá trị, ưu tiên hiển thị title tùy chỉnh.
[ ] Frontend: cho phép sửa tên trực tiếp trong Sidebar (double-click hoặc icon edit nhỏ), input inline, lưu khi Enter/blur.
[ ] Nút "Sao chép" trên mỗi câu trả lời AI trong Chat — copy toàn văn câu trả lời (không kèm citation pill) vào clipboard, có feedback ngắn (icon đổi tạm thời hoặc toast nhỏ) xác nhận đã copy thành công.
[ ] Verify E2E sạch theo đúng quy tắc đã có (tài khoản thật, không mock): tạo vài hội thoại, đổi tên 1 cái, xóa 1 cái (xác nhận không còn trong danh sách, xác nhận API 404 khi cố gọi lại conversation đã xóa), test copy câu trả lời hoạt động đúng trên cả desktop và mobile.

Feature — PWA (Progressive Web App), phạm vi có giới hạn (sau deadline 05/09)
Quyết định phạm vi: app phụ thuộc hoàn toàn backend sống (RAG streaming, auth Supabase) — KHÔNG làm offline-first đầy đủ (giả vờ hoạt động khi mất mạng gây trải nghiệm tệ hơn không làm gì). Chỉ làm "installable app":
1. Cài vào màn hình chính được (manifest.json + icon nhiều cỡ, dùng lại logo Scale icon + palette navy/gold đã có, không cần thiết kế mới)
2. Cache tài nguyên tĩnh (JS/CSS/font) để load nhanh hơn lần mở sau
3. Trang fallback offline thân thiện ("Không có kết nối — vui lòng thử lại") khi mất mạng, thay vì lỗi trắng
4. KHÔNG cache/giả lập Chat/Quiz/Essay khi offline — các tính năng này luôn cần mạng thật, phải báo rõ ràng khi offline thay vì hiển thị dữ liệu cache cũ gây hiểu lầm

[ ] manifest.json: tên app, icon (192/512/apple-touch-icon), theme_color/background_color khớp palette editorial (navy #1E2460 hoặc ivory #F5F0E8, tự chọn hợp lý), display: standalone
[ ] Service worker: cache-first cho static assets, network-only cho mọi API call (/api/*) — không cache response API dù là GET, vì dữ liệu (chat, quiz, dashboard) luôn cần mới nhất
[ ] Trang/màn hình fallback khi offline
[ ] Icon set: tạo từ chính logo Scale icon hiện có (lucide-react trong khung bg-primary), render ra các cỡ cần thiết — không cần thiết kế mới qua Figma
[ ] Verify: cài thử trên điện thoại thật (hoặc Chrome DevTools Application tab mô phỏng), xác nhận installable, icon hiển thị đúng, tắt mạng xác nhận fallback offline hiện đúng còn API call thật vẫn network-only không bị cache sai

Feature — Mobile Responsive UI toàn app (song song với Bước 2, không phụ thuộc dữ liệu)
Bối cảnh: Sidebar mobile đã có drawer pattern (feature trước), nhưng chưa audit toàn diện responsive cho nội dung chính từng trang (Chat, Quiz v2 grid 15 bộ, Essay v2 4 category card, Dashboard 4 khối, câu hỏi/form dài).
[ ] Audit từng trang ở viewport mobile thật (< 768px): Welcome/Sign in/Sign up (đã làm trước, xác nhận lại), Chat (bong bóng tin nhắn, citation pill, input), Quiz set grid + màn làm bài, Essay bank cards + màn làm bài + minigame, Dashboard 4 khối (đặc biệt Hero và 2 hàng card đôi)
[ ] Sửa các điểm vỡ layout phát hiện được — ưu tiên: không tràn ngang (horizontal scroll không mong muốn), touch target đủ lớn (tối thiểu 44x44px), text không bị quá nhỏ để đọc
[ ] Verify bằng viewport thật (điện thoại qua LAN, hoặc Playwright mobile viewport) cho từng trang, không chỉ resize DevTools qua loa

Bước A (Phase 5a/5b v2) — ĐÃ HOÀN THÀNH: ingest 5 file mới + thay thế Giáo trình bản chất lượng thấp
- Xóa 1030 chunk cũ "Giáo trình Luật Tố tụng hình sự -đã nén.pdf", thay bằng bản mới chất lượng tốt hơn (722 chunk, không lỗi font).
- Ingest 4 file mới: Luật tổ chức tòa án nhân dân (171 chunk, legal_text), Tình huống tố tụng hình sự (14 chunk, academic_reference), 784492208-Đề cương (64 chunk, academic_reference), Đề cương ôn tập theo chương (139 chunk, academic_reference).
- Tổng corpus: 2645 chunk, 2639 point Qdrant (6 chunk unusable không embed, gồm 5 chunk cũ đã biết + Điều 152 Luật tổ chức TAND mới phát hiện — lỗi font gốc + RECITATION chặn OCR fallback, chấp nhận vì nội dung ít khả năng bị hỏi).
- Bỏ qua 3 file trùng lặp với corpus đã có (Thông tư liên tịch 05, Nghị định 250 (1), Thông tư liên tịch 01/2026 (1)) — không ingest.

3 bug phát hiện khi spot-check "Luật tổ chức tòa án nhân dân" (văn bản legal_text hoàn toàn mới, không có sẵn known-fix list):
1. Số chú thích dính liền tiêu đề Điều bãi bỏ (Điều 63, 79, 82) — đã sửa.
2. NGHIÊM TRỌNG: Điều 150 trích dẫn nguyên văn "Điều 116" của Luật Thi hành án dân sự làm ví dụ minh họa (thiếu dấu ngoặc kép mở trong PDF gốc) — bị parser nhận nhầm là Điều 116 thật, ĐÈ LÊN Điều 116 thật ("Thư ký Tòa án") và cắt cụt Điều 150. Đây là loại lỗi nguy hiểm nhất đã gặp trong toàn dự án: không mất dữ liệu (dễ phát hiện) mà THAY THẾ dữ liệu đúng bằng dữ liệu sai, trông vẫn hợp lệ. Đã sửa bằng danh sách loại trừ tường minh + assert tự báo lỗi nếu PDF gốc đổi.
3. Điều 150 (sau khi sửa bug #2) vẫn bị tách khoản tự động, sinh khoản trùng số do văn bản trích dẫn lồng nhau có đánh số riêng → đụng độ point ID Qdrant, 7/182 chunk sẽ âm thầm mất khi upsert. Đã sửa: giữ Điều 150 làm 1 chunk duy nhất không tách khoản.

Bài học: với văn bản legal_text mới không có known-fix list sẵn, BẮT BUỘC spot-check kỹ ngay từ lần ingest đầu tiên (không đợi phát hiện qua RAG chat như các bug trước) — đặc biệt cảnh giác với Điều luật có nội dung trích dẫn văn bản pháp luật khác bên trong (dễ gây nhận nhầm số Điều).

Chuỗi audit dữ liệu sau Bước A (đáng đưa vào phần Methodology/Data Quality của bài báo)
Phát hiện xuất phát từ 1 câu hỏi đơn giản ("vì sao Giáo trình mới ít chunk hơn bản cũ, vì sao unusable không rescue"), dẫn tới chuỗi điều tra hé lộ 1 khoảng trống đã tồn tại từ Phase 3 và 1 bug hệ thống mới:

1. Giáo trình mới (722 chunk) ít hơn bản cũ (1030 chunk) — xác nhận bằng đo garbage-ratio (is_text_garbage): bản cũ 99.8% trang garbage do lỗi hỏng font "nén" file gốc (không phải thiếu nội dung — đối chiếu mục lục/tác giả từng chương khớp 100% giữa 2 bản). Số chunk ít hơn ở bản mới hoàn toàn do chunker gộp đúng thành đoạn văn mạch lạc khi text sạch, đúng target design ~1288 ký tự/chunk.

2. Rescue tầng 2 (Tesseract fallback cho chunk unusable) CHƯA TỪNG được chạy trong toàn bộ dự án — tồn tại từ Phase 3 dưới dạng "one-off recovery script" (rescue_unusable_chunks.py) nhưng không ai từng thực thi cho tới lượt audit này. Không phải hồi quy do Bước A gây ra.

3. Khi chạy rescue lần đầu, phát hiện bug hệ thống nghiêm trọng hơn cả vấn đề OCR: chunking.py tính extraction_quality theo TOÀN BỘ Điều (span đầu-cuối), không theo từng Khoản riêng — khiến các Khoản hoàn toàn sạch (nằm trọn trên trang tốt) bị gắn nhầm "unusable" oan chỉ vì 1 Khoản khác của cùng Điều chạm trang lỗi. Đã sửa: tính quality theo từng Khoản độc lập. Quét lại toàn bộ 6 văn bản legal_text (1543 chunk) xác nhận chỉ 2 vị trí bị ảnh hưởng (TT01 Điều 39, Luật tổ chức TAND Điều 152) — không lan rộng hơn.

4. Trong lúc dọn dẹp, đối chiếu số liệu chunks.json (2645) vs Qdrant (2644) phát hiện thêm 1 lỗi in ấn thật trong chính văn bản gốc "Văn bản hợp nhất BLHS 2015.pdf": Điều 189 Khoản 3 xuất hiện lặp 2 lần liền kề trong bản PDF chính phủ công bố (không phải lỗi trích xuất của dự án) — 1 bản dùng thuật ngữ "hàng phạm pháp" (chỉ xuất hiện đúng 1 lần/toàn văn bản, xác định là câu chữ nháp sót lại), 1 bản dùng "vật phạm pháp" (xuất hiện 22 lần xuyên suốt, đúng thuật ngữ chuẩn/hiện hành). Qdrant tình cờ giữ đúng bản hiện hành do thứ tự upsert — đã sửa loại trừ tường minh bản sai, không còn phụ thuộc vào sự tình cờ này.

Bài học tổng quát: (a) 1 script "one-off, chưa từng chạy" trong pipeline có thể ẩn giấu bug thật lâu dài — đáng định kỳ tự hỏi "cơ chế này có thực sự đang hoạt động, hay chỉ tồn tại trên giấy"; (b) tính toán ở cấp "toàn bộ Điều" cho 1 thuộc tính vốn có thể khác nhau ở cấp "từng Khoản" (extraction_quality) là 1 dạng lỗi khái quát hóa sai phạm vi, nên rà soát khi thiết kế field metadata; (c) văn bản pháp luật do chính cơ quan nhà nước công bố vẫn có thể chứa lỗi in ấn thật (không phải luôn là lỗi từ phía công cụ xử lý), cần cơ chế phát hiện qua tần suất thuật ngữ/đối chiếu chứ không mặc định tin tưởng nguồn.

Số liệu cuối cùng sau toàn bộ Bước A: 2644 chunk, 2644 point Qdrant, khớp tuyệt đối, 0 unusable, 0 point ID trùng lặp.

Bước B — Xử lý Bộ 7 thiếu 1 câu (sau khi xóa mcq4-set7-q4 trùng lặp)
Quyết định: KHÔNG phục hồi câu trùng, KHÔNG rút câu từ bộ khác — soạn 1 câu MCQ mới bằng LLM để đắp đủ 5 câu cho Bộ 7. Đây là lần đầu tiên dự án để LLM tự soạn nội dung câu hỏi mới (khác hẳn việc chuẩn hóa/trích xuất từ nguồn có sẵn đã làm xuyên suốt từ Phase 5a) — áp ràng buộc chặt:
[ ] Câu mới PHẢI grounding vào đúng 1 Điều luật thật có trong corpus Qdrant (không tự bịa tình huống/quy định) — chọn 1 Điều liên quan chủ đề tương tự các câu khác trong Bộ 7 nếu hợp lý (quyền bào chữa), lấy nguyên văn nội dung Điều đó làm cơ sở soạn câu hỏi + 4 đáp án (1 đúng, 3 nhiễu hợp lý)
[ ] Đáp án đúng phải trích dẫn/diễn giải chính xác nội dung Điều đã chọn, không suy diễn thêm
[ ] BẮT BUỘC hiển thị đầy đủ câu hỏi mới (câu hỏi, 4 đáp án, đáp án đúng, Điều luật căn cứ) để người dùng duyệt trước khi thêm vào question_bank.json — không tự động chấp nhận, đúng quy trình spot-check đã áp dụng cho mọi dữ liệu câu hỏi khác trong dự án

Feature — Google OAuth Login (sau deadline 05/09)
Bối cảnh: đã cố tình cắt khỏi scope từ đầu (từng chủ động xóa nút Google khỏi mockup Figma lúc build lại Welcome/Sign in/Sign up). Giờ quay lại làm thật theo yêu cầu.
Setup thủ công (đã làm ngoài phạm vi code, không phải việc của Claude Code): OAuth Client ID tạo trên Google Cloud Console, redirect URI trỏ đúng Supabase callback (https://<project-ref>.supabase.co/auth/v1/callback), bật Google provider trên Supabase Dashboard với Client ID/Secret.
[ ] Thêm nút "Tiếp tục với Google" vào Sign in/Sign up, dùng supabase.auth.signInWithOAuth({ provider: 'google' }) — giữ nguyên style editorial đã có (không phá vỡ layout hiện tại của 2 trang)
[ ] Xử lý redirect callback đúng — Supabase tự redirect về app sau khi Google xác thực xong, xác nhận route callback (thường /auth/callback hoặc xử lý ngay tại root qua onAuthStateChange) hoạt động đúng, điều hướng vào /dashboard sau khi login thành công
[ ] Xử lý case user đăng nhập Google lần đầu — Supabase tự tạo user mới, xác nhận không có bước nào trong luồng app giả định user phải qua /register trước (kiểm tra logic hiện có có chặn nhầm user OAuth mới không)
[ ] Verify E2E: đăng nhập Google thật (dùng tài khoản Google thật của người test, không giả lập), xác nhận vào được /dashboard, session hoạt động bình thường với mọi API (Chat/Quiz/Essay) như user email/password

Feature — Redesign Dashboard Hero: rotation 3 loại gợi ý + dọn UX clarity (sau deadline 05/09)
Bối cảnh: Hero hiện tại (Phase 7 v2) chỉ gợi ý theo weak-topic essay, cố định — cảm thấy hạn chế, không phản ánh đủ 3 mảng hoạt động (MCQ/Essay/Minigame). Đồng thời phát hiện 2 lỗi UX clarity nhỏ khác.

[ ] Hero rotation — 3 variant xoay tuần tự mỗi lần user vào lại /dashboard hoặc refresh (dùng localStorage lưu index xoay vòng 0→1→2→0..., không cần backend, đây là state UI thuần túy không phải dữ liệu nhạy cảm):
  - Variant 1 (Essay): gợi ý ngân hàng tự luận theo weak-topic (logic đã có), hiện kèm tiến độ ngân hàng đó (X/Y câu đã luyện)
  - Variant 2 (MCQ): hiện tiến độ MCQ tổng hợp (X/15 bộ đã làm, % đúng — lấy từ đúng data source Khối 1 hiện có), gợi ý làm tiếp bộ đề tiếp theo
  - Variant 3 (Minigame): gợi ý thử "Tôi hỏi bạn trả lời", CTA dẫn /essay/practice — không cần hiện tiến độ (minigame không track hoàn thành theo thiết kế)
  - Giữ nguyên nhánh fallback cho user hoàn toàn mới (chưa có weak-topic data): chỉ xoay vòng Variant 2/3 (bỏ Variant 1 vì chưa có weak-topic để gợi ý), hoặc dùng đúng CTA chung đã có sẵn từ thiết kế gốc
  - QUAN TRỌNG: kiểm tra lại mapWeakTopicToEssayBankCategoryMock — xác nhận đã dùng category thật từ question_bank.json (Lý thuyết/Vận dụng/Bán trắc nghiệm/Tình huống) hay vẫn còn mock từ trước khi Bước 2 hoàn thành, sửa nếu còn mock

[ ] "Từ khoá hôm qua": thêm chữ "Điều" trước số Điều trong chip (hiện chỉ hiện "16 · ...", đổi thành "Điều 16 · ...")

[ ] "Chủ đề cần ôn lại": bỏ badge % hiển thị cạnh tên chủ đề — chỉ giữ tên chủ đề + nút "Ôn tập", vì % không cần thiết cho UI này (logic filter "cần ôn lại" đã dùng % nội bộ, không cần phơi ra UI gây rối mắt, đặc biệt khi trộn lẫn dữ liệu MCQ (đúng/sai tuyệt đối) và Essay (chấm rubric) dưới cùng 1 con số % dễ gây hiểu lầm)

[ ] "Chủ đề cần ôn lại" — nút "Ôn tập" đổi hành vi: điều hướng vào /chat (hội thoại mới) và TỰ ĐỘNG gửi 1 câu hỏi về đúng chủ đề đó (ví dụ topic "Phạm vi điều chỉnh" → câu hỏi tự động "Phạm vi điều chỉnh của Luật Tố tụng Hình sự là gì?" hoặc template linh hoạt hơn "Giải thích cho tôi về: {topic}" để chịu được nhiều dạng phrasing khác nhau của topic_category, không chỉ noun-phrase ngắn). Query tự động này đi qua đúng pipeline Query Understanding đã có (rewrite_question), không cần xử lý riêng.
  Lý do phân biệt có chủ đích với Hero Variant 1 (cũng gợi ý weak-topic nhưng dẫn vào luyện tập tự luận): Hero = "làm bài" (hành động luyện tập), "Chủ đề cần ôn lại" → Chat = "hiểu lại khái niệm" (hành động ôn khái niệm trước khi luyện tập) — 2 hành động bổ trợ nhau, không phải trùng lặp/không nhất quán.
  Kỹ thuật: truyền topic qua query param khi điều hướng (/chat?q=<encoded>), ChatView đọc param lúc mount, tự fill + tự gửi (không chỉ prefill chờ user bấm gửi), sau đó clear param khỏi URL (router.replace) để tránh gửi lặp khi refresh/back.

Feature — Cải thiện retrieval cho câu hỏi vận dụng/tình huống dài (fix ngay, không để dành v2)
Bối cảnh: test 3 câu thật (vandung-q7, vandung-q26, tinhhuong-q4) cho thấy generation trung thực (không bịa, biết từ chối đúng lúc) nhưng retrieval là điểm nghẽn — câu hỏi dài/nhiều dữ kiện bị nhiễu bởi chi tiết thủ tục bề mặt lặp lại trong câu hỏi, bỏ lỡ Điều luật chứa nguyên tắc cốt lõi. Nặng nhất ở tinhhuong-q4 (bỏ lỡ Điều 109/123, vớt nhầm Điều 165/110 + 1 Thông tư về thủ tục).

Chiến lược: 2 bước leo thang, chỉ làm Bước 2 nếu Bước 1 không đủ — tránh nhảy thẳng vào thay đổi kiến trúc lớn khi chưa thử giải pháp đơn giản.

[ ] Bước 1 — Mở rộng top_k cho legal_text semantic search khi câu hỏi dài (ngưỡng độ dài cần xác định, ví dụ >200-300 ký tự câu hỏi gốc): tăng LEGAL_SEMANTIC_TOP_K/LEGAL_PRIMARY_COUNT động thay vì cố định — giả thuyết: Điều đúng có thể đã nằm trong corpus nhưng bị xếp hạng thấp do nhiễu, không hoàn toàn biến mất khỏi kết quả retrieval, mở rộng vùng vớt có thể đủ.
  Test lại CHÍNH XÁC 3 câu đã dùng để chẩn đoán (vandung-q7, vandung-q26, tinhhuong-q4) — xác nhận tinhhuong-q4 giờ có vớt được Điều 109/123 trong top-k mở rộng không.
  Chạy lại toàn bộ 29 câu evaluation — xác nhận KHÔNG hồi quy (đặc biệt citation precision không bị pha loãng do vớt thêm nhiều chunk không liên quan cho câu ngắn vốn đã hoạt động tốt — chỉ áp dụng ngưỡng mở rộng cho câu ĐỦ DÀI, không áp dụng toàn cục).

[ ] Bước 2 (CHỈ làm nếu Bước 1 không đủ, xác nhận bằng cách test lại đúng 3 câu) — mở rộng Query Understanding (đã có từ Phase 4 Extension) để chắt lọc thêm 1 "câu hỏi cốt lõi" tập trung vào nguyên tắc pháp lý, tách khỏi chi tiết tình huống, dùng riêng cho bước retrieval — giữ nguyên câu hỏi gốc đầy đủ cho bước generation cuối (để model vẫn áp dụng đúng vào tình huống cụ thể). Tái dùng hạ tầng rewrite_question đã có, không xây pipeline song song mới.
  Cùng yêu cầu test: 3 câu chẩn đoán + toàn bộ 29 câu evaluation, không hồi quy.

Verify cuối: sau khi 1 trong 2 bước đạt yêu cầu (hoặc cả 2 nếu cần), cập nhật lại bảng chẩn đoán 3 câu trong requirements.md với kết quả MỚI, để có trước/sau rõ ràng cho phần Discussion của bài báo.

Feature — Tăng "impact" LLM cho câu hỏi dài/phức tạp (tiếp nối Bước 1 retrieval, tận dụng ngân sách Gemini còn dư)
Bối cảnh: Bước 1 (mở rộng top_k) đã giải quyết retrieval cho câu hỏi dài. Giờ cải thiện thêm ở tầng generation cho đúng nhóm câu hỏi này — tái dùng cờ is_long_question đã có (>250 ký tự), không cần logic phát hiện mới.

[x] Model routing động: câu hỏi dài (is_long_question=true) chuyển sang gọi model Gemini mạnh hơn cho bước generation cuối (không đụng model dùng cho embedding/query understanding — chỉ generation cuối). Câu ngắn/tra cứu trực tiếp giữ nguyên model rẻ hiện tại (đã kiểm chứng tốt qua evaluation). Thêm biến môi trường mới (ví dụ GEMINI_CHAT_MODEL_COMPLEX), mặc định fallback về GEMINI_CHAT_MODEL hiện tại nếu không set (backward compatible, không phá vỡ gì nếu chưa cấu hình).

[x] Chain-of-thought có cấu trúc cho câu hỏi dài: thêm đoạn hướng dẫn vào system prompt (CHỈ áp dụng khi is_long_question=true, không đổi prompt cho câu ngắn) — khuyến khích model lập luận tường minh theo bước: (1) xác định các sự kiện/tư cách pháp lý của các bên trong tình huống, (2) đối chiếu từng sự kiện với điều kiện luật định trong context, (3) mới đưa ra kết luận. Mục đích: làm hành vi lập luận từng bước đã quan sát tự nhiên ở tinhhuong-q4 trở nên nhất quán, không phụ thuộc may rủi.

ĐÃ HOÀN THÀNH. Implementation:
- `backend/app/core/config.py`: `gemini_chat_model_complex: str | None` (alias `GEMINI_CHAT_MODEL_COMPLEX`), property `resolved_complex_chat_model` fallback về `gemini_chat_model`.
- `backend/app/prompts/rag_prompts.py`: `RAG_LONG_QUESTION_COT_ADDENDUM` + `build_system_prompt(is_long_question)`.
- `backend/app/services/rag_service.py`, `stream_answer_question()`: chọn `system_prompt`/`generation_model` theo `is_long_question` (cùng ngưỡng 250 ký tự của Bước 1).

Model chọn: `gemini-3.1-pro-preview`. Đã search danh sách model thật qua Gemini API (không đoán theo
tên cũ) — `gemini-2.5-pro` và `gemini-3-pro-preview` đều đã bị deprecate (404 "no longer
available"). **`gemini-3.1-pro-preview` là lựa chọn Pro-tier duy nhất còn hoạt động tại thời điểm
implement — hiện KHÔNG có bản GA (non-preview) nào của dòng Pro khả dụng qua API key này.** Dùng
model preview là quyết định buộc phải chấp nhận (không có lựa chọn GA thay thế), không phải sơ suất
chọn nhầm — hệ quả trực tiếp là độ trễ cao và dao động lớn (503 "high demand" khá thường xuyên), xử
lý ở mục fallback bên dưới.

Test cô lập biến số (yêu cầu bổ sung giữa chừng, trước khi chốt): so sánh CoT-only+flash-lite riêng
(tắt model routing) với CoT+pro-preview trên 4 câu tình huống — kết luận CoT một mình (không đổi
model) hầu như không cải thiện gì so với baseline gốc, cả nội dung, trích dẫn, lẫn xu hướng "hedge"
gần như giống hệt nhau. Chỉ pro-preview mới cho tính quyết đoán (kết luận dứt khoát khớp văn phong
ground truth) và khả năng nắm bắt điểm mấu chốt pháp lý tinh vi (ví dụ: chỉ pro-preview nhận ra
"gián đoạn thời gian phá vỡ tính quả tang" ở tinhhuong-q9 - cả 2 bản flash-lite đều bỏ lỡ hoàn toàn
insight này). Kết luận: pro-preview thực sự cần thiết, không phải chỉ do cấu trúc CoT.

[x] Fallback tự động pro-preview → flash-lite khi timeout/lỗi, cho câu hỏi dài. Do quyết định dùng
model preview ở trên đánh đổi lấy độ trễ cao/dao động lớn (5s-68s quan sát được) và tần suất 503 "high
demand" đáng kể, bổ sung bước leo thang thứ 3 (ngoài kế hoạch ban đầu, phát sinh từ chính số liệu đo
được ở bước model routing) để chặn trần latency mà không mất khả năng dùng pro-preview khi nó phản
hồi bình thường.

Implementation: `backend/app/services/gemini_client.py`, `stream_generate_answer()` nhận thêm
`fallback_model` + `first_token_timeout`. Có deadline TUYỆT ĐỐI (tính một lần trước khi mở kết nối)
bao trùm cả bước mở kết nối/chờ header lẫn bước chờ token đầu tiên. Nếu model chính (pro-preview) gặp
503/429/lỗi mạng/hết deadline mà CHƯA gửi token nào cho client, chuyển ngay (không backoff — bản thân
việc fallback đã là cách phục hồi) sang model dự phòng (flash-lite, vẫn giữ nguyên system prompt CoT).
Model cuối cùng trong chuỗi giữ nguyên retry-với-backoff cũ (3 lần) — nơi gọi không truyền
fallback_model (mọi nơi khác ngoài đường câu dài) không đổi hành vi. Một khi đã có token nào được gửi
cho client, không retry/fallback nữa (tránh lặp nội dung) — lỗi ở giai đoạn đó truyền thẳng ra ngoài
như cũ. `backend/app/services/rag_service.py`: `LONG_QUESTION_FIRST_TOKEN_TIMEOUT_SECONDS = 18.0`
(giữa khoảng 15-20s được đề xuất).

2 bug phát hiện và sửa trong lúc implement (case study - đúng dạng bug "tưởng đúng logic nhưng chỉ lộ
khi đo số liệu thật" đã lặp lại nhiều lần trong dự án này, ví dụ tương tự ở Phase 4/6 với payload index
và ở Bước 1/2 của feature retrieval phía trên):
1. Bản đầu tiên đặt timeout riêng cho MỖI lần gọi `anext()` trên iterator dòng SSE thay vì một deadline
   tuyệt đối - dòng đệm/dòng rỗng (keep-alive, candidate rỗng) liên tục "làm mới" đồng hồ đếm, khiến
   tổng thời gian chờ trước token thật vượt xa ngưỡng dự kiến (đo được: 38s+ dù đặt ngưỡng 18s). Sửa
   bằng cách tính deadline một lần duy nhất trước vòng lặp, dùng thời gian còn lại (remaining) cho mỗi
   lần chờ thay vì reset lại timeout đầy đủ.
2. Sau khi sửa (1), vẫn đo được thời gian vượt ngưỡng (21-25s dù đặt 18s) - vì deadline chỉ bắt đầu
   tính SAU KHI đã nhận response header, trong khi TTFB (thời gian chờ header) mới chính là phần chậm
   nhất của gemini-3.1-pro-preview (14-20s quan sát được qua log thời gian giữa các lệnh gọi Gemini kế
   tiếp nhau) - một deadline chỉ tính từ lúc đã có header sẽ bỏ lọt đúng phần trễ mà cơ chế fallback
   này sinh ra để chặn. Sửa bằng cách bọc luôn bước mở kết nối (`client.stream(...).__aenter__()`,
   tương đương gửi request + chờ header) trong cùng một deadline với bước đọc dòng SSE sau đó, thay vì
   2 deadline tách rời.
   Cả 2 bug này chỉ lộ ra khi đo latency thật qua request thực tế tới Gemini (không mock) - review code
   tĩnh không phát hiện được, vì logic "trông đúng" ở cấp độ đọc code (asyncio.wait_for bọc quanh mỗi
   lần chờ trông hợp lý), chỉ sai ở chỗ đặt lại điểm bắt đầu đếm.

Latency worst-case - trước/sau fallback (đo trên 4 câu tình huống, latency thật không giả lập):

| | Trước (chỉ model routing, không fallback) | Sau (có fallback) |
|---|---|---|
| Worst-case quan sát (4 câu) | 69.84s (tinhhuong-q7) | 26.37s (tinhhuong-q4) |
| Trần lý thuyết | Không có - phụ thuộc hoàn toàn vào pro-preview | ≈ 18s (timeout) + latency flash-lite (~5-11s quan sát được) ≈ 30-33s |
| Rủi ro 503 làm lỗi hẳn stream | Có | Không - 503 chuyển fallback êm, không lộ lỗi cho user |

Bằng chứng thực tế (không phải giả lập): trong lần chạy test cuối cùng để lấy số liệu final, pro-preview
tự nhiên gặp 2 lần 503 "high demand" thật (không ép) cho tinhhuong-q1 và tinhhuong-q7 - cả 2 lần fallback
kích hoạt đúng, flash-lite trả lời thành công trong 7-8s, user không thấy lỗi.

Đánh đổi chấp nhận: khi fallback kích hoạt, chất lượng câu trả lời rơi về mức flash-lite+CoT (đã đo ở
bước trên: kết luận vẫn đúng nhưng hedge/kém quyết đoán hơn pro-preview ở một số câu như tinhhuong-q7) -
hợp lý vì có câu trả lời chất lượng khá trong thời gian chấp nhận được > không có câu trả lời/chờ vô hạn.

Test: dùng lại 3 câu chẩn đoán (đặc biệt tinhhuong-q4) + thêm 2-3 câu Tình huống khác trong ngân hàng đề (chưa từng test) để xác nhận cải thiện có nhất quán, không chỉ đúng 1 câu đã biết đáp án. Chạy lại 29 câu evaluation, xác nhận không hồi quy + đo thêm latency (model mạnh hơn có thể chậm hơn, cần biết đánh đổi).
ĐÃ THỰC HIỆN ĐẦY ĐỦ - xem chi tiết ở 2 mục [x] trên. 29 câu evaluation qua 3 lần chạy (model routing,
CoT-only isolation, fallback cuối) đều cho kết quả giống hệt nhau (exact_match_rate 90%, mean_recall
90%, mean_precision 68-69%, groundedness/correct_refusal 100%) - không hồi quy, vì bộ 29 câu không có
câu nào vượt ngưỡng 250 ký tự nên chưa từng thực sự kích hoạt code path câu dài (retrieval mở rộng,
model routing, CoT, hay fallback) - bộ eval này chỉ xác nhận "không phá gì" cho câu ngắn/vừa, việc kiểm
chứng cải thiện thực chất luôn phải dựa vào test riêng các câu tình huống dài.

Feature — Gộp câu tự nhiên cho danh sách "Ý còn thiếu/sai" trong kết quả chấm tự luận (fix theo UAT feedback)
Bối cảnh: hiện tại mỗi essay_key_points bị thiếu hiển thị thành 1 bullet riêng, kể cả khi nhiều ý cùng chủ ngữ/cấu trúc (ví dụ 3 bullet "Cơ quan điều tra có nhiệm vụ..." lặp lại chủ ngữ) — đọc rời rạc, không tự nhiên như văn viết thật.

RÀNG BUỘC BẮT BUỘC (không được vi phạm nguyên tắc đã chốt ở Phase 5b): việc gộp câu CHỈ là lớp hiển thị, KHÔNG được đổi cơ chế chấm điểm gốc (matched/missing vẫn trả về theo POSITIONS như cũ, không đổi). Bước gộp câu chỉ được phép NỐI/DIỄN ĐẠT LẠI đúng nội dung đã có trong các ý bị thiếu đã xác định — không thêm thông tin mới, không bớt ý, không đổi nghĩa.

[x] Thêm 1 bước hậu xử lý (tận dụng chung lời gọi LLM chấm điểm hiện có, thêm field mới trong response thay vì gọi riêng) — sinh thêm "missing_points_display": gộp các essay_key_points bị thiếu có cùng chủ ngữ/chủ đề thành 1-2 câu tự nhiên, giữ nguyên nội dung, không suy diễn thêm. Nếu các ý không cùng chủ ngữ/không gộp tự nhiên được, giữ nguyên dạng bullet riêng như cũ (không ép gộp gượng gạo).
[x] Test bằng chính ví dụ đã nêu (lythuyet-q11 — Điều 163, 3 ý "Cơ quan điều tra có nhiệm vụ...") — xác nhận gộp đúng thành câu tự nhiên, không mất/thêm ý.
[x] Test thêm vài câu khác có key_points KHÔNG cùng chủ ngữ (ví dụ câu có 4-5 ý về các khía cạnh khác nhau) — xác nhận hệ thống không ép gộp gượng gạo, giữ nguyên bullet riêng khi không hợp lý để gộp.
[x] Xác nhận scoring/matched-missing logic hoàn toàn không đổi — chỉ thêm field hiển thị mới, không sửa cơ chế chấm điểm.

ĐÃ HOÀN THÀNH. Implementation:
- `backend/app/prompts/essay_prompts.py`: thêm rule 8 vào `ESSAY_GRADING_SYSTEM_PROMPT`, yêu cầu model trả thêm field "missing_points_display" cùng lời gọi chấm điểm hiện có (không gọi LLM riêng). Rule 1-7 gốc (kể cả cách xác định matched/missing theo vị trí/positions) giữ nguyên không đổi.
- `backend/app/models/essay.py`: `EssaySubmitResponse.missing_points_display: list[str] | None = None`.
- `backend/app/services/essay_service.py`: `_validate_missing_points_display()` kiểm tra kiểu dữ liệu (list[str] không rỗng phần tử), quy tắc rỗng-khi-không-có-missing/không-rỗng-khi-có-missing; giá trị không hợp lệ rơi về `None`. Logic tính `matched`/`missing` từ `results` theo vị trí trong `_parse_grading_response()` giữ nguyên 100%, chỉ thêm field mới song song.
- `backend/app/api/essay.py`: truyền `missing_points_display` qua `EssaySubmitResponse`.
- Frontend (`EssayBankRunner.tsx`, `app/essay/practice/page.tsx`, `lib/types.ts`): render `result.missing_points_display ?? result.missing_points` — tự động fallback về bullet gốc khi model không trả field hợp lệ.

Test thật qua Gemini (không mock), lythuyet-q11 (Điều 163), câu trả lời lạc đề → cả 3 ý missing: gộp
đúng thành "Cơ quan điều tra có nhiệm vụ phát hiện tội phạm, thu thập chứng cứ và làm rõ tội phạm." -
không mất/thêm ý so với 3 essay_key_points gốc.

Test regression scoring: câu trả lời partial-correct (chỉ đúng ý 1 và 3 trong 3 ý của lythuyet-q11) →
`matched`/`missing` xác định đúng theo vị trí y hệt cơ chế cũ (ý 1, 3 matched; ý 2 missing), chỉ thêm
`missing_points_display: ["Cơ quan điều tra còn có nhiệm vụ thu thập chứng cứ."]` - xác nhận scoring
logic không đổi.

Test câu KHÔNG cùng chủ ngữ: lythuyet-q20 (8 ý về "khám xét" nhưng khác chủ đề con: khi nào tiến hành /
đối tượng bị thu giữ / căn cứ liên quan) - model không ép gộp thành 1 câu, tách thành 3 nhóm tự nhiên
theo đúng chủ đề con. Tương tự lythuyet-q9 (4 "phương pháp" điều chỉnh khác nhau) - tách 2 câu 2 nhóm,
không gộp gượng gạo thành 1 câu 4 ý. Ngược lại lythuyet-q1 (6 ý cùng chủ ngữ "Ngành luật này điều
chỉnh...") - gộp gọn thành 1 câu tự nhiên, đủ cả 5 quá trình tố tụng.

Fallback an toàn: test response giả (field thiếu, sai kiểu, rỗng-khi-có-missing) đều rơi về `None` -
frontend tự render lại `missing_points` gốc, không crash.

Feature — Polish Chat: chuẩn hóa nguồn, xử lý out-of-scope gọn, chặn lộ tài liệu tham khảo ngoài corpus, sửa bug lặp câu trả lời cũ khi hỏi lạc đề (từ UAT thật) Phát hiện qua UAT thật với 3 người test — 4 vấn đề, ưu tiên vấn đề D (bug chức năng) ngang với 3 vấn đề UX/grounding còn lại.

[x] A. ĐÃ SỬA. Chuẩn hóa tên nguồn hiển thị — hiện tại citation academic_reference hiện nguyên tên file PDF gốc (ví dụ "Giao-Trinh-Luat-Tố-Tụng-Hinh-Sự-Dh-Luat-Hn.pdf") thay vì tên tài liệu tự nhiên ("Giáo trình Luật Tố tụng Hình sự - Đại học Luật Hà Nội"). Thêm bảng ánh xạ source_document → display_name (corpus cố định ~11 văn bản, dùng static mapping, không cần đổi ingestion) — áp dụng cả khi build context cho LLM lẫn khi render citation cho user.

Đã thêm `backend/app/core/document_display_names.py` — static mapping, phủ đủ toàn bộ 17 văn bản thực tế trong corpus (không phải ~11 như ước tính ban đầu, corpus đã mở rộng qua các Phase). Áp dụng ở `rag_prompts.py` (context block model đọc — model không bao giờ thấy raw filename để có thể lặp lại trong câu trả lời), `legal_service.py` (full-text response), và `rag_service.py` (aggregate structure answer). Fallback an toàn: filename không có trong mapping thì bỏ đuôi ".pdf" thay vì lỗi cứng hoặc lộ nguyên filename.

Verify: hỏi trực tiếp câu chạm đúng văn bản "...Dh-Luat-Hn.pdf" nêu trong bug report (real API, không mock) — câu trả lời không còn chứa bất kỳ raw ".pdf" filename nào.

[x] B. ĐÃ SỬA. Trả lời gọn cho câu hỏi meta/out-of-scope — case cụ thể: user hỏi "bây giờ tôi hỏi bạn 1 câu ngoài lề bạn có trả lời được không" (câu hỏi VỀ khả năng, không phải câu hỏi ngoài lề thật) → bot trả lời dài dòng, liệt kê nhiều đoạn không cần thiết. Sửa: rút gọn phản hồi cho dạng câu hỏi meta/từ chối xuống 1-2 câu, không lặp lại cấu trúc đầy đủ như câu trả lời substantive.

Đã thêm rule 7 vào `RAG_SYSTEM_PROMPT` (`rag_prompts.py`). Lưu ý: câu hỏi meta này thực ra cũng thường được `is_out_of_scope` (mục E) gắn true và short-circuit thẳng ra `FALLBACK_ANSWER` cố định (vốn đã ngắn 1 câu) — rule 7 là lớp phòng thủ bổ sung cho trường hợp Query Understanding không chắc chắn nên để `is_out_of_scope=false` và câu hỏi vẫn đi qua generation.

Verify: hỏi đúng câu UAT (real API) — trả lời còn đúng 1 câu, không còn liệt kê dài dòng.

[x] C. ĐÃ SỬA. Chặn lộ cấu trúc prompt nội bộ ("NGỮ CẢNH") — bot đang trực tiếp nhắc tên field nội bộ ("phần NGỮ CẢNH được cung cấp") trong câu trả lời cho user — đây là prompt leakage, không nên để lộ chi tiết triển khai. Thêm rule rõ ràng trong system prompt: không bao giờ nhắc tên các phần/field nội bộ của prompt, nói tự nhiên như hiểu biết sẵn có, không như đang mô tả cấu trúc dữ liệu được đưa vào.

Đã thêm rule 8 vào `RAG_SYSTEM_PROMPT`, liệt kê rõ các nhãn cấm nhắc: "NGỮ CẢNH", "QUY ĐỊNH PHÁP LUẬT", "TÀI LIỆU HỌC THUẬT", "LỊCH SỬ HỘI THOẠI GẦN ĐÂY".

Verify: cross-check toàn bộ câu trả lời test (case A/B/C/D) bằng regex tìm các cụm nhãn nội bộ — không còn xuất hiện.

[x] D. ĐÃ SỬA. Chặn lộ danh mục "TÀI LIỆU THAM KHẢO" trong academic_reference — phát hiện: 1 số chunk academic_reference chứa nguyên phần "Danh mục tài liệu tham khảo" ở cuối giáo trình (liệt kê tên tác giả/công trình BÊN NGOÀI corpus thực tế, ví dụ "Đào Trí Úc, Nguyễn Ngọc Chí..."). Model đang trích dẫn lại danh mục này như thể đó là nguồn có thể truy cập được, gây hiểu lầm về phạm vi dữ liệu thật hệ thống có. Hướng sửa đúng: XỬ LÝ Ở TẦNG INGESTION (giống pattern KNOWN_TRAILING_BOILERPLATE_MARKERS đã có) — nhận diện và loại bỏ phần "TÀI LIỆU THAM KHẢO"/danh mục tham khảo khỏi chunk academic_reference lúc parse (đây là back-matter không có giá trị grounding, cùng loại với "Nơi nhận" đã lọc trước đây), không phải vá ở tầng prompt. Quét toàn bộ academic_reference tìm các chunk còn dính danh mục tham khảo tương tự, re-parse + re-embed các chunk bị ảnh hưởng.

Quét toàn bộ academic_reference (1102 chunk, không chỉ case đã báo) tìm ra đúng 7 chunk bị ảnh hưởng trên 5 văn bản. 3 cơ chế xử lý trong `ingestion/chunking.py`:
- `ACADEMIC_REFERENCE_LIST_HEADING_PATTERN` (regex tổng quát, không hardcode theo văn bản) — drop chunk có section_heading khớp đúng "TÀI LIỆU THAM KHẢO"/"DANH MỤC TÀI LIỆU THAM KHẢO" (5 chunk/3 văn bản, heading đã tách sạch thành dòng riêng).
- `KNOWN_ACADEMIC_TRAILING_REFERENCE_MARKERS` (dict theo (source_document, chunk_index), mirror đúng pattern `KNOWN_TRAILING_BOILERPLATE_MARKERS` đã có cho legal_text) — 2 chunk có marker dính giữa đoạn văn thật (heading không viết hoa toàn bộ nên không tách được thành heading riêng) → truncate tại marker, giữ lại nội dung thật phía trước.
- `KNOWN_ACADEMIC_CHUNKS_TO_DROP` — 1 chunk là phần tiếp nối danh mục + abstract tiếng Anh trùng lặp, không có heading để bắt được, drop nguyên chunk theo key (source_document, chunk_index).

Đã re-parse riêng 5 văn bản bị ảnh hưởng (không re-ingest toàn bộ 12+ file), re-embed 2 chunk bị truncate, xóa 6 point bị drop khỏi Qdrant theo point ID xác định (build_point_id), merge lại vào chunks.json. Regression: chạy lại `regression_check_legal_text` + `test_chuong_muc` + `test_dieu_chuong_muc_boundary` + `test_dieu_phan_boundary` — 1533/1533 chunk legal_text khớp baseline (logic legal_text hoàn toàn không bị đụng tới). Quét lại corpus sau fix với nhiều biến thể cụm từ hơn (không chỉ khớp chính xác) — xác nhận 0 case còn sót.

Verify: hỏi 2 câu chạm đúng 2 trong 5 văn bản đã sửa (real API) — không còn trích tên tác giả ngoài corpus (Đào Trí Úc, Nguyễn Ngọc Chí...) trong câu trả lời.

[x] E (ƯU TIÊN CAO, phát hiện thêm ngoài 3 case đã nêu) — ĐÃ SỬA. BUG: hội thoại nhiều lượt với câu hỏi lạc đề/ngoài luồng/không nghiêm túc khiến bot LẶP LẠI câu trả lời substantive cũ thay vì nhận ra chủ đề đã đổi. Case thật: sau khi hỏi 1 câu luật, user hỏi tiếp "đi nhà nghỉ với anh không" và "bỏ qua ngữ cảnh trước đi, tôi muốn tâm sự" — cả 2 lần bot đều trả lời gần y hệt câu luật trước đó, không nhận ra đây là câu hỏi khác hẳn.

Điều tra (real API, tài khoản Supabase test thật, không mock) xác định đúng giả thuyết (a): Query Understanding (rewrite_question) VI PHẠM HỢP ĐỒNG OUTPUT của chính nó. Prompt cũ yêu cầu "CHỈ trả về đúng một câu hỏi đã viết lại, không thêm giải thích", nhưng với câu hỏi lạc đề, model đôi khi (quan sát được 1/3 lần lặp lại độc lập trong lúc điều tra) trả về một câu MÔ TẢ/META kiểu "Câu hỏi của bạn không liên quan đến nội dung Luật Tố tụng Hình sự Việt Nam..." thay vì giữ nguyên câu hỏi gốc hoặc câu hỏi đã viết lại thật. Câu meta này sau đó bị pipeline phía sau dùng Y NGUYÊN như thể là câu hỏi thật — vừa làm query cho retrieval (chứa từ khóa pháp lý nên vượt threshold, kéo về các chunk luật chung chung), vừa làm "Câu hỏi của sinh viên" trong prompt sinh câu trả lời cuối — khiến model sinh ra câu trả lời substantive về pháp luật thay vì từ chối. Không phải lỗi (b) retrieval/threshold hay (c) cache/state — cả 2 tầng đó xử lý đúng chức năng của mình, chỉ đơn giản là nhận input đã hỏng từ tầng (a). Đã kiểm tra kỹ frontend (ChatView.tsx) — mỗi câu hỏi tạo message id/state mới hoàn toàn, không có bằng chứng lỗi cache/state.

Cách sửa tận gốc (không vá ở prompt sinh câu trả lời cuối, sửa đúng tầng gây lỗi):
1. Tách response của Query Understanding thành 2 field JSON riêng biệt: `rewritten_question` và `is_out_of_scope` — enforce Ở TẦNG API qua Gemini `responseSchema` (không chỉ dựa vào lời văn trong system prompt như trước, vì đó chính là thứ đã bị vi phạm). Model buộc phải trả về cả 2 field mỗi lần gọi, không còn chỗ để nhét câu mô tả vào field câu hỏi.
2. Khi `is_out_of_scope=true`, `rag_service.stream_answer_question` short-circuit ROUTE THẲNG sang câu trả lời fallback đã có sẵn (`FALLBACK_ANSWER`) — không gọi retrieval, không gọi generation, citations rỗng, cùng shape với nhánh "không tìm thấy context" đã có.
3. Lớp an toàn thứ 2 (không tin tuyệt đối vào riêng lớp schema): nếu `is_out_of_scope=false` nhưng `rewritten_question` vẫn có dấu hiệu bất thường rõ ràng (chứa cụm mô tả điển hình như "câu hỏi của bạn"/"không liên quan"/"xin lỗi", hoặc dài bất thường so với câu gốc), tự động fallback về câu hỏi gốc của user thay vì dùng thẳng.

Bug phụ phát hiện khi test lại (đã sửa trước khi commit, không phải regression bị bỏ sót): bản đầu tiên của rule `is_out_of_scope` định nghĩa phạm vi ứng dụng quá hẹp — chỉ nói "Luật Tố tụng Hình sự" — khiến model hiểu nhầm và gắn `is_out_of_scope=true` sai cho các câu hỏi HỢP LỆ về Bộ luật Hình sự (nội dung, không phải thủ tục) như "phòng vệ chính đáng", "tuổi chịu trách nhiệm hình sự" — vì câu hỏi chỉ nói "pháp luật hình sự" mà không có chữ "tố tụng". Phát hiện được nhờ chạy lại bộ eval 29 câu SAU KHI sửa xong (không chỉ test riêng case đã biết) — citation accuracy tụt 90%→80%, truy vết bằng cách gọi trực tiếp `rewrite_question()` cho từng câu fail để xem `is_out_of_scope` trả về gì, xác nhận đúng là bug ở định nghĩa phạm vi. Sửa bằng cách viết lại rule để nêu rõ phạm vi bao gồm cả Bộ luật Hình sự/Nghị định/Thông tư liên quan (không chỉ literal "tố tụng"), thêm nguyên tắc "phân vân thì ưu tiên false" (an toàn hơn là chặn nhầm). Re-verify: citation accuracy trở lại 95% (cao hơn baseline 90%, trong phạm vi variance bình thường).

Số liệu xác nhận cuối cùng (real API, không mock):
- Đúng kịch bản bắt bug ban đầu (1 câu luật + "đi nhà nghỉ với anh không"), lặp lại 10 lần ĐỘC LẬP sau khi sửa: 10/10 refuse đúng (trước khi sửa: quan sát 1/3 lần lỗi trong lúc điều tra).
- 5 câu lạc đề/không nghiêm túc khác (câu gốc, "bỏ qua ngữ cảnh...", "hôm nay thời tiết đẹp nhỉ", câu vô nghĩa, "bạn có yêu tôi không"): 5/5 refuse đúng — xác nhận fix tổng quát, không chỉ vá riêng 1 case.
- Eval 29 câu (backend/evaluation/run_evaluation.py, chạy lại toàn bộ sau fix): correct_refusal_rate = 100% (7/7 out_of_scope, không đổi so với baseline), groundedness = 100% (không đổi), citation accuracy = 95% (baseline 90%, KHÔNG hồi quy — cao hơn baseline).
- Lưu ý phụ: chạy eval 29 câu cần sửa `run_evaluation.py` tăng pacing giữa các câu (0.3s → 6.5s) để không bị chính rate limiter của app (`LLM_ROUTE_RATE_LIMIT = 10/minute`, đã thêm ở 1 lần security audit trước) chặn giữa chừng — lỗi hạ tầng test có sẵn từ trước, không liên quan tới fix này, chỉ lộ ra lần đầu khi chạy eval fresh.

Bug — Lộ số thứ tự nội bộ tài liệu nguồn ("Tình huống N") + retrieval bỏ lỡ Điều 298 BLTTHS khi câu hỏi phụ thuộc ngữ cảnh hội thoại trước
Phát hiện qua đánh giá thủ công 1 câu trả lời Chat thật, sau đó điều tra và tái hiện bằng đúng 4 tin nhắn thật gửi tuần tự trong CÙNG 1 conversation_id (real API, tài khoản test thật, không mock) — 2 vấn đề riêng biệt nhưng có quan hệ nhân quả trong tình huống này:

1. Leak "Tình huống N": file `693495639-TÌNH-HUỐNG-TỐ-TỤNG-HINH-SỰ.pdf` (academic_reference) tự đánh số nội bộ thật trong chính nội dung ("Tình huống 4:", "Tình huống 5:", "Tình huống 13:", "Tình huống 14:"...). Khi chunk chứa số thứ tự này lọt vào NGỮ CẢNH, model đôi khi quote thẳng số thứ tự đó vào câu trả lời ("Theo tài liệu học thuật (Tình huống 14)...") — số thứ tự này chỉ có ý nghĩa tổ chức nội bộ trong tài liệu gốc, sinh viên không có tài liệu để đối chiếu, và đây là lớp lộ thông tin KHÁC với case C ở mục Polish Chat phía trên (case C chặn nhãn cấu trúc do CHÍNH HỆ THỐNG này tạo ra như "NGỮ CẢNH"/"QUY ĐỊNH PHÁP LUẬT"; case này là số thứ tự có thật bên trong CHÍNH VĂN BẢN NGUỒN, hệ thống không tạo ra nhãn đó).

2. Điều 298 BLTTHS ("Giới hạn của việc xét xử") bị retrieval bỏ lỡ cho câu hỏi tình huống "tại phiên tòa xét xử, có căn cứ xác định hành vi cấu thành tội cướp tài sản (Điều 168)..." khi câu hỏi này là lượt thứ 3 trong 1 hội thoại (lượt 1 đã nêu bị cáo bị truy tố tội TRỘM CẮP theo Điều 173). Đo trực tiếp: Điều 298 rank #133/1000 trong semantic search (score 0.62, dưới các Điều BLHS láng giềng của Điều 168 như 171/170/169/302). Nguyên nhân xác nhận qua probe độc lập (không phụ thuộc cơ chế multi-turn): bản thân câu hỏi lượt 3 không tự nó nói rõ đây là tội KHÁC với tội đã truy tố — sự tương phản đó chỉ có ý nghĩa nhờ lượt 1, nhưng Query Understanding không chủ động bơm ngữ cảnh tương phản đó vào `rewritten_question`, khiến embedding thuần túy giống 1 câu tra cứu Điều 168 BLHS thông thường.

Quan hệ nhân quả giữa 2 vấn đề trong case cụ thể này: khi Điều 298 (legal_text) không được retrieve, model mất nguồn trích dẫn "sạch" cho khái niệm giới hạn xét xử, buộc phải dựa hẳn vào academic_reference — tăng áp lực/xác suất quote thẳng số thứ tự nội bộ của tài liệu đó (quan sát 2/5 lần leak trong lần test đầu, so với 0/8 lần trong các câu hỏi tự dựng độc lập mà Điều 298 vẫn được retrieve song song).

Lưu ý về phương pháp điều tra: lần test ĐẦU TIÊN bằng câu hỏi tự dựng (không phải nguyên văn thật) KHÔNG tái hiện được cả 2 bug — retrieval hoạt động tốt vì cách diễn đạt tự dựng vô tình quá tường minh ("tội nặng hơn tội đã truy tố"). Chỉ khi dùng ĐÚNG NGUYÊN VĂN 4 tin nhắn thật, đúng thứ tự, cùng 1 conversation_id mới tái hiện được — bài học: test bằng câu hỏi tự dựng dù bám sát mô tả vấn đề vẫn có thể che giấu bug thật do khác biệt tinh vi trong cách diễn đạt/ngữ cảnh hội thoại.

[x] Fix 1 — chặn leak "Tình huống N": thêm rule 10 (tách riêng khỏi rule 8) vào `RAG_SYSTEM_PROMPT` (`backend/app/prompts/rag_prompts.py`) — cấm quote/nhắc số thứ tự nội bộ có thật trong tài liệu nguồn academic_reference dưới mọi hình thức, chỉ được diễn đạt lại bản chất pháp lý bằng lời riêng.
[x] Fix 2 — cải thiện retrieval Điều 298 qua Query Understanding: mở rộng rule 2.b (KHÔNG thêm mục 2.e riêng) trong `QUERY_UNDERSTANDING_SYSTEM_PROMPT` (`backend/app/prompts/query_understanding_prompts.py`) — khi câu hỏi hiện tại nêu tội danh/Điều khác với tội danh/Điều đã bị truy tố trong lịch sử hội thoại (cùng bị can/bị cáo), `rewritten_question` phải nêu rõ sự tương phản đó (ví dụ "...tội cướp tài sản theo Điều 168, khác với tội trộm cắp tài sản theo Điều 173 đã bị truy tố ban đầu...").
[x] Test lại đúng 4 tin nhắn thật, 10 conversation_id độc lập (40 lượt tổng): leak "Tình huống N" 0/40 (trước fix: 2/5 = 40%). Điều 298 lọt vào legal_primary và được cite đúng cùng Điều 168/173: 10/10 (trước fix: 0/5).
[x] Chạy lại 29 câu evaluation, xác nhận không hồi quy.

Bug phụ phát hiện khi test lại (đã sửa trước khi commit, không phải regression bị bỏ sót): bản đầu tiên của Fix 2 thêm hẳn 1 mục 2.e riêng, dài ~9 dòng, mô tả chi tiết + ví dụ cho quy tắc tương phản tội danh. Bản này gây REGRESSION không liên quan về mặt logic: câu hỏi case 10 trong eval suite ("Theo Nghị định 250/NĐ-CP, việc định giá tài sản...") bị `is_out_of_scope` gắn nhầm thành `true` một cách NHẤT QUÁN (10/10 lần), dù rule mới thêm vào không hề đề cập gì tới logic phân loại out-of-scope. Xác nhận bằng `git stash`: prompt gốc (trước khi thêm rule 2.e) → 10/10 `is_out_of_scope=False` (đúng); prompt có rule 2.e dài → 10/10 `True` (sai). Sửa bằng cách RÚT GỌN, sáp nhập trực tiếp vào rule 2.b hiện có (2 câu, không tạo mục riêng) — re-test: case 10 trở lại 10/10 `False` đúng, đồng thời Fix 2 chính (Điều 298) vẫn giữ nguyên 10/10 thành công, không bị ảnh hưởng.

Bài học tổng quát hóa được (áp dụng cho mọi lần sửa system prompt sau này): thêm một khối rule mới dài, kể cả khi về mặt NỘI DUNG/LOGIC hoàn toàn không liên quan tới một quy tắc khác trong cùng system prompt (ở đây: rule về "tương phản tội danh trong rewritten_question" không liên quan gì tới rule "is_out_of_scope"), vẫn có thể gây HIỆU ỨNG PHỤ không mong muốn lên phần khác của cùng prompt — nhiều khả năng do việc chèn thêm nội dung dài làm dịch chuyển phân bố attention/context của model một cách khó dự đoán, không phải lỗi logic tường minh có thể lường trước bằng cách đọc rule. Nguyên tắc rút ra: ƯU TIÊN rule ngắn gọn, sáp nhập vào rule có sẵn cùng chủ đề thay vì thêm mục riêng dài dòng khi có thể — vừa giảm rủi ro hiệu ứng phụ, vừa giữ prompt gọn. Sau khi sửa bất kỳ rule nào trong 1 system prompt nhiều rule, PHẢI test lại toàn bộ eval suite (không chỉ case đang sửa) để bắt được đúng loại regression "không liên quan về logic nhưng liên quan về vị trí trong cùng prompt" này — đây là lần thứ 2 loại bug này xuất hiện trong dự án (lần đầu ở case E phía trên, cũng phát hiện nhờ chạy lại eval suite đầy đủ thay vì chỉ test case đang sửa).

Case study cho phần Discussion/Limitations của bài báo: đây là ví dụ cụ thể cho rủi ro của kiến trúc nhiều bước LLM nối tiếp (query understanding → retrieval → generation) khi MỘT bước vi phạm hợp đồng output (dù prompt đã yêu cầu rõ ràng bằng lời văn) mà bước sau không có cơ chế validate lại, lỗi sẽ lan truyền và biểu hiện ra ở tầng cuối (generation) theo cách trông giống lỗi ở tầng đó, trong khi gốc rễ thực sự nằm ở tầng đầu. Bài học rút ra, tổng quát hóa được: (1) hợp đồng giữa các bước LLM nối tiếp nên được enforce bằng cơ chế có cấu trúc (JSON schema) thay vì chỉ dựa vào lời văn prompt, đặc biệt khi output của bước trước được dùng trực tiếp làm input cho bước sau mà không qua người dùng xem lại; (2) ngay cả sau khi enforce bằng schema, vẫn nên có lớp validate độc lập ở phía nhận dữ liệu (defense in depth) vì schema chỉ đảm bảo đúng KIỂU dữ liệu, không đảm bảo đúng NỘI DUNG; (3) khi mở rộng logic phân loại nhị phân/phạm vi bằng mô tả tự nhiên trong prompt, cần test lại theo cả 2 hướng (không chặn nhầm case hợp lệ VÀ chặn đúng case không hợp lệ) trước khi coi là đã sửa xong, tránh false positive tương tự bug phụ đã phát hiện.

Feature — Mở rộng phân loại ý định Query Understanding: chào hỏi + tóm tắt câu trả lời trước (UAT lượt 2) Bối cảnh: hệ thống hiện chỉ phân loại nhị phân is_out_of_scope (true/false, từ fix bug E) — không đủ cho 2 case UAT mới: (1) chào hỏi bị coi như câu hỏi luật hoặc bị từ chối cứng nhắc, (2) yêu cầu "tóm tắt lại" bị coi như câu hỏi luật mới, kích hoạt retrieval không cần thiết.

Thiết kế: đổi is_out_of_scope (boolean) thành field intent (enum) trong response schema Query Understanding: "legal_question" (mặc định, luồng RAG hiện tại) | "greeting" (chào hỏi/giới thiệu) | "summarize_previous" (yêu cầu tóm tắt câu trả lời gần nhất) | "out_of_scope" (giữ nguyên hành vi đã fix ở bug E).

[ ] greeting: short-circuit KHÔNG qua retrieval/generation costly — dùng template trả lời cố định (có vài biến thể ngẫu nhiên tránh lặp máy móc), giới thiệu ngắn gọn bản thân + gợi ý cách dùng. Không cần LLM generation, rẻ và nhanh nhất có thể (giữ tinh thần đã áp dụng cho out_of_scope: short-circuit tránh chi phí không cần thiết). [ ] summarize_previous: KHÔNG retrieval mới — lấy đúng nội dung câu trả lời gần nhất của assistant trong conversation (đã có sẵn qua recent_turns/chat_query_logs), đưa qua 1 lời gọi LLM nhẹ với ràng buộc CHẶT: chỉ được tóm gọn/rút gọn ĐÚNG nội dung đã có, không thêm thông tin pháp lý mới, không suy diễn thêm. Giữ nguyên citations của câu trả lời gốc (không cần tính lại). [ ] Edge case: nếu intent=summarize_previous nhưng KHÔNG có câu trả lời assistant nào trước đó trong hội thoại (ví dụ đây là tin nhắn đầu tiên) — trả lời nhẹ nhàng hướng dẫn user đặt câu hỏi trước ("Bạn muốn mình tóm tắt nội dung nào? Hãy đặt câu hỏi trước nhé.") [ ] Test cả 3 intent mới (legal_question giữ nguyên không đổi hành vi) bằng câu hỏi thật qua API thật — số lượng lặp lại VỪA PHẢI (3-5 lần, không cần 10, do ngân sách Gemini API còn hạn chế ~150k VNĐ) để tiết kiệm chi phí nhưng vẫn đủ tin cậy. [ ] Chạy lại 29 câu evaluation xác nhận không hồi quy — đặc biệt các câu ngắn/legal_question thông thường không bị phân loại nhầm sang greeting/summarize_previous.

Feature — Sinh tình huống minh họa + chấm định tính câu trả lời của user trong Chat (từ mass test UAT) Triết lý cốt lõi (do người dùng đặt ra, giữ nguyên xuyên suốt thiết kế): "Đây là chatbot hỗ trợ học tập, chữa bài, chứ không phải giáo viên chấm điểm." — KHÔNG dùng điểm số tuyệt đối (không "7/10", không %), chỉ dùng feedback định tính dạng matched/missing points, tái dùng đúng UI/UX đã build cho module Tự luận, không phải phát minh cách trình bày mới. Đây cũng nhất quán với quyết định đã chốt từ đầu dự án: không gamification (đã cắt điểm số/streak/leaderboard khỏi scope).

Bug — "giải thích đơn giản hơn" bị gộp nhầm vào summarize_previous, tạo ra bản trả lời NGẮN nhưng vẫn khó hiểu thay vì bản DỄ HIỂU hơn
Phát hiện qua UAT kiểm tra nhanh 4 case chưa test riêng (trước UAT thật): gửi "Điều 173 Bộ luật Hình sự quy định gì về tội trộm cắp tài sản?" rồi "giải thích đơn giản hơn được không, tôi không hiểu" — intent bị phân vào summarize_previous vì định nghĩa gốc của intent này ("tóm tắt/rút gọn/nói ngắn lại") đủ rộng để LLM khớp nhầm với yêu cầu "giải thích lại". Hệ quả: SUMMARIZE_SYSTEM_PROMPT ép cứng theo hướng RÚT NGẮN (không quá 30-40% độ dài gốc, mặc định 3-4 câu) — câu trả lời co từ 1552 xuống 503 ký tự nhưng vẫn giữ nguyên thuật ngữ pháp lý gốc ("chiếm đoạt tài sản", "khung hình phạt"...), không thực sự dễ hiểu hơn như sinh viên yêu cầu, chỉ là bản nén của bản gốc.

Nguyên nhân gốc: summarize_previous gộp chung 2 nhu cầu khác nhau về bản chất — "ngắn hơn" (độ dài) và "dễ hiểu hơn" (độ phức tạp ngôn ngữ) — dùng chung 1 prompt bị ràng buộc độ dài, nên mọi yêu cầu "giải thích lại" đều bị xử lý như yêu cầu rút gọn.

[x] Tách "explain_simpler" thành intent riêng (mở rộng enum intent của Query Understanding lên 7 giá trị, thêm vào cạnh legal_question/greeting/summarize_previous/request_scenario/answer_evaluation/out_of_scope). Viết lại rule phân loại trong QUERY_UNDERSTANDING_SYSTEM_PROMPT (`backend/app/prompts/query_understanding_prompts.py`) làm rõ ranh giới: summarize_previous = yêu cầu về ĐỘ DÀI (ngắn hơn, để ghi chú/phát biểu), explain_simpler = yêu cầu về ĐỘ DỄ HIỂU (không hiểu, xin diễn đạt khác/ví dụ) — dấu hiệu nhận biết là từ khóa bối rối ("không hiểu", "khó hiểu") hoặc xin cách diễn đạt khác/ví dụ, không chỉ đơn thuần xin bản ngắn hơn. Trường hợp mơ hồ không có từ khóa độ dài rõ ràng → ưu tiên explain_simpler (cách diễn đạt tự nhiên hơn khi ai đó chưa hiểu).
[x] Tạo EXPLAIN_SIMPLER_SYSTEM_PROMPT riêng (`backend/app/prompts/conversational_prompts.py`), tách hẳn khỏi SUMMARIZE_SYSTEM_PROMPT: KHÔNG có ràng buộc giới hạn độ dài — bản diễn giải được phép DÀI HƠN bản gốc nếu cần thêm ví dụ đời thường/giải thích thuật ngữ; hướng dẫn thay thuật ngữ chuyên ngành bằng từ đời thường khi không làm sai nghĩa, hoặc giữ thuật ngữ bắt buộc nhưng giải thích ngay sau; vẫn giữ ràng buộc grounding chặt như summarize_previous (chỉ diễn giải lại nội dung đã có, không thêm căn cứ pháp lý mới). Wiring vào `stream_answer_question` (`backend/app/services/rag_service.py`) cùng shape với nhánh summarize_previous (tái dùng citations của last_turn, cùng cơ chế fallback khi lỗi/không có lượt trước).
[x] Test lại đúng case đã phát hiện (Điều 173 + "giải thích đơn giản hơn được không, tôi không hiểu"): intent giờ đúng là explain_simpler, câu trả lời DÀI HƠN bản gốc (2077 so với 1552 ký tự), dùng ví dụ đời thường ("cần câu cơm chính của nạn nhân") thay vì chỉ nén ý.
[x] Test 3 case ranh giới phân loại: "tóm tắt lại giúp mình trong 3 câu thôi" → summarize_previous (đúng); "mình vẫn chưa hiểu lắm, bạn nói lại theo cách khác được không" → explain_simpler (đúng); "nói lại giúp mình" (mơ hồ, không có từ khóa độ dài) → explain_simpler (đúng theo quy tắc ưu tiên đã định).
[x] Chạy lại 29 câu evaluation — do không có EVAL_USER_EMAIL/PASSWORD trong .env (không chạy được run_evaluation.py qua HTTP/Supabase auth thật), verify bằng script gọi trực tiếp service layer (rewrite_question + stream_answer_question) trên cùng 29 câu, real Gemini/Qdrant, không mock: citation accuracy 20/20, groundedness 29/29, correct-refusal 7/7 (khớp baseline), 0/29 câu legal_question bị phân loại nhầm sang summarize_previous/explain_simpler. Lưu ý: backend/evaluation/results.json KHÔNG được ghi đè lần này vì không chạy qua pipeline chính thức (thiếu is_fallback/used_academic_reference đọc lại từ chat_query_logs) — cần chạy run_evaluation.py thật qua HTTP khi có EVAL_USER_EMAIL/PASSWORD để cập nhật file đó.

Thiết kế 2 lượt liên kết: [ ] Lượt 1 — sinh tình huống: intent mới "request_scenario" (mở rộng enum intent của Query Understanding, thêm vào bên cạnh legal_question/greeting/summarize_previous/out_of_scope). Kích hoạt khi user yêu cầu ví dụ/tình huống thực tế, hoặc ngữ cảnh hội thoại cho thấy đang thảo luận lý thuyết và hợp lý để đề xuất tình huống minh họa. Dùng đúng nội dung/Điều luật đã có trong hội thoại gần đây (không retrieval lại từ đầu). Bot sinh 2 phần: (a) tình huống fictional hiển thị cho user, (b) bộ key_points ẩn (không hiển thị, lưu vào chat_query_logs — thêm cột mới nếu cần) dùng để chấm ở lượt 2 — PHẢI grounding vào đúng Điều luật đã thảo luận trong hội thoại, không tự bịa nguyên tắc pháp lý mới không có căn cứ. [ ] Lượt 2 — chấm định tính: intent mới "answer_evaluation", chỉ kích hoạt khi lượt trước trong cùng hội thoại có tình huống + rubric ẩn đã lưu (không phải câu hỏi thông thường). Lấy key_points ẩn, chấm theo đúng cơ chế LLM-as-judge đã có (matched/missing POSITIONS, không reconstructed text — tái dùng đúng nguyên tắc essay_service.py). Feedback dạng "Ý đã có / Ý còn thiếu" + 1 câu nhận xét định tính ngắn, KHÔNG có điểm số/phần trăm dưới bất kỳ hình thức nào. [ ] Chi phí: tính năng này thêm 2 lời gọi LLM mới mỗi vòng — build và test kỹ Lượt 1 riêng, xác nhận ổn định trước khi làm Lượt 2, tránh build cả 2 cùng lúc rồi phải sửa nhiều vòng tốn ngân sách Gemini còn hạn chế. [ ] Test Lượt 1: sinh tình huống có thực sự grounding vào Điều luật đã thảo luận không, tình huống có hợp lý/tự nhiên không, rubric ẩn có đúng dùng làm căn cứ chấm hợp lý không (spot-check thủ công như đã làm cho essay_key_points). [ ] Test Lượt 2 (sau khi Lượt 1 ổn định): chấm đúng matched/missing theo rubric ẩn, không lộ rubric cho user, không có điểm số nào xuất hiện trong output.

Feature — Big update sau UAT lượt 3: cải thiện reasoning câu hỏi phức tạp, ngưỡng nhiều câu hỏi con/1 tin nhắn, ẩn danh hóa người thật Bối cảnh: UAT lượt 3 phát hiện 3 hiện tượng, sau điều tra/thảo luận thu gọn còn 2 hạng mục thật cần sửa (hạng mục thứ 3 ban đầu — "chưa áp case có tên nhân vật" — hóa ra đã đúng hành vi mong muốn cho người thật, chỉ cần làm rõ/củng cố, không phải bug).

[ ] A. Cải thiện retrieval cho câu hỏi tình huống nhiều tình tiết/phức tạp (gộp case "anh A/B đồng phạm D" đã sửa trước + case mới "nhận định đúng/sai + tình huống phúc thẩm 6 câu hỏi con"): tiếp tục áp dụng đúng phương pháp đã dùng cho Điều 298/280/D đồng phạm — điều tra rank/score thật của Điều luật đúng bị bỏ lỡ (nghi ngờ ban đầu: Điều 358 hủy án tuyên vô tội, nguyên tắc "không làm xấu hơn tình trạng bị cáo" khi chỉ có kháng cáo giảm nhẹ), không đoán mà đo bằng dữ liệu thật.  
  Câu hỏi mẫu của user trong lúc UAT:
  A và B thực hiện hành vi giết 04 người tại tỉnh N. Vụ án do Cơ quan Cảnh sát điều tra Bộ Công an khởi tố và điều tra. Bản kết luận và đề nghị truy tố được gửi đến Viện kiểm sát có thẩm quyền. Câu hỏi :Viện kiểm sát nào có thẩm quyền quyết định việc truy tố bị can A, B? Viện kiểm sát cấp nào có trách nhiệm thực hành quyền công tố tại phiên tòa? 

[ ] B. Điều tra riêng ngưỡng "nhiều câu hỏi con trong 1 tin nhắn" — trục HOÀN TOÀN KHÁC với multi-turn hội thoại đã test OK (10 lượt riêng biệt, không suy giảm). Test tăng dần số câu hỏi con trong 1 tin nhắn (4 → 6 → 8...) để tìm ngưỡng bắt đầu suy giảm chất lượng/bỏ sót câu. Case UAT thật đã có 6 câu hỏi con (4 nhận định + 2 tình huống) — dùng làm test case đầu tiên.
  Câu hỏi mẫu của user trong lúc UAT:
  Câu 1. Nhận định đúng/sai – Giải thích Nhận định 1: Thẩm phán chủ tọa phiên tòa phải từ chối tiến hành tố tụng hoặc bị thay đổi nếu là người thân thích với người bào chữa trong vụ án đó. Nhận định 2: Một người có thể tham gia tố tụng với hai tư cách trong vụ án hình sự. Nhận định 3: Biện pháp tạm giam không áp dụng với bị can là người dưới 18 tuổi bị khởi tố về tội ít nghiêm trọng. Nhận định 4: Thời hạn điều tra bổ sung được xác định căn cứ theo loại tội phạm. ⸻ Câu 2. Câu hỏi tình huống Hãy nêu hướng giải quyết và cơ sở pháp lý để áp dụng của Hội đồng xét xử phúc thẩm trong các trường hợp sau đây: Trường hợp 1 Có căn cứ xác định hành vi của bị cáo không cấu thành tội phạm. Trường hợp 2 Có căn cứ để tăng hình phạt cho bị cáo đã kháng cáo yêu cầu giảm hình phạt, ngoài ra không còn kháng cáo, kháng nghị nào khác.

[ ] C. Ẩn danh hóa người thật trong câu hỏi tình huống — QUYẾT ĐỊNH ĐÃ CHỐT: khi câu hỏi nhắc tên người có thật/nhận diện được ngoài đời (người nổi tiếng, nhân vật thời sự...) kèm mô tả hành vi cụ thể, bot PHẢI reframe thành nhân vật ẩn danh (A/B/C...) trong câu trả lời, phân tích nguyên tắc pháp lý áp dụng cho loại hành vi mô tả — TUYỆT ĐỐI không nhắc lại tên thật, không khẳng định đây là kết luận về vụ việc thực tế cụ thể nào (thêm câu miễn trừ rõ ràng). Phân biệt 2 loại câu hỏi (không reframe máy móc mọi trường hợp):

Hỏi "nếu có hành vi X thì cấu thành tội gì" (dù kèm tên người thật) → REFRAME, trả lời phân tích ẩn danh.
Hỏi trực tiếp xin xác nhận/phủ nhận cáo buộc cụ thể ("X có tội không?", "ai đúng ai sai trong vụ này?") → TỪ CHỐI như hiện tại, không suy đoán thay tòa án. Lý do quyết định: tránh hệ thống khẳng định tội danh cụ thể cho người thật dựa trên tin đồn/mô tả một chiều chưa qua kiểm chứng pháp lý nào — vi phạm trực tiếp nguyên tắc suy đoán vô tội mà chính sản phẩm dạy cho user, và là rủi ro pháp lý/danh dự thật cho dự án khi khảo sát/bảo vệ trước hội đồng.

[x] Điều tra mục A: đo trực tiếp rank/score thật qua Gemini embed_query + Qdrant query_points (top_k=1000, real API) cho câu hỏi mẫu "VKS nào truy tố / VKS cấp nào công tố tại phiên tòa". Điều căn cứ đúng xác nhận từ văn bản luật thật (grep `ingestion/chunks.json`): Điều 239 (thẩm quyền truy tố), Điều 266 (nhiệm vụ VKS công tố khi xét xử), Điều 268 (thẩm quyền xét xử của Tòa án — quyết định VKS cấp nào). Đo được: Điều 239 rank #1 (lọt), Điều 266 rank #20 (trong top-25 pool nhưng thua primary_count=8, bị 7 Điều mang tính hành chính chung cùng tài liệu như Điều 4/7/9/41/42/236/461 chiếm hết slot), Điều 268 rank #67 (ngoài hẳn top-25, không cách nào lọt dù nới primary_count). Chạy full pipeline thật xác nhận: model không fallback trắng mà tự suy luận ra "VKSND cấp tỉnh" bằng kiến thức nội tại, không trích Điều 268 nào (vì không có trong NGỮ CẢNH) — câu trả lời nghe hợp lý nhưng KHÔNG GROUNDED, khó phát hiện hơn hẳn một fallback trắng thông thường.

[x] Điều tra mục B: test kiểm soát quyết định — đo rank của từng Điều căn cứ đúng khi hỏi MỘT MÌNH so với khi GỘP CHUNG vào 1 tin nhắn nhiều câu hỏi con (biến thể 4/6/8 câu). Kết quả: hầu hết Điều rank **#1 khi hỏi riêng** (Điều 49, 174, 357, 359) nhưng rơi xuống hạng vài chục tới vài trăm ngay khi gộp với bất kỳ câu hỏi khác chủ đề nào (ví dụ Điều 359 từ #1 solo rơi xuống #425-910 khi gộp). Đây KHÔNG PHẢI hiện tượng "ngưỡng số lượng" (không phải kiểu "4 câu ổn, 6-8 câu mới hỏng") — ngay ở biến thể 4 câu, chỉ 1/8 Điều còn lọt top-25. Nguyên nhân gốc: `embed_query` mã hóa cả message nhiều chủ đề thành 1 vector trung bình duy nhất, pha loãng tín hiệu của mọi chủ đề "phụ". Chạy full pipeline thật trên đúng 6 câu UAT xác nhận thiệt hại cụ thể: nhận định 2 trả lời "Đúng" — SAI về nội dung pháp lý (đúng ra có giới hạn theo Điều 72 khoản 4b, Điều này rank quá thấp nên không được retrieve); nhận định 1 trích "Điều 49, Điều 53" nhưng 2 Điều này không hề có trong `legal_primary`/`legal_related` — trích dẫn không grounded; Câu 2 (cả 2 trường hợp) fallback trắng hoàn toàn. Phát hiện phụ về tính đúng đắn: giả thuyết ban đầu về Điều 358 cho Câu 2 Trường hợp 1 là SAI — Điều đúng là Điều 359 (Điều 358 là hủy án để điều tra/xét xử lại, khác hẳn "tuyên vô tội, đình chỉ vụ án"); đáng chú ý là Điều 358 (sai) rank cao hơn Điều 359 (đúng) trong mọi biến thể gộp — một fix "nới rank" cẩu thả trong tương lai có thể vô tình kéo đúng Điều SAI vào context.

[x] Fix phụ phát hiện cùng đợt điều tra mục B (đã sửa, xem thay đổi riêng): `_is_fallback_answer()` kiểm tra substring "không tìm thấy nội dung liên quan" trên TOÀN VĂN BẢN khiến 1 câu trả lời gộp nhiều câu hỏi con bị coi là fallback toàn bộ chỉ vì 1 phần fallback, xóa sạch citations của những phần đã trích đúng (ví dụ nhận định 4 trích đúng Điều 174 vẫn bị xóa vì Câu 2 fallback). Sửa: `citations` không còn gate theo `is_fallback` nữa, chỉ dựa vào `actually_cited_primary` (đã extraction-based sẵn) — `related_articles` vẫn giữ gate như cũ. Test lại đúng case 6 câu UAT (2 lần, real API): citations giữ được (không còn bị xóa về `[]`) dù `is_fallback=True` do Câu 2 vẫn fallback. 29 câu eval không hồi quy (exact_match 100%, groundedness 100%, correct-refusal 100%, academic-reference usage 100%).

[x] Case study đặc biệt phát hiện trong lúc điều tra mục B — nhận định 3 (tạm giam người dưới 18 tuổi) fallback KHÔNG PHẢI bug ingestion: xác nhận corpus thiếu hoàn toàn Chương XXVIII BLTTHS (Điều 413-430, "Thủ tục tố tụng đối với người dưới 18 tuổi") — gap thật trong `ingestion/chunks.json` (Điều 412 nhảy thẳng sang Điều 431). Ban đầu nghi ngờ lỗi parse bỏ sót 1 khoảng Điều. Đọc trực tiếp đúng trang PDF gốc `Bộ luật TTHS.pdf` (trang 200-201, `pdfplumber`, không đoán) phát hiện SỰ THẬT KHÁC HẲN: văn bản hợp nhất ghi rõ "Chương XXVIII (được bãi bỏ)" kèm chú thích số 203: "Chương này được bãi bỏ theo quy định tại điểm i khoản 2 Điều 177 của Luật Tư pháp chưa thành niên số 59/2024/QH15, có hiệu lực kể từ ngày 01 tháng 01 năm 2026." Đây KHÔNG PHẢI thiếu sót ingestion — corpus đang phản ánh ĐÚNG thực tế pháp lý hiện hành (bãi bỏ đã có hiệu lực tính đến thời điểm audit). Nếu "khôi phục" nội dung Điều 413-430 vào corpus như luật hiện hành sẽ là DẠY SINH VIÊN 1 QUY ĐỊNH ĐÃ HẾT HIỆU LỰC — rủi ro nghiêm trọng hơn nhiều so với fallback hiện tại. Đã grep toàn bộ `chunks.json` xác nhận thêm: không có nội dung thực chất nào của Luật Tư pháp người chưa thành niên số 59/2024/QH15 được ingest ở bất kỳ tài liệu nào trong corpus (chỉ có 41 chunk nhắc lướt cụm "chưa thành niên" trong giáo trình/đề cương khác, không phải Điều luật của chính luật này). KẾT LUẬN: fallback hiện tại cho câu hỏi loại này là HÀNH VI ĐÚNG (trung thực khi không có căn cứ), không phải thiếu sót cần sửa gấp — không ingest gì thêm trong đợt sửa này.

[x] Đính chính điều tra nhận định 4 (thời hạn điều tra bổ sung "vòng qua Thông tư liên tịch thay vì trích thẳng Điều 174") — kết luận trước đó trong mục B ("Điều 174 CÓ trong context nhưng model không trích") SAI, do 2 lỗi trong chính phương pháp điều tra, không phải trong hệ thống: (a) nhầm lẫn "lọt top-25 của pool semantic top-1000" (kết quả từ script probe độc lập) với "được chọn vào `legal_primary`" — đây là 2 bước KHÁC NHAU trong pipeline thật (`retrieve_context` còn áp `LEGAL_PRIMARY_COUNT=8` + `MAX_PRIMARY_PER_SOURCE_DOCUMENT` sau bước rank thô), script probe ban đầu chỉ đo bước rank thô rồi kết luận nhầm sang bước sau; (b) bug dedupe trong chính script chẩn đoán: gom nhóm chỉ theo `dieu_number` (chuỗi số) thay vì cặp `(source_document, dieu_number)`, khiến "Điều 14" in ra bị hiểu nhầm là Điều 14 BLTTHS trong khi thực chất là Điều 14 của Thông tư liên tịch 01/2026 (2 văn bản khác nhau tình cờ cùng đánh số Điều 14) — một bug tưởng vô hại nhưng đủ để lái toàn bộ kết luận điều tra sai hướng.
  Kết luận ĐÚNG sau khi sửa lại cách đo (gọi trực tiếp `retrieve_context` qua pipeline thật, dedupe theo cặp document+Điều, 8 lần chạy độc lập, real API): Điều 174 BLTTHS **chưa bao giờ** vào `legal_primary` hay `legal_related` (0/8 lần) — 3/8 slot primary bị Thông tư liên tịch 01/2026 chiếm (Điều 14, 18, 19 của chính Thông tư này, không phải BLTTHS). Việc model trích "khoản 2 Điều 174" trong câu trả lời là do model đọc lại đúng 1 câu cross-reference có sẵn NGUYÊN VĂN trong nội dung Điều 19 Thông tư liên tịch ("...không được quá thời hạn điều tra bổ sung quy định tại khoản 2 Điều 174") — không phải model tự suy luận, càng không phải hallucination; model chỉ dùng đúng và duy nhất nguồn nó thực sự nhận được.
  Đây là BIẾN THỂ THỨ 2 của cùng root cause đã ghi ở mục A/B (retrieval crowding do 1 vector embedding không mã hóa được nhiều chủ đề trong 1 tin nhắn gộp) — khác mục A/B ở chỗ lần này văn bản HƯỚNG DẪN THI HÀNH (Thông tư liên tịch) cạnh tranh thắng và chiếm slot của văn bản LUẬT GỐC (BLTTHS), thay vì các Điều "họ hàng" cùng một văn bản chiếm chỗ lẫn nhau như mục A.
  QUYẾT ĐỊNH: KHÔNG thêm rule ưu tiên nguồn gốc luật (BLTTHS/BLHS trước Thông tư/Nghị định) vào RAG_SYSTEM_PROMPT như đề xuất ban đầu — rule đó không giải quyết được root cause thật (Điều 174 chưa từng tới context nên không có gì để "ưu tiên" trong lúc generate), đồng thời có rủi ro tác dụng phụ thật: có thể khiến model né tránh trích cả nội dung Thông tư liên tịch hợp lệ trong trường hợp nó LÀ nguồn duy nhất đúng cho câu hỏi. Đóng việc này lại, không sửa generation-prompt riêng lẻ cho case này — chờ chung giải pháp retrieval tổng thể ở Việc 3 (tách câu hỏi nhiều chủ đề thành nhiều truy vấn/embedding riêng).

Bài học phương pháp luận (đáng đưa vào bài báo, cùng nhóm với bài học thời gian hiệu lực ở case study Chương XXVIII): khi điều tra bug bằng SCRIPT CHẨN ĐOÁN RIÊNG thay vì gọi trực tiếp đúng hàm/pipeline production, phải cẩn trọng xác nhận từng bước trung gian của script khớp ĐÚNG logic thật của hệ thống, không chỉ khớp về mặt khái niệm. Hai cái bẫy cụ thể đã tự mắc phải: (1) "lọt vào một tập hợp lớn hơn ở bước đầu" (rank trong pool top-1000) không đồng nghĩa "được chọn vào tập hợp con cuối cùng dùng cho generation" (`legal_primary` sau các bước lọc/cap riêng) — kết luận rút ra từ bước trung gian mà không verify tới bước cuối là kết luận chưa đủ căn cứ; (2) một logic dedupe/group tưởng chừng vô hại (theo số Điều) có thể âm thầm gộp nhầm 2 thực thể khác nhau làm một khi corpus có nhiều văn bản dùng chung cách đánh số Điều (rất phổ biến ở văn bản pháp luật Việt Nam - BLTTHS, BLHS, Nghị định, Thông tư liên tịch đều tự đánh số Điều từ 1) - luôn dùng khóa đầy đủ `(source_document, dieu_number)` khi so sánh/gộp Điều giữa các văn bản khác nhau, không bao giờ dùng riêng `dieu_number`.

[ ] Việc cần làm sau (mở rộng scope corpus, KHÔNG phải bug, không gộp vào đợt sửa hiện tại): ingest Luật Tư pháp người chưa thành niên số 59/2024/QH15 làm 1 dự án ingest riêng — cần (a) xác nhận nguồn chính thức (Cổng thông tin Chính phủ/Quốc hội, không tự ý lấy nguồn không xác thực cho nội dung sẽ dạy sinh viên), (b) chạy đúng quy trình ingest đầy đủ đã có (title-truncation check, Chương/Mục/Phần boundary, extraction_quality theo Khoản, OCR fallback nếu cần, spot-check thủ công, test hồi quy title-truncation/boundary/quality), (c) không gộp vội vào đợt sửa hiện tại vì đây là bổ sung nguồn luật mới hoàn toàn, khác bản chất so với sửa retrieval/code trên corpus đã có.

Bài học tổng quát (đáng chú ý nhất trong toàn bộ chuỗi audit retrieval của dự án, đáng đưa vào bài báo): hệ thống RAG grounding vào văn bản luật cần tính tới yếu tố THỜI GIAN HIỆU LỰC — 1 văn bản "đầy đủ" tại thời điểm ingest vẫn có thể có phần đã bị bãi bỏ bởi luật khác ban hành sau (văn bản hợp nhất tự ghi chú rõ điều này qua footnote, nhưng chỉ ai đọc kỹ mới thấy). Việc phát hiện đúng nguyên nhân (đọc kỹ chú thích trong chính văn bản gốc, không mặc định "thiếu dữ liệu = lỗi ingest") quan trọng hơn hẳn việc cố "lấp đầy" mọi khoảng trống retrieval bằng mọi giá — lấp sai chỗ này (khôi phục luật đã bãi bỏ) sẽ tạo ra một loại lỗi còn nguy hiểm hơn cả lỗi đang cố sửa: hệ thống tự tin trích dẫn một quy định không còn hiệu lực.

Feature — Việc 3: Tách câu hỏi nhiều chủ đề trước khi retrieval (giải quyết tận gốc "embedding dilution") Bối cảnh: mục A/B đã xác định root cause của nhiều case fallback/sai — khi 1 tin nhắn chứa nhiều câu hỏi con thuộc chủ đề pháp lý khác nhau (ví dụ 4 nhận định + 2 tình huống), toàn bộ tin nhắn bị embed thành 1 vector duy nhất, pha loãng tín hiệu tới mức Điều luật đúng của từng câu con rớt hạng nặng (rank #1 khi hỏi riêng → hạng vài trăm khi gộp chung). Không sửa được bằng nới top_k/primary_count vì mức độ dilution quá lớn.

Thiết kế: tách 1 tin nhắn nhiều câu hỏi con thành các sub-query riêng NGAY TỪ Query Understanding, retrieval ĐỘC LẬP cho từng sub-query (mỗi câu con có vector embedding sạch, không bị pha loãng bởi câu khác), rồi build context có cấu trúc rõ ràng cho generation.

[x] Bước 1 — Phát hiện + tách câu hỏi nhiều chủ đề: mở rộng Query Understanding, thêm khả năng trả về mảng sub_questions thay vì 1 rewritten_question duy nhất khi phát hiện TÍN HIỆU CẤU TRÚC RÕ RÀNG - gồm CẢ đánh số/nhãn tường minh ("1./2./3.", "Nhận định 1/2/3", "Trường hợp 1/2", "Câu 1/2"...) LẪN nhiều câu hỏi độc lập nối tiếp không cần nhãn khi có tín hiệu phân tách rõ ràng (mỗi ý kết thúc bằng dấu "?" riêng, hỏi về 2 đối tượng/khái niệm khác nhau) - vẫn CHỈ dựa vào tín hiệu quan sát được trong văn bản (không đoán ngữ nghĩa mơ hồ "câu này có vẻ phức tạp"), tránh kích hoạt nhầm cho câu hỏi phức tạp nhưng là 1 câu hỏi thống nhất. Mỗi sub_question giữ nguyên nội dung/từ ngữ gốc của câu con đó (không paraphrase mất chi tiết).
  Phát hiện khi test: hành vi thực tế RỘNG HƠN mô tả ban đầu (ban đầu chỉ dự kiến đánh số/nhãn tường minh) - model tự nhận diện được câu hỏi mẫu mục A ("Viện kiểm sát nào có thẩm quyền quyết định việc truy tố...? Viện kiểm sát cấp nào có trách nhiệm thực hành quyền công tố...?", KHÔNG có nhãn "1./2." nào) là 2 sub_questions độc lập, nhất quán 3/3 lần chạy. Đã verify KHÔNG gây false-positive qua 4 case control khác cũng có 2 dấu "?" nhưng cùng 1 chủ đề thống nhất (ví dụ "Điều 173 BLHS quy định gì về tội trộm cắp tài sản? Mức hình phạt cao nhất là bao nhiêu?", "Phòng vệ chính đáng là gì và khi nào được coi là vượt quá giới hạn?") - cả 4 case này đều đúng sub_questions=[] như kỳ vọng. QUYẾT ĐỊNH: giữ nguyên hành vi này (không siết chặt chỉ còn đánh số tường minh) - đây là hành vi tốt hơn dự kiến ban đầu, đúng tinh thần "tín hiệu cấu trúc quan sát được" (mỗi ý có dấu "?" riêng vẫn là tín hiệu cấu trúc, không phải suy đoán ngữ nghĩa thuần túy), và giải quyết được bonus cho chính case mục A (2 câu hỏi con map tới 2 Điều khác nhau, Điều 239 và Điều 268, vốn cũng bị embedding dilution như mục B).
[x] Bước 2 — Retrieval độc lập từng sub_question: thêm hàm `retrieve_context_for_subquestions()` (`backend/app/services/rag_service.py`) gọi `retrieve_context()` RIÊNG cho từng sub_question qua `asyncio.gather` (mỗi câu có legal_primary/legal_related riêng, dùng đúng cơ chế top_k=25/primary_count=8/diversity-aware đã có nguyên vẹn - không đổi logic retrieval đã ổn định, chỉ gọi nhiều lần thay vì 1 lần, chạy concurrent nên không cộng dồn latency tuyến tính). CHƯA wire vào `stream_answer_question`/pipeline chat thật (Bước 3) - hàm đứng độc lập, test trực tiếp không qua API.
  Test bắt buộc (case UAT 6 câu, real API) - bảng so sánh rank/score Điều đúng qua 3 cách hỏi:

  | Sub-question | Điều đúng | Hỏi-một-mình (mục B) | Gộp-chung-cũ (mục B) | Tách-riêng-mới (Bước 1+2) |
  |---|---|---|---|---|
  | Nhận định 1 | 49 | #1 | #16 | #1 - VÀO legal_primary |
  | Nhận định 2 | 72 | #46 | #230 | #96 - vẫn MISS |
  | Nhận định 3 | (không có, Chương XXVIII đã bãi bỏ) | - | - | không có gì để trích, đúng kỳ vọng |
  | Nhận định 4 | 174 | #1 | #20-28 (chưa từng vào primary) | #1 - VÀO legal_primary |
  | Câu 2 TH1 | 359 | #1 | #425-466 | #3 - VÀO legal_primary |
  | Câu 2 TH2 | 357 | #1 | #30-35 | #1 - VÀO legal_primary |

  KẾT QUẢ: 4/5 Điều có ground truth (49, 174, 359, 357) giờ lọt `legal_primary` thật sự sau khi tách - rank gần khớp với "hỏi một mình", xác nhận tách câu hỏi khắc phục đúng root cause dilution đã xác định ở mục A/B. Điều 72 (nhận định 2) vẫn MISS nhưng KHÔNG phải do dilution (đã loại trừ bằng chính cột "hỏi một mình" - Điều 72 solo đã rank #46, ngoài top-25 ngay cả khi không có câu nào khác cạnh tranh) - nội dung "hai tư cách" nằm ở khoản 4b, một sub-clause nhỏ bên trong Điều lớn "Người bào chữa", bản thân yếu về embedding, là giới hạn retrieval riêng không liên quan gì tới việc tách câu hỏi, ngoài phạm vi Bước 1+2.
  Không hồi quy theo thiết kế (không chỉ theo test): `sub_questions`/`retrieve_context_for_subquestions()` chưa được gọi ở bất kỳ đâu trong `chat.py`/`stream_answer_question` - hành vi phục vụ user hiện tại không thể bị ảnh hưởng, không cần chạy 29 câu eval cho riêng bước này.
  Việc 3 Bước 3 (build context có cấu trúc cho generation + wire vào `chat.py`/`stream_answer_question` thật) đã bắt đầu implement nhưng test ngay lập tức phát hiện ra vi phạm rule 9 (case Điều 419, nhận định 3) không liên quan gì tới Việc 3 - đã TẠM DỪNG Bước 3 để ưu tiên điều tra/sửa rule 9 trước (xem mục dưới). Bước 3 vẫn đứng riêng, chưa test lại/commit.

Fix — RAG_SYSTEM_PROMPT rule 9 (cấm trích số Điều chưa được retrieval xác thực) bị vi phạm bởi academic_reference: phát hiện khi test Việc 3 Bước 3 (case Điều 419, nhận định 3) - model trích "(Điều 419)" dù Điều 419 chưa từng có trong `legal_primary`, chỉ xuất hiện như ví dụ minh họa BÊN TRONG nội dung một chunk `academic_reference`. Điều tra rộng xác nhận đây không phải case đơn lẻ - cùng pattern xảy ra ở câu "Phân tích mối quan hệ và tính thống nhất giữa LHS và LTTHS" (trích Điều 13/298/33/368/369, trong đó 13/33/298 leak từ academic_reference, còn 368/369 là hallucination thuần túy - không hề xuất hiện trong bất kỳ chunk nào được retrieve).

[x] Bước 1 — Đo baseline thật trước khi sửa: thêm metric `citation_grounding_rate` vào `backend/evaluation/run_evaluation.py`, chạy cho TOÀN BỘ 29 câu (không chỉ 2 câu academic-only) - tách riêng mọi số Điều model viết ra trong câu trả lời, đối chiếu với `legal_primary` thật sự được retrieve cho đúng câu hỏi đó (tái sử dụng `DIEU_NUMBER_PATTERN`). Sửa 1 false-positive trong lúc build: "được phép" phải là hợp của (a) `dieu_number` tiêu đề khối VÀ (b) mọi số Điều xuất hiện NGAY BÊN TRONG nội dung chunk đó (một Điều luật thật hay tự trích dẫn chéo Điều khác trong chính nội dung nó, ví dụ Điều 155 BLTTHS trích "các điều 134, 135, 136..." - hợp lệ, không phải vi phạm). Baseline: `mean_rate=97%`, `pooled_rate=89% (39/44 Điều)`, đúng 1 câu vi phạm (câu LHS-LTTHS ở trên).
[x] Bước 2.1 — Mở rộng rule 9 (`rag_prompts.py`): bổ sung 2 dạng vi phạm mới quan sát được ngoài dạng "so sánh 2 giai đoạn/chủ thể" cũ - "đáp án nhận định Đúng/Sai kèm căn cứ pháp lý" và "phân tích lý luận nhắc nhiều số Điều minh họa" - kèm 1 lưu ý ngược lại (Điều tự trích dẫn chéo bên trong 1 khối đã hợp lệ vẫn được phép). Test riêng prompt-only: KHÔNG đủ - lặp lại 20 lần độc lập case LHS-LTTHS, vẫn 20/20 (100%) vi phạm, vượt xa ngưỡng >10-15% đã thống nhất trước để quyết định có cần guard code-level hay không.
[x] Bước 2.2 — Guard code-level (buffer có chọn lọc, không phải toàn bộ `legal_question`): `rag_service.py` thêm `_rule9_ungrounded_dieu_numbers()` (cùng logic với eval script), kích hoạt buffer-thay-vì-stream-token cho đúng tập câu hỏi có `retrieval.used_academic_reference=True` (không phải "legal_primary yếu/rỗng" như đề xuất ban đầu - đã verify case thật có `legal_primary` khỏe mạnh, 6 items, vẫn vi phạm 100%, nên trigger đúng là "có dùng academic_reference" chứ không phải "thiếu context"). Vi phạm phát hiện trước khi gửi client → thay nguyên văn bằng `RULE9_VIOLATION_FALLBACK_ANSWER` (cùng pattern "thay nguyên khối, không patch từng chỗ" đã dùng cho leak ẩn danh mục C). Đường stream thường (không dùng academic_reference) giữ nguyên live-streaming, chỉ log cảnh báo (log-only, chưa phải guard) vì rủi ro đo được thấp hơn nhiều. Verify: 10/10 lần chặn thành công trên case LHS-LTTHS, "419"/"13"/"298"/... không bao giờ lọt ra client.
  KẾT QUẢ sau sửa (so baseline): `mean_rate=100%`, `pooled_rate=100% (42/42 Điều)`. Không hồi quy: citation accuracy/groundedness/correct-refusal vẫn 100%. Đánh đổi CHẤP NHẬN: `academic_reference_usage` giảm 100%→50% (1/2) - câu LHS-LTTHS giờ LUÔN fallback thay vì trả lời. Đã điều tra 1 bước trước khi chấp nhận (không phải quyết định vội): đọc trực tiếp chunk academic_reference, xác nhận 13/33/298 là ví dụ minh họa THẬT trong tài liệu gốc (cùng pattern Điều 419), còn 368/369 hallucination hoàn toàn không có trong bất kỳ context nào được retrieve. Kiểm tra khả năng mở rộng retrieval: nguồn academic tự nhắc tới dải rộng Điều 7-33 (26 nguyên tắc, cả 1 chương BLTTHS) chỉ cho 1 câu hỏi so sánh mở - không có cách nới `LEGAL_PRIMARY_COUNT`/retrieval hợp lý nào vét hết một cách đáng tin cậy, và phần hallucination (368/369) không truy được về bất kỳ input nào để retrieval "sửa" - kết luận: fallback là lựa chọn đúng cho case này (honest refusal hơn là trích dẫn tự tin nhưng sai), không phải thất bại của retrieval.
[x] Migration `backend/migrations/0008_chat_query_logs_rule9_grounding.sql` (cột `rule9_ungrounded_dieu_numbers jsonb` + index) - đã chạy trong Supabase SQL editor, wire vào `chat_log_service.py` đã hoàn thành, verify ghi đúng qua real API (case vi phạm ghi đúng list Điều bắt được dù answer đã bị fail-closed thay thế; case sạch ghi `[]`; intent không phải legal_question ghi `null`; không có lỗi INSERT).
[x] Bước 3 — Build context có cấu trúc cho generation + wire vào pipeline thật: `build_multi_part_user_prompt()` gắn nhãn "PHẦN i" cho từng sub_question cùng context riêng từ Bước 2, `RAG_MULTI_PART_ADDENDUM` yêu cầu model trả lời từng PHẦN CHỈ dùng context của đúng PHẦN đó (không mượn Điều luật chéo). Wire vào `chat.py` → `stream_answer_question(sub_questions=...)`: khi `sub_questions` có ≥2 phần và không đi kèm `needs_anonymization`, vào nhánh multi-part; ngược lại nhánh single-question cũ giữ nguyên 100% hành vi (streaming bình thường, guard rule 9 chỉ log-only trừ khi `used_academic_reference`).
  Guard citation-grounding cho nhánh multi-part: LUÔN buffer toàn bộ (quyết định đã chốt, không đo lường theo tỉ lệ vi phạm như nhánh single-question - vì đây là traffic nhỏ và rủi ro "mượn Điều chéo PHẦN" lớn hơn). Check mọi Điều trong câu trả lời so với HỘI của `legal_primary` từ MỌI sub_question (tái dùng `_rule9_ungrounded_dieu_numbers`) - 1 PHẦN trích Điều chỉ được retrieve cho PHẦN khác cũng là vi phạm rule 9 y hệt leak từ academic_reference. Vi phạm → fail-closed, ghi `rule9_ungrounded_dieu_numbers`.
  Bug phát hiện khi test (không liên quan rule 9): case UAT 6 câu (5 phần, đã bỏ Nhận định 3 để tránh trigger rule 9 guard) - 3/3 lần model (chạy trên `gemini-3.1-flash-lite` do `gemini-3.1-pro-preview` timeout 100% trong môi trường test, luôn rơi về fallback model) BỎ HẲN PHẦN 1-3, chỉ trả lời PHẦN 4-5, dù context riêng từng PHẦN đã đúng (xác nhận qua log). Đã loại trừ nguyên nhân do code (verify `stream_generate_answer`'s fallback logic không làm rơi nội dung) và do quy mô multi-part nói chung (case 2 PHẦN tối giản: 2/2 lần trả lời ĐÚNG cả 2 phần, đúng Điều 49/53 và 174, không mượn chéo) - bug chỉ xảy ra ở quy mô ≥5 PHẦN dưới fallback model.
  Fix: thêm completeness guard `_multipart_missing_parts()` (`rag_service.py`) - sau buffer, check đủ N nhãn "PHẦN i" có xuất hiện trong câu trả lời không (regex khớp lỏng, tolerant định dạng). Thiếu bất kỳ phần nào → fail-closed (tái dùng `RULE9_VIOLATION_FALLBACK_ANSWER`), ghi `multipart_missing_parts`. Chạy SAU rule 9 guard (nếu rule 9 đã fail-closed thì bỏ qua completeness, tránh check trên text đã bị thay). Test: 5 PHẦN thiếu, 6/6 lần bị chặn đúng (`missing PHAN [1,2,3] of 5`); UAT 6 câu đầy đủ (rule 9 guard bắt trước do Nhận định 3), 3/3 lần - 2 guard không xung đột, không double-trigger; case 2 PHẦN, 3/3 lần KHÔNG bị chặn oan.
  Migration `backend/migrations/0009_chat_query_logs_multipart_completeness.sql` (cột `multipart_missing_parts jsonb` + index) - đã chạy, wire vào `chat_log_service.py`, verify ghi đúng qua real API (case thiếu phần ghi đúng `[1,2,3]`, case single-question ghi `null`, không lỗi INSERT).
  29 câu eval sau toàn bộ Việc 3: `exact_match_rate=95%` (baseline 100%, 1 câu lệch: thiếu Điều 87 trong case "vai trò chứng cứ", KHÔNG qua nhánh multi-part - nhiều khả năng do cùng nguyên nhân môi trường flash-lite fallback đang ảnh hưởng toàn bộ phiên test, không phải hồi quy từ code Việc 3), `mean_recall=98%` (baseline 100%), `groundedness=100%`, `correct-refusal=100%`, `citation_grounding pooled=100% (38/38)`, `academic_reference_usage=50%` (không đổi).
  Rủi ro còn tồn đọng, chưa giải quyết gốc rễ: nguyên nhân `gemini-3.1-pro-preview` timeout 100% trong môi trường test chưa rõ (có thể chỉ là vấn đề tạm thời của sandbox/khu vực, không nhất thiết xảy ra trên production) - nếu preview model cũng kém ổn định trên production, nhánh multi-part với ≥4 PHẦN sẽ thường xuyên fail-closed về câu an toàn chung chung thay vì trả lời thật. Theo dõi qua cột `multipart_missing_parts` trong `chat_query_logs` sau khi lên production.

Việc 3 — ĐÃ HOÀN THÀNH (Bước 1+2+3 + completeness guard)
Bước 3: build context có cấu trúc (mỗi sub_question nhãn "PHẦN i" + context riêng), buffer toàn bộ câu trả lời (không stream token-by-token cho nhánh multi-part, đánh đổi latency lấy an toàn — quyết định đã chốt), 2 lớp guard độc lập chạy tuần tự sau generate: (1) rule 9 citation-grounding, (2) completeness (đủ N nhãn PHẦN) — chỉ chạy khi (1) đã sạch, tránh double-check.
Bug phát hiện trong lúc test: với ≥4-5 phần dưới model fallback (flash-lite, do pro-preview timeout 100% trong môi trường test), model có xu hướng bỏ sót các phần đầu, chỉ trả lời phần cuối — độc lập với rule 9, chưa từng được thiết kế để phát hiện trước đó. Đã thêm completeness guard xử lý đúng.
Kết quả cuối: case UAT 6 câu — rule 9 guard bắt đúng (Điều 419 đã bãi bỏ), case 5 câu (loại trigger rule 9) — completeness guard bắt đúng 6/6 lần model bỏ phần, case 2 câu (regression) — cả 2 guard không chặn oan, Điều đúng khớp ground truth, không mượn chéo giữa các phần.
Giới hạn còn theo dõi: nguyên nhân gemini-3.1-pro-preview timeout 100% trong môi trường test chưa rõ (có thể là vấn đề tạm thời của sandbox, không chắc phản ánh production) — guard đã che chắn hậu quả (không lọt câu trả lời thiếu phần ra client), nhưng nếu preview model kém ổn định tương tự trên production, nhánh multi-part ≥4 phần sẽ thường fallback về câu an toàn chung chung thay vì trả lời thật — cần theo dõi qua cột multipart_missing_parts sau khi có dữ liệu thật từ user.

Feature — "Cách mạng" retrieval: audit corpus quy định đã bãi bỏ (C) + HyDE (B) + LLM re-ranking (A) Thứ tự triển khai: C độc lập, làm song song. B trước A (đổi input trước, xử lý output sau) — đo riêng từng bước để biết mức đóng góp thật, không đổi 2 biến cùng lúc.

[x] C — Audit chủ động toàn corpus tìm quy định đã bãi bỏ/hết hiệu lực: grep toàn bộ `ingestion/chunks.json` (2629 chunk, 17 văn bản) với các cụm "bãi bỏ", "hết hiệu lực", "thay thế bởi", "không còn áp dụng", "được thay thế". Đa số hit "được thay thế" là nhiễu (thay thế cụm từ trong văn bản hợp nhất, ví dụ "chính quyền địa phương" → "Ủy ban nhân dân", hoặc thay thế người — thẩm phán/kiểm sát viên dự khuyết — không phải bãi bỏ quy định). Đọc kỹ từng case còn lại, đối chiếu số chú thích với vị trí đánh dấu inline để phân biệt chú thích thật thuộc về Điều đang đọc với chú thích bị xén lẫn vào chunk kế bên do PDF tách trang (chú thích ở cuối trang bị gộp vào đoạn văn bản của Điều kế tiếp cùng trang — cùng cơ chế đã thấy ở case Chương XXVIII). Kết quả:
— Bãi bỏ TOÀN BỘ Điều (is_repealed=true, 3 chunk): Điều 63, Điều 79, Điều 82 (Luật Tổ chức TAND) — cùng bị bãi bỏ theo khoản 23 Điều 1 Luật số 81/2025/QH15, hiệu lực 01/07/2025.
— Bãi bỏ MỘT PHẦN (has_repealed_clause=true, phần còn lại của Điều vẫn hiệu lực, 8 chunk): Điều 4 khoản 2 điểm a/d/g (BLTTHS, theo Luật 99/2025/QH15, hiệu lực 01/07/2025); Điều 39 khoản 1 điểm đ (BLTTHS, theo Luật Tư pháp NCTN 59/2024/QH15, hiệu lực 01/01/2026); Điều 161 khoản 1 điểm c (BLTTHS, theo Luật TCTAND 34/2024/QH15, hiệu lực 01/01/2025); Điều 326 khoản 7 (BLTTHS, theo Luật TCTAND 34/2024/QH15, hiệu lực 01/01/2025); Điều 62 khoản 2 (Luật TCTAND, theo Luật Tòa án chuyên biệt TTTCQT 150/2025/QH15, hiệu lực 01/01/2026); Điều 122 khoản 2 và Điều 127 khoản 2 (Luật TCTAND, theo Luật 81/2025/QH15, hiệu lực 01/07/2025).
— Gap ngoài corpus (không có chunk để đánh dấu, chỉ ghi nhận): Chương XXVIII BLTTHS Điều 413-430 (đã biết, xem case study Việc 2 phía trên) + 1 case MỚI phát hiện — 1 Mục (chứa Điều 50-54, nằm giữa Điều 49a và Điều 55) trong Luật Tổ chức TAND bị bãi bỏ theo khoản 23 Điều 1 Luật 81/2025/QH15 (hiệu lực 01/07/2025) và hoàn toàn vắng mặt trong corpus — giống hệt cơ chế Chương XXVIII, corpus đang phản ánh đúng thực tế (không cần backfill).
— Chỉ đánh dấu metadata trong `ingestion/chunks.json` (file không track git, đã cập nhật trực tiếp), CHƯA đổi hành vi RAG/retrieval nào ở bước này — để dành cho guard tương lai.

[x] C tiếp theo — dùng metadata is_repealed/has_repealed_clause để bảo vệ chủ động trong RAG pipeline (làm trước B vì là rủi ro thật): thêm `is_repealed`/`repealed_note`/`has_repealed_clause`/`repealed_clause_note` vào payload whitelist (`ingestion/vector_store.py chunk_to_point`) + index BOOL riêng cho `is_repealed`; patch trực tiếp 11 point đã có trong Qdrant qua `set_payload` (script mới `ingestion/patch_repealed_metadata.py`, không cần re-embed vì chunk_text không đổi). Backend (`backend/app/services/rag_service.py`): (1) mọi truy vấn legal_text (`_retrieve_legal_exact`, `_retrieve_semantic`) giờ `must_not` loại is_repealed=true khỏi kết quả — 3 chunk Điều 63/79/82 (Luật TCTAND) không bao giờ vào được legal_primary dù điểm cao thế nào; (2) hàm mới `_retrieve_repealed_dieu` + short-circuit ngay trong `stream_answer_question` (trước khi gọi retrieve_context): câu hỏi gọi đúng số Điều đã bãi bỏ toàn bộ trả lời thẳng "Điều X ... đã bị bãi bỏ ... theo [văn bản] ... hiệu lực [ngày]" thay vì fallback chung chung hay trích nội dung cũ; (3) 8 chunk has_repealed_clause=true vẫn dùng được làm legal_primary (phần lớn Điều còn hiệu lực) nhưng `format_legal_context_block` (`backend/app/prompts/rag_prompts.py`) chèn thêm dòng "[CẢNH BÁO HIỆU LỰC: ...]" nêu đúng khoản/điểm đã bãi bỏ + văn bản/ngày thay thế, cộng rule 11 mới trong RAG_SYSTEM_PROMPT dạy model không trích phần đó làm căn cứ hiện hành nếu câu hỏi chạm đúng phần đó.
Test qua real API (in-process, gọi thẳng `stream_answer_question` — không có tài khoản EVAL_USER_EMAIL/PASSWORD trong session này nên không qua được HTTP endpoint, nhưng vẫn là Gemini+Qdrant thật, không mock, cùng kiểu direct-call đã dùng cho các audit rank/score trước đây): hỏi "Điều 63 Luật Tổ chức Tòa án nhân dân quy định gì?" → trả lời đúng "đã bị bãi bỏ theo khoản 23 Điều 1 Luật số 81/2025/QH15, hiệu lực 01/07/2025", không trích nội dung cũ; hỏi đúng Điều 4 khoản 2 điểm a BLTTHS ("giải thích từ ngữ Cơ quan điều tra") → model tự nhận diện đúng phần này đã bãi bỏ theo Luật 99/2025/QH15, không dùng làm căn cứ hiện hành.
Chạy lại 29 câu eval (cùng phương thức in-process real-API do thiếu tài khoản eval cho HTTP path): citation_accuracy 100% (20/20), correct_refusal 100% (7/7), groundedness 96.5% (28/29) — 1 fail duy nhất là case "Phân tích mối quan hệ LHS-LTTHS" đã biết trước và chấp nhận từ commit trước (rule 9 citation-grounding guard fail-closed đúng như thiết kế, không phải hồi quy mới, không liên quan tới 11 chunk vừa đánh dấu).

[ ] B — HyDE (Hypothetical Document Embeddings): trước khi embed câu hỏi để retrieval, sinh 1 đoạn văn giả định "trông như câu trả lời lý tưởng" (giọng văn luật, không phải giọng câu hỏi tình huống) bằng 1 lời gọi Gemini nhẹ, embed đoạn đó thay vì câu hỏi gốc. Giả thuyết: giải quyết đúng gốc rễ dilution/mismatch giọng văn giữa câu hỏi tình huống và văn bản luật. Test bằng đúng các case chẩn đoán đã biết trước đây (Điều 298, Điều 280, case Điều 165/110 "crowding" trùng từ vựng bề mặt) — đo rank/score TRƯỚC/SAU khi có HyDE, so với rank khi retrieval thường (không HyDE). Chạy 29 câu eval, đo citation_grounding_rate/accuracy — xác nhận không hồi quy cho câu hỏi ngắn/tra cứu trực tiếp vốn đã hoạt động tốt (rủi ro: HyDE có thể "diễn giải" lệch câu hỏi đơn giản).

[x] A — LLM re-ranking: implement xong trên nhánh legal_text semantic (`_rerank_legal_candidates` + `_retrieve_legal` trong `backend/app/services/rag_service.py`, prompt/schema mới `RERANK_SYSTEM_PROMPT`/`RERANK_RESPONSE_SCHEMA`/`build_rerank_user_prompt` trong `rag_prompts.py`). Dedup top-25 ứng viên (chunk-level) xuống 1 dòng/Điều TRƯỚC khi đưa vào re-rank (đúng fix cho vấn đề "Điều 15 nhiều Khoản chiếm nhiều slot" đã phát hiện ở B) - 1 lời gọi Gemini nhẹ chấm điểm 0-10 cho từng Điều DUY NHẤT, đọc câu hỏi GỐC (không phải HyDE passage). Exact-match Điều vẫn luôn ưu tiên tuyệt đối, không qua re-rank. Fail-closed về đúng thứ tự similarity cũ nếu lời gọi Gemini lỗi/JSON hỏng (không vỡ request).

Test case Điều 109 (tinhhuong-q4) - đo đủ 4 tổ hợp (baseline/B-only/A-only/A+B) để tách bạch đóng góp riêng của A:
- baseline (không B không A): 109 có mặt primary (rank 4), 117 có mặt (rank 6), 123 KHÔNG có mặt (rank 12, ngoài top-8).
- B-only (HyDE, không A): 109 BỊ LOẠI khỏi primary (rank rớt xuống 19 trong toàn corpus), 117 có mặt, 123 vẫn không có mặt - đây là vấn đề đã ghi ở B.
- **A-only (re-rank trên vector KHÔNG qua HyDE)**: cả 3 Điều 109/117/123 đều có mặt trong primary - A một mình giải quyết ĐÚNG vấn đề crowding, không cần B.
- **A+B (đúng scope nhiệm vụ này - re-rank trên vector ĐàQUA HyDE)**: 117 và 123 có mặt, nhưng 109 VẪN BỊ LOẠI. Nguyên nhân xác nhận bằng cách gọi thẳng `_retrieve_semantic` với vector HyDE: Điều 109 không hề xuất hiện trong 25 chunk thô đầu tiên lấy về từ Qdrant (Điều 15 một mình chiếm 5/25 slot, cộng nhiều Điều hành chính khác) - B đã loại 109 khỏi pool NGAY TỪ BƯỚC LẤY DỮ LIỆU THÔ, trước khi A kịp chạy; A chỉ sắp xếp lại những gì đã có trong pool, không thể cứu một ứng viên chưa từng được Qdrant trả về. Đây là giới hạn thật của kiến trúc "B rồi mới A" (không phải bug logic của A) khi 2 kỹ thuật xếp chồng theo đúng thứ tự yêu cầu của nhiệm vụ.

Test 2 case còn lại (298, 280) với A+B: cả 2 vẫn có mặt trong primary bình thường (298 rank 2 sau 168 - hợp lý vì câu hỏi tự nhắc Điều 168 nhiều lần; 280 rank 1) - A không làm tệ đi những gì B đã cải thiện tốt cho các case này.

Eval 29 câu (A+B, so với B-only): exact_match 100% (không đổi), mean_recall 100% (không đổi), mean_precision 73.3% (B-only: 71.8%, nhích lên nhẹ), groundedness 100% (không đổi), correct_refusal 100% (không đổi), citation_grounding pooled_rate 97.7% (B-only: 98.0%, cùng mức nhiễu, không xấu đi đáng kể - xem giới hạn phương pháp đo bên dưới). Không câu nào hồi quy.

Latency tổng (B+A cộng dồn, 29 câu, real API): trung bình 7.86s/câu (so với B-only 6.84s/câu, so với baseline trước B ước tính ~5-6s/câu dựa trên phép đo retrieval-only riêng) - mỗi request giờ tốn thêm 2 lời gọi Gemini phụ (HyDE + re-rank) ngoài lời gọi generation chính, tổng chi phí thêm ước tính ~1.5-2.5s/request so với trước khi có B/A.

Giới hạn phương pháp đo (theo yêu cầu ghi nhận rõ, không phải bug hệ thống): `_compute_allowed_dieu_numbers` (dùng trong `run_evaluation.py` và script eval trực tiếp) tự chạy lại TOÀN BỘ retrieval độc lập lần 2 để kiểm chứng citation_grounding - vốn đã được chính `run_evaluation.py` ghi nhận là có nhiễu do query understanding không hoàn toàn deterministic giữa 2 lần gọi. Thêm HyDE (B) và re-rank (A) đưa vào TỔNG CỘNG 2 lời gọi Gemini không-deterministic bổ sung vào đúng phép re-run này (mỗi lần audit 1 câu giờ gọi lại Gemini 4 lần thay vì 2: query understanding + HyDE + re-rank + [embed x2], so với trước chỉ query understanding + embed). Quan sát thực tế: pooled citation_grounding_rate vẫn ổn định quanh 97-98% ở cả B-only và A+B (không có xu hướng xấu đi rõ rệt thêm khi cộng A), nhưng đây là 1 giới hạn CỐ HỮU của phương pháp audit "gọi lại để kiểm chứng" khi pipeline có càng nhiều bước LLM không-deterministic nối tiếp - không nên coi 1-2 vi phạm citation_grounding lẻ tẻ trong eval là bằng chứng chắc chắn của lỗi trích dẫn thật, cần đối chiếu trực tiếp với answer/citations của CHÍNH lần chạy gốc trước khi kết luận (đã làm vậy ở B, xác nhận case Nghị định 250 Điều 7 flagged sai - trích dẫn gốc thực ra đúng 100%).

[x] Union pool + cắt top-25 - phát hiện A+B (1 pool duy nhất, fetch theo vector HyDE) có thể tự loại 1 Điều đúng khỏi pool thô TRƯỚC KHI re-rank kịp chạy (case Điều 109) - fix bằng cách fetch top-25 legal_text theo CẢ HAI vector (HyDE và câu hỏi gốc, tái dùng `academic_vector` sẵn có cho câu hỏi gốc, không tốn thêm lời gọi Gemini embed), merge dedup theo `point_id` giữ điểm cao hơn nếu trùng (`_merge_semantic_pools` trong `rag_service.py`), rồi CẮT xuống top-25 theo điểm gốc trước khi đưa vào `_rerank_legal_candidates` - tránh để re-rank phải xử lý pool đôi (32-38 candidate, đo được rerank riêng lẻ 3.1-8.6s) mà không cần thiết, vì hầu hết câu hỏi không cần cả 2 pool để đạt đủ độ phủ.

Case study tổng kết hành trình B → A → Union → cắt-top-25 (đo đủ 4 cấu hình, cùng 1 bộ case chẩn đoán và cùng 29 câu eval, real Gemini + Qdrant API, không mock):

| Cấu hình | Điều 109 (tinhhuong-q4, đo lặp) | Điều 117/123 | exact_match | mean_recall | mean_precision | groundedness | correct_refusal | citation_grounding pooled | latency TB/câu (eval, gồm cả generation) | rerank component latency |
|---|---|---|---|---|---|---|---|---|---|---|
| B-only (HyDE, không re-rank) | 0/1 | 1/2 | 100% | 100% | 71.8% | 100% | 100% | 98.0% | 6.84s | - (không có bước rerank) |
| A+B (1 pool, fetch theo vector HyDE) | 0/1 | 2/2 | 100% | 100% | 73.3% | 100% | 100% | 97.7% | 7.86s | 2.1-2.5s (17-19 candidate) |
| Union+A (2 pool merge, CHƯA cắt) | ~1/1* | 2/2 | 100% | 100% | 74.5% | 100% | 100% | 97.5% | 10.26s | 3.1-8.6s (32-38 candidate) |
| **Union+A cắt top-25 (CHỐT)** | **4/5 (80%)** | 2/2 | 100% | 100% | 69.3%** | 100% | 100% | 100%** | 9.62s | **2.5-3.35s (23-25 candidate)** |

*chỉ đo 1 lần, không lặp lại như 2 cấu hình còn lại.
**mean_precision/citation_grounding dao động 69-75%/97-100% giữa các lần chạy 29-câu khác nhau (nhiễu bình thường của 1 lần chạy, không phải xu hướng xấu đi do cắt pool - không có case nào FAIL ở bất kỳ cấu hình nào).

Quyết định cuối - CHỐT Union+A cắt top-25: đây là cấu hình duy nhất phục hồi được Điều 109 ở mức đáng kể (80%, so với 0% ở cả B-only và A+B pool đơn) mà KHÔNG kéo theo chi phí latency thảm hại của union chưa cắt (rerank riêng lẻ giảm từ 8.6s đỉnh điểm xuống còn 2.5-3.35s, gần sát mức A+B pool đơn 2.1-2.5s) - không hồi quy trên toàn bộ 29 câu eval ở bất kỳ metric nào.

Lý do CHẤP NHẬN 80% thay vì cố đạt 100%: đã điều tra trực tiếp lần miss (1/5 lần) - Điều 109 VẪN có mặt trong pool đã cắt (hạng 15/25 theo điểm gốc, không bị loại khỏi pool), nhưng lần đó LLM re-rank chỉ chấm 5/10 cho nó (thấp hơn vài Điều cạnh tranh khác trong đúng lần gọi đó). Đây là NHIỄU CHẤM ĐIỂM của chính lời gọi Gemini re-rank (temperature=0.1, không phải 0 - vẫn có phương sai giữa các lần gọi), không phải bug loại-ứng-viên-khỏi-pool như ở A+B pool đơn. Tăng top-k cắt (ví dụ 30-35 thay vì 25) KHÔNG giải quyết được loại nhiễu này - vì vấn đề gốc không nằm ở việc ứng viên có mặt hay không (đã có mặt), mà ở việc LLM chấm điểm dao động run-to-run cho đúng 1 ứng viên nằm giữa bảng xếp hạng - chỉ tốn thêm chi phí (nhiều candidate hơn = rerank chậm hơn) mà không chắc cải thiện tỷ lệ. Bài học tổng quát: sau khi đã sửa đúng NGUYÊN NHÂN CẤU TRÚC (pool exclusion), phần nhiễu còn lại thuộc về bản chất xác suất của chính LLM re-ranker - chấp nhận như 1 giới hạn đã biết (tương tự các trường hợp "flaky ~10-20%" khác đã ghi nhận trong dự án), không cố khử nhiễu bằng cách vặn thêm tham số retrieval.

Việc còn lại (không làm trong đợt này): `backend/evaluation/results.json` KHÔNG được cập nhật qua đợt B/A/Union này - vẫn giữ số liệu cũ từ trước khi có B/A (không có tài khoản `EVAL_USER_EMAIL`/`EVAL_USER_PASSWORD` trong môi trường làm việc để chạy `run_evaluation.py` qua HTTP endpoint thật). Mọi số liệu eval trong case study này đến từ 1 script đo trực tiếp (gọi thẳng `stream_answer_question`/`retrieve_context` trong tiến trình, cùng real Gemini/Qdrant API, bỏ qua lớp HTTP/Supabase-auth) - cùng tinh thần "real API, không mock" nhưng khác methodology với `run_evaluation.py`, nên `results.json` cần được người có tài khoản eval chạy lại chính thức sau, không tự ý ghi đè bằng số liệu từ phương pháp đo khác.

Feature — Đổi luồng Tự luận: vào ngân hàng thấy danh sách câu hỏi ngay, cho chọn tự do thay vì random 1 câu/lượt
Quyết định: bỏ hẳn cơ chế "vào ngân hàng → nhận ngẫu nhiên 1 câu" làm mặc định. Vào ngân hàng (/essay/[category]) hiển thị NGAY danh sách/lưới toàn bộ câu hỏi trong ngân hàng đó, user tự chọn câu muốn làm.

[x] Trạng thái mỗi câu tính theo LẦN LÀM GẦN NHẤT (không gộp lịch sử nhiều lần) — 3 trạng thái màu (tái dùng token đã audit WCAG AA):
  - Đã làm đủ ý (không có missing_points ở lần gần nhất): navy đặc
  - Đã làm nhưng còn thiếu ý (có missing_points): amber tint
  - Chưa làm: viền navy nhạt/nền trắng
  Backend: `GET /api/essay/banks/{category}/questions` mới (`app/api/essay.py`, `question_bank_service.get_essay_bank_question_list`) — dựa trên `_get_latest_essay_attempt_per_question` (cùng pattern "latest row wins" với `_get_latest_attempt_per_set` của quiz), phân loại done/needs_review/not_done từ `missing_points` của lần `essay_attempts` gần nhất.
[x] UI: lưới số dạng ô vuông (`EssayQuestionGrid.tsx`), mỗi ô = 1 câu, bấm vào mở màn làm bài đúng câu đó. Chip lọc "Tất cả/Chưa làm/Cần ôn lại" phía trên, tái dùng token `bg-primary`/`amber-100+amber-300+amber-800`/`border-primary/15 bg-card` đã dùng ở nơi khác trong app (quiz grid, badge variants).
[x] Trong màn làm bài (sau khi chọn 1 câu, `EssayBankRunner.tsx`): nút "← Câu trước / Câu sau →" theo đúng thứ tự ngân hàng, nút "Xem danh sách" quay lại lưới. ĐÃ SỬA 2 lỗi lộ ra khi build so với mockup Figma gốc: (1) không hiển thị badge Điều/căn cứ pháp lý trước khi nộp bài — `dieu_number` là căn cứ của đáp án (xem `explanation` trong question_bank.json), chỉ lộ ra sau khi chấm qua `suggested_dieu`; (2) không dùng eyebrow "TÔI HỎI · BẠN TRẢ LỜI" hay nút "Câu khác" — đó là hành vi riêng của minigame /essay/practice (chọn ngẫu nhiên), không hợp lý khi user đã chủ động chọn câu từ lưới; màn làm bài ở đây chỉ có nút "Nộp câu trả lời".
[x] Không ảnh hưởng: Dashboard "Tự luận theo ngân hàng" (vẫn tính đúng X/Y câu qua `get_essay_banks_summary`, không đổi), minigame "Tôi hỏi bạn trả lời" (`/essay/practice`, hoàn toàn tách file/code riêng, giữ nguyên eyebrow/nút Câu khác/badge Điều pre-submit của nó).

Feature — Ingest 12 văn bản pháp luật mới (đợt 2026-08-29/30): 10 văn bản mới + điều tra VBHN BLTTHS + case study quy trình test hồi quy (đáng đưa vào phần Methodology/Data Quality của bài báo)

Phần A — Ingest 10/12 văn bản mới (2 văn bản còn lại xử lý riêng, xem dưới): 8 Quyết định/Thông tư/Thông tư liên tịch + 1 Nghị quyết, tổng 329 chunk mới, 100% extraction_quality=ok. Loại trừ khỏi batch: 1 file trùng lặp xác nhận (`01_2026_TTLT-VKSNDTC-BCA-BQP_694946.pdf` = đúng nội dung "Thông tư liên tịch 01_2026 VKSND - BCA - BQP.pdf" đã có trong corpus, không ingest) và 1 văn bản hợp nhất BLTTHS mới giữ lại điều tra riêng (xem phần B).

5 lớp lỗi phát hiện qua spot-check toàn bộ chunk mới (không chỉ mẫu 5-10), tất cả đã sửa bằng cơ chế lookup table hand-verified sẵn có (không dùng rule tổng quát hoá — đúng bài học đã rút ra từ Phase 3):
1. 16 case title-truncation (cùng bug class đã biết, tiêu đề bị cắt giữa từ/giữa cụm do dòng đầu tiên của Điều bị wrap).
2. Bug MỚI: 2 văn bản "Quyết định ban hành kèm theo Quy chế" (QĐ 06, QĐ 505/QĐ-VKSTC) có Điều 3 (ngoài, phần Quyết định) cuốn cả chữ ký + trang bìa của Quy chế đính kèm vào cuối chunk — cùng họ với bug "heading Chương/Mục dính vào cuối Điều" đã sửa ở Phase 3 Extension, nhưng lần này ranh giới là 1 trang bìa + khối chữ ký, không phải heading cấu trúc — sửa bằng `KNOWN_TRAILING_BOILERPLATE_MARKERS`.
3. Hệ quả của bug #2: 2 văn bản trên có Điều 1/2/3 xuất hiện HAI LẦN (Quyết định ngoài tự đánh số riêng, Quy chế đính kèm cũng bắt đầu lại từ Điều 1) — đụng độ point ID Qdrant (key cũ chỉ có dieu_number+khoan_number). Sửa TẬN GỐC bằng cách mở rộng `build_point_id`/`_key_for` thêm 1 field `dieu_occurrence` (chỉ số lần xuất hiện của đúng dieu_number trong 1 văn bản, mặc định 0) — chỉ nối vào natural key khi occurrence != 0, giữ nguyên 100% point ID của toàn bộ corpus cũ (đã verify bằng code review + sau đó bằng test hồi quy thật).
4. NGHIÊM TRỌNG: OCR fallback (Gemini Vision) trên 1 trang trắng hoàn toàn (xác nhận bằng render ảnh trực tiếp) của "Thông tư 02_2018_TT-TANDTC.pdf" đã BỊA ra nguyên 1 đoạn văn về luật lao động (không liên quan gì tố tụng hình sự) — 1 dạng lỗi khác hẳn "nhận nhầm/thiếu chữ" mà OCR fallback vốn được thiết kế để xử lý, và `is_text_garbage` không bắt được vì văn bản bịa vẫn là tiếng Việt có dấu, đúng ngữ pháp. Sửa bằng truncation marker giống #2.
5. TTLT 29/2025 (văn bản sửa đổi TTLT 10/2018): phụ lục mẫu biểu (Mẫu số 01-06C) không có heading "PHỤ LỤC" (khác quy ước mọi văn bản khác trong corpus) nên `APPENDIX_HEADING_PATTERN` không bắt được — nội dung mẫu biểu (có đánh số 1./2./3. riêng trong từng mẫu) bị đọc nhầm thành 20 khoản giả của Điều 3 "Hiệu lực thi hành". Sửa bằng truncation marker riêng cho văn bản này. Đồng thời phát hiện thêm: Điều 1 của chính văn bản này trích dẫn nguyên văn thay thế cho 1 điều của TTLT 10/2018, trong đó có 1 đoạn liệt kê "1. Quán triệt... 2. Thực hiện..." lồng bên trong khoản 6 — đụng độ số khoản y hệt bug lịch sử "Điều 150 Luật tổ chức TAND" (Phase 3 Extension) — sửa bằng cách thêm vào `KNOWN_NO_KHOAN_SPLIT_DIEU` (giữ nguyên 1 chunk không tách khoản).

Test qua Chat thật (in-process, gọi thẳng `stream_answer_question`, real Gemini+Qdrant API): 4 câu hỏi nội dung mới + 2 câu hỏi nội dung cũ (BLTTHS Điều 108, 173) — retrieval/citation đúng 100%, không hồi quy nội dung cũ.

Phần B — Điều tra văn bản hợp nhất BLTTHS mới (104/VBHN-VPQH, 27/8/2025, 250 trang) — CHƯA ingest, chờ quyết định:

B.0 — Bối cảnh phát hiện ban đầu: trong quá trình phân loại 12 file "mới" ở Phần A, 1 file ("Văn bản hợp nhất BLTTHS 2025 (104_VBHN-VPQH) - CHƯA INGEST.pdf") không khớp check trùng lặp đơn giản với "Bộ luật TTHS.pdf" đang sống trong corpus, nên được tách ra điều tra riêng thay vì ingest ngay hoặc loại bỏ ngay.

B.1 — SỬA LẠI TOÀN BỘ (2026-08-30): phương pháp điều tra ban đầu SAI, kết luận "137 Điều thay đổi nội dung" SAI. Ghi lại đầy đủ làm case study phương pháp luận cho phần Methodology của bài báo.

Phương pháp ban đầu (đã dùng, nay xác nhận sai): dựa vào 238 chú thích đánh số trong chính văn bản VBHN — mỗi chú thích ghi "Điều/khoản/điểm này được sửa đổi theo Luật X" — lọc ra 137/493 Điều có ít nhất 1 chú thích trích luật sau 02/2021 (Luật TCTAND 34/2024, Luật Tư pháp NCTN 59/2024, Luật 99/2025), rồi KẾT LUẬN "137 Điều này có nội dung khác bản BLTTHS đang sống trong corpus". Đây là bước suy luận SAI: đếm số Điều có chú thích không tương đương với đo khác biệt nội dung giữa 2 văn bản cụ thể — chú thích chỉ nói "Điều này TỪNG được luật X sửa đổi (so với bản GỐC 2015)", không nói gì về việc bản "Bộ luật TTHS.pdf" đang sống trong corpus đã phản ánh sửa đổi đó hay chưa. Giả định ngầm (chưa từng kiểm chứng trực tiếp) là "bản đang sống chỉ tới 02/2021" — dựa hoàn toàn vào giá trị `law_version` đã ghi trong `document_registry.py` khi ingest lần đầu, một giá trị TỰ KHAI BÁO, không đối chiếu lại với nội dung thật của file.

Phương pháp đúng (2026-08-30, theo yêu cầu điều tra lại): so sánh trực tiếp body text từng Điều giữa 2 nguồn — "Bộ luật TTHS.pdf" (đang sống, từ `chunks.json`) và VBHN 104/VBHN-VPQH (parse tươi qua đúng pipeline sản xuất) — hoàn toàn KHÔNG dùng bộ máy 238 chú thích (nghi ngờ đúng: bản thân phương pháp chú thích là nguồn gây kết luận sai, không phải nguồn đáng tin để đo khác biệt). Quy trình: với mỗi Điều, ghép các chunk theo đúng thứ tự khoản (bỏ dòng tiêu đề lặp lại ở mỗi chunk), chuẩn hoá Unicode NFC + khoảng trắng, gỡ 2 lớp nhiễu định dạng đã xác định rõ nguồn gốc — (a) chú thích `[N]` gắn liền cụm từ trong bản VBHN (giữ nguyên trong body vì đó là nội dung có thật của văn bản, chỉ gỡ khi so sánh), (b) câu định nghĩa chú thích bị "tràn" (bleed) vào giữa thân Điều trong bản "Bộ luật TTHS.pdf" đang sống (lỗi trích xuất văn bản nguồn, không phải nội dung Điều) — rồi diff từng từ, phân loại từng khác biệt còn lại là "nhiễu định dạng đã biết nguyên nhân" hay "khác nội dung pháp lý thật".

KẾT QUẢ CUỐI CÙNG (soát toàn bộ 493 Điều, không lấy mẫu):
- 233/493 Điều (47%) — byte-identical tuyệt đối sau chuẩn hoá.
- 260/493 Điều (53%) — có khác biệt bề mặt, NHƯNG toàn bộ (đã soát thủ công từng trường hợp, không còn trường hợp chưa phân loại) quy về đúng 4 loại nhiễu đã xác định rõ nguyên nhân, không có loại nào là nội dung pháp lý:
  1. ~140 Điều: 1 số chú thích (footnote index) dính liền vào 1 từ trong bản "Bộ luật TTHS.pdf" đang sống, không có khoảng trắng ngăn cách (ví dụ `xã35,` thay vì `xã,`, `quyền108` thay vì `quyền`, `1.86` thay vì `1.`) — sót lại sau khi gỡ nhiễu tự động, không phải nội dung.
  2. ~15 Điều: bản "Bộ luật TTHS.pdf" đang sống có sẵn lỗi title-truncation (tiêu đề Điều bị cắt ngang do wrap dòng, cùng lớp lỗi đã sửa 30+ lần cho VBHN trong phiên này — xem B (tiếp) cũ, nay đã revert phần thực thi) — phần tiêu đề bị cắt trôi dạt thành "thân Điều" giả trong dữ liệu đang sống, ví dụ Điều 273 có đoạn côi cút "án nhân dân và Tòa án quân sự" nằm lạc trong thân bài thay vì thuộc về tiêu đề.
  3. 1 số ít biến thể chính tả giữa 2 lần in ấn khác nhau của cùng văn bản: `ngặn`/`ngăn`, `doạ`/`dọa`, `toạ`/`tọa` — đều là biến thể chính tả tiếng Việt hợp lệ, không phải lỗi hay khác nội dung.
  4. Điều 509/510: bản "Bộ luật TTHS.pdf" đang sống có nguyên bản chưa sửa của ĐÚNG lỗi đã tìm và sửa cho VBHN trong phiên này (khối chữ ký + xác thực văn bản hợp nhất tràn vào cuối Điều cuối cùng, xem lại đoạn dưới) — chưa từng được sửa vì bản đang sống trước đây không parse lại được (thiếu file PDF gốc, đã khắc phục ở Phần C).
- **0/493 Điều khác nội dung pháp lý thật.** Đã kiểm tra trực tiếp lại toàn bộ ví dụ "flagship" từng dẫn ra ở bản báo cáo trước (Điều 111 "Công an cấp xã", Điều 454 "có kết luận khỏi bệnh...", Điều 193 "Viện kiểm sát có thẩm quyền") — cả 3 đều đã có sẵn trong bản "Bộ luật TTHS.pdf" đang sống, không phải nội dung VBHN mới thêm vào.

Bài học phương pháp luận (đáng đưa vào phần Methodology/rủi ro của bài báo): đếm sự hiện diện của 1 chỉ báo gián tiếp (ở đây: chú thích trích dẫn luật sửa đổi) và suy ra trực tiếp "có khác biệt nội dung" là 1 dạng proxy indirect measurement — chỉ báo có thể đúng về MỘT SỰ KIỆN LỊCH SỬ (Điều này từng được luật X sửa) nhưng sai về TRẠNG THÁI HIỆN TẠI của 1 nguồn dữ liệu cụ thể (nguồn đó đã phản ánh sửa đổi đó hay chưa) nếu không đối chiếu trực tiếp lại nguồn. Rủi ro lớn hơn khi 2 nguồn được so sánh (ở đây: bản "cũ" và VBHN "mới") vô tình lại rất giống nhau về nội dung — chỉ báo gián tiếp khi đó không phân biệt nổi "2 bản khác nội dung" và "2 bản giống nội dung nhưng khác chất lượng trích xuất". Bài học áp dụng: khi phát biểu kết luận dạng "văn bản A khác văn bản B", luôn cần ít nhất 1 lần đối chiếu trực tiếp nội dung 2 nguồn cụ thể, không suy luận thuần tuý từ metadata/chỉ báo gián tiếp của 1 trong 2 nguồn, dù chỉ báo đó (ở đây: 238 chú thích) tự thân là dữ liệu chính xác.

B.2 — Tác động lên ground truth: KHÔNG có case nào trong `question_bank.json`/`test_set.json` cần sửa. Đảo ngược hoàn toàn kết luận trước đây về `lythuyet-q17` (Điều 37) — báo cáo trước cho rằng VBHN bổ sung mới nội dung "Điều tra viên là Trưởng/Phó Công an cấp xã" (khoản 1a) mà ground truth hiện tại thiếu, đề xuất bổ sung. Kết luận đó dựa trên tiền đề sai ở B.1 (137 Điều thay đổi). Đối chiếu trực tiếp: bản "Bộ luật TTHS.pdf" đang sống ĐÃ CÓ SẴN nguyên văn khoản 1a này (đã xác nhận đọc trực tiếp — chỉ lẫn nhiễu chú thích tràn vào giữa câu, không mất nội dung). Không có Điều nào trong 10 case đã rà soát (8 câu `question_bank.json` + 2 case `direct_citation` `test_set.json`) bị ảnh hưởng bởi VBHN theo bất kỳ hướng nào — 10/10 giữ nguyên, không sửa gì.

Phần B2 — Cân nhắc thay bản BLTTHS nguồn vì lý do chất lượng dữ liệu (KHÔNG PHẢI cập nhật sửa đổi luật) — quyết định độc lập, chưa thực hiện, không khẩn cấp:

Tách hẳn khỏi câu hỏi "nội dung có khác không" (đã trả lời dứt điểm ở B.1: không khác). Đây là câu hỏi hoàn toàn khác: bản "Bộ luật TTHS.pdf" đang sống trong corpus có 1 số lượng đáng kể lỗi trích xuất/parse CHƯA TỪNG ĐƯỢC SỬA — không phải vì không sửa được, mà vì trước phiên làm việc này, `raw_documents/` không có file PDF gốc để parse lại (khắc phục ở Phần C), nên các lỗi này tồn tại âm thầm trong dữ liệu đang phục vụ người dùng thật từ trước tới nay:

- ~61 chunk (thuộc 61 Điều distinct) có câu định nghĩa chú thích tràn (bleed) vào giữa thân Điều — ví dụ Điều 11 có nguyên 1 câu về Điều 7 (luật khác, không liên quan) chen vào giữa 2 câu của Điều 11.
- ~16 Điều có tiêu đề bị cắt ngang giữa từ/cụm từ do lỗi wrap dòng title (cùng lớp lỗi `KNOWN_NON_KHOAN_TITLE_CONTINUATIONS` đã sửa hệ thống cho VBHN trong phiên này — xem `ingestion/chunking.py`, chưa commit, chưa áp dụng cho bản đang sống).
- Điều 509/510 (2 Điều cuối cùng): khối chữ ký + dòng "XÁC THỰC VĂN BẢN HỢP NHẤT" + tên người ký tràn vào cuối thân Điều — cùng lớp lỗi "Điều cuối không có Điều kế tiếp để chặn ranh giới" đã tìm và sửa cho VBHN (xem `KNOWN_TRAILING_BOILERPLATE_MARKERS` trong `ingestion/chunking.py`).

Tổng cộng ~77+ chunk/Điều đang sống có 1 trong các lỗi trên — không ảnh hưởng tới NỘI DUNG PHÁP LÝ (đã xác nhận ở B.1: nội dung vẫn đúng, chỉ là hiển thị/trích dẫn không sạch, ví dụ 1 câu trích dẫn có thể vô tình lẫn 1 câu chú thích không liên quan). Bản VBHN 104/VBHN-VPQH, sau khi áp dụng đầy đủ các fix đã viết trong phiên này (title-continuation, footnote-suffix-strip, trailing-boilerplate cho Điều 510), parse sạch 0 lỗi thuộc cả 3 lớp trên trên toàn bộ 493 Điều — đã xác nhận bằng scan tự động sau mỗi lần sửa.

Nếu MUỐN nâng chất lượng dữ liệu (không phải bắt buộc, không có deadline pháp lý nào thúc ép vì nội dung đã đúng), phương án khả thi là thay file nguồn "Bộ luật TTHS.pdf" bằng bản VBHN 104/VBHN-VPQH đã parse sạch — nhưng đây là quyết định RIÊNG, để dành cân nhắc sau, KHÔNG vội, vì:
1. Không có rủi ro nội dung nào đang tồn tại (đã xác nhận 0/493 Điều khác nội dung) — khác hẳn tình huống "cập nhật luật mới" (có deadline/rủi ro trả lời sai luật).
2. Cơ chế kỹ thuật cho quyết định "thay nội dung khác nhau" (archive `is_superseded`, filter must_not trong `rag_service.py`, repoint `LAW_NAME_TO_SOURCE_DOCUMENT`) đã được viết trong phiên này rồi lại REVERT hoàn toàn (xem `git diff`/git log — không còn trong working tree) vì cơ chế đó được thiết kế đúng cho tình huống "2 văn bản khác nội dung, 1 bản cũ 1 bản mới, cần route người dùng sang bản đúng" — KHÔNG áp dụng cho tình huống hiện tại ("2 văn bản cùng nội dung, chỉ khác chất lượng OCR/parse"), dùng nhầm cơ chế sẽ tạo ra 1 document giả mang tên khác nhưng nội dung y hệt, gây rối thêm không cần thiết.
3. Nếu sau này quyết định thay, cách làm đúng là ĐƠN GIẢN HƠN nhiều so với kế hoạch B.4 cũ đã revert: không cần archive/is_superseded gì cả — có thể coi đây như 1 lần "resync nguồn" giống hệt case Nghị định 250/TTLT 01_2026 ở Phần C (giữ nguyên `source_document`/`law_version`, chỉ thay file PDF nguồn vật lý, point ID Qdrant khớp lại tự nhiên do cùng natural key, overwrite tại chỗ) — vì 2 file thực chất là 2 bản in của CÙNG 1 nội dung, không phải 2 văn bản khác nhau.
4. Công việc parse-fix cho VBHN (tất cả entry mới trong `KNOWN_NON_KHOAN_TITLE_CONTINUATIONS`, `KNOWN_FOOTNOTE_FUSED_DIEU_TITLE_SUFFIXES`, `KNOWN_TRAILING_BOILERPLATE_MARKERS` của `ingestion/chunking.py`, cùng entry đăng ký trong `document_registry.py`/`document_display_names.py`) vẫn giữ nguyên trong working tree (uncommitted, không ảnh hưởng hành vi sống vì VBHN chưa được ingest/dùng ở đâu) — sẵn sàng dùng lại nguyên vẹn nếu/khi quyết định resync sau này, không mất công làm lại.

Phần C — Case study: chuỗi phát hiện qua file backup PDF thiếu/lỗi khi chạy test hồi quy cho Phần A

Bối cảnh: sau khi hoàn thành Phần A, raw_documents/ của 6 văn bản legal_text CŨ (đã ingest từ trước, không liên quan Phần A) không còn PDF gốc trên máy (đã dọn sau ingest, đúng thiết kế .gitignore) — không chạy được `regression_check_legal_text.py` để xác nhận thay đổi code ở Phần A (đặc biệt: điểm ID theo `dieu_occurrence`, truncation marker mới) không phá vỡ dữ liệu cũ. Yêu cầu backup + khôi phục 6 file dẫn tới 1 chuỗi phát hiện ngoài dự tính ban đầu:

1. Lần khôi phục đầu: 5/6 file bị lệch Unicode normalization (NFD trên đĩa do phục hồi từ nguồn khác hệ điều hành, thường gặp khi copy từ macOS — vs NFC trong `document_registry.py`) khiến parser báo "file not found" dù `ls` hiện tên giống hệt. Sửa bằng rename thuần filesystem (dùng `os.rename` với tên lấy trực tiếp từ `os.listdir`, không gõ lại tên có dấu — gõ lại sẽ tự động là NFC, không khớp file NFD trên đĩa).

2. Sau khi sửa tên file, chạy test hồi quy: 4/6 văn bản khớp tuyệt đối golden ngay — xác nhận toàn bộ thay đổi code ở Phần A đúng là NO-OP cho dữ liệu cũ như code review đã dự đoán trước. 2/6 văn bản (Nghị định 250, TTLT 01/2026) lệch nặng, chunk count dao động giữa các lần chạy (56/66/77 cho cùng 1 file Nghị định 250). Điều tra bằng `pdfplumber`: `len(page.chars) == 0` trên TOÀN BỘ trang của cả 2 file — bản backup phục hồi là ảnh scan thuần, không có text layer, trong khi golden (`extraction_method=text_layer` 100%) chứng minh bản gốc dùng để ingest lần đầu có text layer thật. Bản scan buộc toàn bộ trang qua Gemini Vision OCR — sinh ra kết quả không ổn định (2 lần chạy liên tiếp cho 2 chunk count khác nhau) và ở mức nặng nhất, GÂY MẤT DỮ LIỆU THẬT (không chỉ khác định dạng): OCR không nhận ra 1 số heading "Điều N." bị mất do ảnh mờ/OCR sai, khiến nội dung Điều đó bị cuốn nhầm vào Điều liền trước — xác nhận cụ thể bằng cách visual-render từng trang, so khớp thủ công.

3. Yêu cầu file thay thế "chính thống" lần 1: file mới đặt vào `raw_documents/` với hậu tố " (1).pdf" (tự động do trùng tên) — kiểm tra `pdfplumber` TRƯỚC khi parse (đúng quy trình đã rút kinh nghiệm từ bước 2, không parse mù) phát hiện file " (1)" VẪN là bản scan cũ (cùng kích thước byte 1.648.665 với bản cũ đã ghi nhận) — báo cáo dừng lại, không parse, yêu cầu kiểm tra lại nguồn.

4. Lần thay thế thứ 2 mới đúng: file mới có `len(page.chars) > 0` trên 100% trang, kích thước byte khác hẳn bản scan cũ (497.582 so với 1.648.665 byte cho Nghị định 250) — xác nhận là file khác thật, không phải đổi tên. Xóa bản " (1)" scan cũ, chuẩn hoá lại tên NFC.

5. Parse lại: chunk count khớp tuyệt đối golden (61, 86), extraction_method=text_layer 100%, nhưng vẫn còn lệch ở mức string-exact — điều tra bằng whitespace-normalize xác nhận TOÀN BỘ lệch chỉ là khác vị trí xuống dòng (do khác trang/font-render giữa 2 nguồn PDF cùng nội dung chính thức), 0 khác biệt nội dung pháp lý thật (đặc biệt kiểm kỹ số liệu/ngày tháng/mức tiền/ngưỡng định lượng — không lệch).

6. TTLT 01/2026 Điều 30: assert lỗi do `KNOWN_NON_KHOAN_TITLE_CONTINUATIONS` cũ hard-code đúng vị trí wrap của FILE CŨ (chữ "trưởng" bị cắt ngang) — file mới wrap sạch hơn 1 từ (không cắt ngang chữ). Xác nhận là case thật (không phải nhiễu OCR — file mới không qua OCR), cập nhật lại value của entry theo đúng file mới, kèm comment giải thích nguyên nhân đổi giá trị (không phải nội dung đổi, chỉ đổi nguồn file).

7. Sau khi sửa Điều 30, lộ thêm 1 mismatch còn lại: TTLT 01/2026 Điều 30... à Điều 37 — tiêu đề bị cắt cụt TRONG CHÍNH GOLDEN (dữ liệu đang sống, đã phục vụ người dùng thật từ trước) — không phải bug mới, không phải do đổi file, mà là 1 khoảng trống tồn tại từ lần ingest gốc chưa từng bị phát hiện (Điều 37 có tiêu đề wrap 4 dòng vật lý, dài hơn mọi case đã có trong bảng tra cứu). Xác nhận tiêu đề đúng đầy đủ bằng cách đối chiếu trực tiếp phần thân Điều (khoản 1-4 giống hệt cả 2 bản, chỉ có tiêu đề sai), thêm entry mới vào bảng tra cứu kèm comment phân biệt rõ "bug tồn tại từ trước, phát hiện qua re-parse, không phải hồi quy". Re-embed + upsert đúng 1 chunk này vào Qdrant (điểm ID không đổi vì dieu_number không đổi — xác nhận trước khi upsert).

8. Cập nhật golden snapshot (`chunks.json` + Qdrant) cho đúng 2 văn bản Nghị định 250 + TTLT 01/2026 bằng bản parse mới nhất từ file chính thống (script `ingestion/resync_source_file_swap.py`, cùng khuôn mẫu `ingest_batch2/3.py`) — 147/147 chunk re-embed thành công, tổng point Qdrant không đổi (2958, xác nhận key không đổi, chỉ overwrite tại chỗ, không tạo điểm mới/mồ côi).

9. Chạy lại test hồi quy: PHÁT HIỆN THÊM 1 bug do CHÍNH sửa đổi ở bước 3 (Phần A) gây ra — mở rộng `_key_for` trong `regression_check_legal_text.py` thêm `dieu_occurrence` (4-tuple) nhưng quên cập nhật `KNOWN_MANUAL_TESSERACT_PATCHES` (vẫn khai 3-tuple) khiến case ngoại lệ Tesseract-patch đã biết từ trước (Luật tổ chức TAND Điều 152 Khoản 5) không còn được nhận diện đúng — script báo "regression" giả cho 1 case đã biết và chấp nhận từ lâu. Sửa bằng cách so khớp `k[:3]` thay vì `k` khi kiểm tra `KNOWN_MANUAL_TESSERACT_PATCHES` (bảng cũ không cần biết về khái niệm occurrence mới). Chạy lại lần cuối: **1862/1862 chunk khớp tuyệt đối, 0 mismatch/missing/extra, `BASELINE PASS`, exit code 0 — 16/16 văn bản legal_text sạch hoàn toàn, không còn ngoại lệ nào cần giải thích thêm.**

Bài học tổng quát: (a) 1 thay đổi tưởng vô hại vào 1 script hỗ trợ (thêm field vào key so sánh) có thể âm thầm vô hiệu hoá 1 cơ chế loại trừ đã có từ trước nếu không rà lại MỌI nơi dùng đúng shape của key đó — luôn grep toàn bộ chỗ dùng 1 cấu trúc dữ liệu trước khi đổi shape của nó; (b) "bản backup" không đồng nghĩa "bản tương đương" — file cùng tên, cùng nội dung nhìn bằng mắt vẫn có thể khác hẳn nhau ở tầng cấu trúc (text layer vs ảnh scan) theo cách chỉ lộ ra khi đo bằng công cụ (`len(page.chars)`), không thể nhận ra qua tên file hay xem nhanh; (c) khi so sánh 2 nguồn văn bản pháp luật CÙNG hiệu lực nhưng khác file, luôn tách bạch "khác biệt trình bày" (line-wrap, khoảng trắng — vô hại) khỏi "khác biệt nội dung" (từ ngữ, số liệu — nghiêm trọng) bằng so sánh có normalize, không kết luận vội từ số lượng mismatch thô; (d) 1 lần re-parse với dữ liệu tốt hơn có thể lộ ra bug tồn tại rất lâu trong chính golden (Điều 37) — golden không phải "chân lý tuyệt đối bất biến", chỉ là snapshot tốt nhất tại 1 thời điểm, vẫn cần đối chiếu lại khi có cơ hội (nguồn dữ liệu mới, sạch hơn).

Backup 6 file PDF nguồn (Bộ luật TTHS, Văn bản hợp nhất BLHS 2015, Nghị định 250, Thông tư liên tịch 05, Thông tư liên tịch 01_2026, Luật tổ chức toà án nhân dân) ra vị trí an toàn ngoài git, ngoài máy đang dùng — tránh lặp lại tình huống "thiếu file test hồi quy" ở đợt ingest sau. Xem chi tiết vị trí backup trong log thao tác của phiên làm việc này (không ghi đường dẫn máy cục bộ vào tài liệu dùng chung).
[x] Test qua tài khoản Supabase test thật (tạo qua Admin API, xoá sau khi test xong — không có sẵn tài khoản test trong `.env`): nhảy tự do 15 → 3 → 40 (grid + nút Câu trước/sau) hoạt động đúng; nộp câu 15 (LLM chấm thật) → ô 15 chuyển amber "Cần ôn lại" ngay lập tức không cần reload, đếm chip cập nhật theo (49/1); chip lọc "Chưa làm"/"Cần ôn lại" lọc đúng; không có badge Điều/căn cứ pháp lý nào xuất hiện trước khi nộp; Dashboard "Bán trắc nghiệm: 1/50 câu" cập nhật đúng; minigame /essay/practice không đổi (vẫn còn eyebrow/nút Câu khác/badge Điều pre-submit). Responsive mobile (375px): lưới thu về 5 cột, touch target ô lưới đo được 44px chiều cao.