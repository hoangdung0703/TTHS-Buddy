# Kiểm thử trình duyệt: Phiên tòa giả định

Bộ kiểm thử chạy giao diện thật (bản build production) trong Chromium headless, với **backend và Supabase giả lập**: không cần tài khoản, không cần backend, không gọi Gemini. Dữ liệu trong `fixtures.mjs` là giả định, chỉ để kiểm bố cục.

## Chạy

```sh
cd frontend
tests/e2e/build.sh          # build một bản sao ở thư mục tạm, phục vụ ở http://localhost:3011
node tests/e2e/suite.mjs    # in PASS/FAIL từng ca, mã thoát khác 0 nếu có ca hỏng
```

- `build.sh` **không** đụng `frontend/.next` (có thể đang chạy `next dev`) và **không** chép file `.env*`. Bản build trỏ tới hai origin giả `http://api.e2e.test` và `http://supabase.e2e.test`; mọi request tới đó do `lib.mjs` trả lời.
- Biến tùy chọn: `E2E_PORT` (mặc định 3011), `E2E_WORK_DIR` (thư mục build, mặc định `$TMPDIR/ttths-e2e`), `E2E_SHOTS=<thư mục>` để lưu ảnh màn hình, `E2E_DEBUG=1` để in thông báo console gây lỗi.
- Dừng server: `kill $(cat ${E2E_WORK_DIR:-$TMPDIR/ttths-e2e}/server.pid)`.

## Playwright

Playwright **không** nằm trong `package.json`. `lib.mjs` tìm theo thứ tự: biến `PLAYWRIGHT_MODULE` (đường dẫn tới thư mục gói `playwright`), gói `playwright` resolve được, rồi bản trong cache của npx (`~/.npm/_npx/*/node_modules/playwright`). Máy chưa có thì chạy một lần:

```sh
npx -y playwright@1.64.0 install chromium
```

## Bao phủ

- Cờ tính năng: dò bằng `HEAD /api/trials` (một lần mỗi người dùng, không dò lại khi chuyển trang), cờ tắt thì ẩn menu và chuyển mọi trang `/trial*` về trang chính, backend chưa có HEAD (405) thì dùng `GET`; không lưu gì về phiên tòa vào storage.
- Danh sách email (`TRIAL_ALLOWED_EMAILS` giả lập): không gửi HEAD khi chưa đăng nhập; đăng nhập sau khi đã vào `/trial` lúc chưa đăng nhập; đổi tài khoản A ↔ B qua form đăng nhập/đăng xuất mà không tải lại trang; lỗi mạng khi dò thì trang sau dò lại; đang chờ kết quả dò thì ẩn menu nhưng không chuyển hướng.
- `remaining.usage_available = false`: trang danh sách và trang tạo vụ hiện đúng câu của hợp đồng, khóa nút tạo, không báo "đã tạo đủ"; backend cũ thiếu trường thì như trước.
- `/trial/new`: thẻ vai bật/tắt theo `config.user_roles`, "Sắp có", thẻ Người xem không có pill Điều, body tạo vụ đúng 5 trường; 429 `trial_global_daily_limit`, 429 `trial_daily_case_limit`, 503 `trial_usage_log_unavailable` (thông điệp riêng, khung trung tính) và lỗi 503 khác.
- Phiên tòa (KSV): ngưỡng ký tự (bảng dự phòng và `text_limits`), 409 đồng bộ lại, bước 5 chọn người được hỏi, tên viết tắt trong panel và tên đầy đủ trong diễn biến, văn bản có cấu trúc, ký tự HTML, cáo trạng trong panel, panel mở rộng, cuộn và nút "Có lời mới", cầu chì tạm nghỉ, không tự gửi `continue`, lỗi giữa stream, thanh kết thúc, không có chỗ hiện nghị án, chờ "Đang lập biên bản" tối đa ~15 giây.
- Phiên tòa (Người xem): không có ô nhập; chú giải thủ tục mở sẵn ở mỗi bước mới, gấp được, nhãn "Bản nháp, đang chờ nhóm luật duyệt" khi `reviewed = false`; tiến trình và nút khóa khi AI đang trình bày; body `advance`/`continue` đúng hợp đồng; 409; cầu chì; khung dưới không che lời mới nhất; 320/390px.
- Phiên tòa (Thư ký): thẻ vai bật theo `config.user_roles`, pill Điều 47 và 258; bước 1 điền sẵn lời mẫu, danh sách triệu tập, ngưỡng 100–3.000, body `speak` đúng hợp đồng; từ bước 2 chỉ có nút chuyển phần; ghi chép tải bằng `GET /notes`, câu nhắc "Gợi ý ghi chép" (không có nhãn chờ duyệt), tự lưu sau 2 giây ngừng gõ (một `PUT` cho một lần sửa, kể cả khi ngăn kéo điện thoại đang mở), mở lại vẫn thấy, lỗi lưu có "Thử lại", phiên xong vẫn lưu, phiên đã bỏ chỉ đọc, không gửi ghi chép kèm `/turn`; KSV/Người xem không gọi route của Thư ký.
- Biên bản (Thư ký): chế độ Soạn/Xem bản nháp, "Chép từ ghi chép", "Lưu ý" sau khi lưu (kèm gợi ý theo mã), thay bằng bản đã làm sạch, đếm ký tự (gợi ý 200–4.000, trần 6.000), nút Chốt khóa khi một mục trống, chốt thì lưu nháp trước rồi mới `finalize`, hủy hộp xác nhận thì không gửi gì; 409 `trial_record_section_empty`, `trial_record_finalized` (chuyển sang xem), `trial_not_clerk`, 422, mất mạng; chế độ xem sau khi chốt (nhãn "Người học soạn", `author_note`), mở lại vẫn ở chế độ xem; 390×844, 1280×600, 1440×900, 1920×1080.
- Phiên tòa (Bị cáo): thẻ vai bật theo `config.user_roles`, pill Điều 61; trích câu hỏi đang chờ từ `pending_question` (người hỏi + câu hỏi), lý lịch điền sẵn từ `prefill`, ngưỡng 1–1.500 (bước 2, 4, 5) và 1–3.000 (bước 7–9); "Từ chối trả lời" chỉ khi có `decline` (hỏi xác nhận, chú giải `decline_note` với căn cứ như server trả, không có nhãn chờ duyệt), body `decline` đúng hợp đồng, câu thủ tục `is_user` hiện bên phía người dùng, kiểu trung tính; bước 7–8 trích câu mời của Chủ tọa, "Không bổ sung" / "Không có ý kiến" (`end_slot`); bước 9 lời sau cùng không có nút từ chối hay bỏ lượt; tab "Vai của bạn" (nguyên văn `note`) chỉ ở phiên Bị cáo, các vai khác không có; 409 `trial_action_not_allowed`, sai version, 401, 422, 429, 503, mất mạng; biên bản như KSV; 390×844, 1280×600, 1440×900, 1920×1080.
- Phiên tòa (Chủ tọa, chặng F1, bước 1–9; backend giả ở `chair.mjs` theo hợp đồng 5.4): thẻ vai bật theo `config.user_roles`, pill Điều 45; bước 1 chỉ có nút chuyển bước; khung "Điều hành" từ `state.presiding` (bắt buộc/tùy chọn, đã làm, chưa làm được, "Lời mẫu gợi ý" không có nhãn chờ duyệt, căn cứ Điều); "Dùng lời mẫu" một cú bấm (body chỉ có khóa mục), "Tự soạn" điền lời mẫu để sửa; câu hỏi (người được hỏi, trần 1.500, bộ đếm câu hỏi), phát biểu khác (có/không người nhận, bộ đếm); nút chuyển bước khi còn thiếu mục: không gửi gì, liệt kê và nháy các mục thiếu; 409 `trial_procedure_incomplete` (`missing_items`); Điều 323 đúng một lần (hỏi xác nhận, bước 5 thu gọn, "Về lại bước 8", đã dùng); ghi chú giới hạn 2 vòng đối đáp; sau lời sau cùng không gửi phát biểu cho bị cáo; bước 10 hiện "Sắp có"; notice "Hệ thống"; mọi mã 409 của vai, 401/404/422/429/503/mất mạng; sai version giữ câu đang gõ; đếm thao tác tối thiểu bước 2–9 (25); 390×844 (ngăn kéo), 1280×600, 1440×900, 1920×1080; vai khác không có khung điều hành.
- Panel hồ sơ đủ 5 tab ở 320/390/1440px (6 tab với Bị cáo).
- Biên bản (KSV và Người xem): dòng mô phỏng đầu/cuối, dòng ghi chú Người xem ngay sau dòng mô phỏng đầu, dòng chấm trống, nhãn Tóm tắt/Nguyên văn, phụ lục, sao chép đúng `text`, chế độ in.
- Console không chứa lời thoại và không có lỗi trang.
