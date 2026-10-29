# Phiên tòa giả định — API contract cho frontend

Tài liệu cho agent làm frontend ở session mới. Đọc file này là đủ; nội dung được viết lại từ code thật trên nhánh `muc5-mock-trial`:
- `backend/app/api/trials.py`
- `backend/app/models/trial_api.py`
- `backend/app/services/trial_session_service.py`
- `backend/app/services/trial_state_machine.py`
- `backend/app/services/trial_record.py`
- `backend/app/services/trial_anonymise.py` (ẩn danh panel)
- `backend/app/services/trial_text_format.py` (quy ước văn bản)
- `backend/app/services/trial_record_summary.py` (tóm tắt IV.2, IV.3 của biên bản)
- `backend/app/services/trial_procedure_notes.py` (chú giải thủ tục của vai Người xem)
- `backend/app/services/trial_clerk.py` (vai Thư ký: ghi chép, mục IV.2/IV.3 do người dùng viết, lưu ý, câu nhắc ghi chép)

Code thay đổi thì sửa file này cùng commit. Thiết kế tổng thể: `THIET-KE.md` (cùng thư mục). File này là chuẩn khi hai file mâu thuẫn.

---

## 0. Tóm tắt nhanh

- Người dùng chọn **một** vai trong `config.user_roles`. Hiện có: `ksv` (Kiểm sát viên), `luat_su` (luật sư bào chữa), `nguoi_xem` (Người xem, từ chặng R1) và `thu_ky` (Thư ký phiên tòa, từ chặng R2). AI đóng mọi vai còn lại; với `nguoi_xem` AI đóng **mọi** vai, người dùng chỉ bấm chuyển phần (Mục 5.1); `thu_ky` nói một lần ở bước 1, ghi chép trong phiên và viết mục IV.2, IV.3 của biên bản qua các route riêng (Mục 5.2, 3.8–3.10).
- Phiên tòa có **11 bước, cố định thứ tự**. Server giữ trạng thái và chỉ chấp nhận những hành động có trong `state.allowed_actions`.
- Mọi lượt **nói** tại phiên tòa đi qua **một** route: `POST /api/trials/{id}/turn`. (Ghi chép và biên bản của Thư ký không phải lời nói, có route riêng.) Route trả **SSE**; client đọc bằng `fetch` + `ReadableStream`, không dùng `EventSource` (cần method POST và header Authorization).
- Mỗi request ghi phải gửi `expected_step` và `expected_version` lấy từ state mới nhất. Lệch thì nhận 409 kèm state hiện tại.
- Biên bản (`GET /record`) chỉ có khi phiên đã `completed`. Không có chấm điểm.
- Tính năng nằm sau cờ `TRIAL_ENABLED` ở backend. Cờ tắt thì **mọi** route `/api/trials*` trả 404 y hệt một đường dẫn không tồn tại.

---

## 1. Môi trường

| Biến | Ở đâu | Ý nghĩa |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/.env.local` (đã có) | Gốc URL backend. Code hiện mặc định `http://localhost:8000` (`lib/api.ts`) |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `frontend/.env.local` (đã có) | Đăng nhập Supabase, lấy access token |
| `TRIAL_ENABLED` | backend (`.env`, Render) | `true` mới bật tính năng. Mặc định tắt |
| `TRIAL_ALLOWED_EMAILS` | backend | Danh sách email được dùng tính năng khi mở dần (phân tách bằng dấu phẩy, không phân biệt hoa thường, bỏ khoảng trắng). **Khác rỗng**: chỉ người dùng đã đăng nhập có email trong danh sách mới dùng được `/api/trials*`; mọi người khác (kể cả chưa đăng nhập, token sai) nhận **đúng** 404 như khi cờ tắt. **Rỗng**: mọi người dùng đã đăng nhập. Email lấy từ JWT đã xác thực |
| `TRIAL_COURT_NAME` | backend | Tên Tòa án dùng trong vụ án, lời thoại và biên bản. Mặc định `Tòa án nhân dân khu vực 1, tỉnh X`. Tên Viện kiểm sát suy ra từ đó (`Viện kiểm sát nhân dân khu vực 1, tỉnh X`). Frontend lấy tên từ `court.name` / `record.court_name`, không hardcode |
| `TRIAL_GLOBAL_DAILY_CASE_LIMIT` | backend | Số vụ tối đa toàn hệ thống mỗi ngày (giờ Việt Nam, mọi người dùng cộng lại). Mặc định 100. Frontend không cần biết, chỉ cần xử lý mã lỗi `trial_global_daily_limit` |
| `TRIAL_CASE_MODEL` | backend | Tùy chọn: model riêng chỉ cho bước tạo vụ án. Chưa đặt thì dùng `GEMINI_CHAT_MODEL`. Frontend không cần biết |

**Frontend không có biến cờ riêng.** Để biết tính năng có bật **cho người dùng hiện tại** không, dò bằng `HEAD /api/trials` (Mục 3.0, là cách chuẩn): `204` thì hiện mục "Phiên tòa giả định"; `404` thì ẩn mục đó khỏi sidebar và chặn truy cập các trang `/trial*`. Kết quả dò phụ thuộc người dùng (danh sách email), nên phải dò lại khi đăng nhập, đăng xuất hoặc đổi tài khoản; không dò khi chưa có token rồi giữ kết quả.

Mọi route cần header `Authorization: Bearer <supabase access token>`. Khi cờ tắt, hoặc khi `TRIAL_ALLOWED_EMAILS` khác rỗng mà người gọi không có trong danh sách, thì 404 đến trước, kể cả khi không có token.

**Quy trình bật cờ theo từng bước (backend, làm tay):**
1. Chạy migration 0012, 0013, 0014 trong Supabase SQL Editor của đúng project mà Render dùng (0014 bắt buộc: thiếu thì không tạo được vụ, 503 `trial_usage_log_unavailable`).
2. Đặt `TRIAL_ALLOWED_EMAILS` trên Render gồm vài email thử nghiệm.
3. Đặt `TRIAL_ENABLED=true` và deploy. Chỉ những email trong danh sách thấy tính năng; người khác thấy như cờ tắt.
4. Mở rộng: thêm email vào danh sách; khi sẵn sàng cho mọi người thì xóa giá trị `TRIAL_ALLOWED_EMAILS` (để rỗng).
Tắt khẩn cấp: `TRIAL_ENABLED=false`.

---

## 2. Định dạng lỗi chung

Lỗi của app có dạng:

```json
{ "error": { "code": "<mã>", "message": "<mô tả>" } }
```

Lỗi 409 của phiên tòa có thêm trường `state` (xem Mục 6).

| HTTP | `error.code` | Khi nào |
|---|---|---|
| 400 | `http_error` (message `Unknown crime_key`) | `crime_key` không có trong danh sách cho phép |
| 401 | `http_error` | Thiếu, sai hoặc hết hạn token |
| 404 | `http_error` (message `Trial not found`) | Phiên không tồn tại **hoặc thuộc người khác**. Hai trường hợp không phân biệt được, có chủ đích |
| 404 | *(body `{"detail": "Not Found"}`)* | Cờ `TRIAL_ENABLED` tắt, hoặc người gọi không có trong `TRIAL_ALLOWED_EMAILS` khi danh sách khác rỗng (y hệt đường dẫn lạ) |
| 409 | `trial_<mã>` | Hành động không hợp lệ ở trạng thái hiện tại, xem Mục 6 |
| 422 | `validation_error` | Body sai schema: thiếu trường, sai kiểu, **có trường thừa**, `user_role` không có trong `config.user_roles` (ví dụ `bi_cao`, `chu_toa` khi chặng của vai đó chưa bật), `witness_count` ngoài 0–2, `text` dài hơn 6000 ký tự (ghi chép: 20000; mỗi mục biên bản: 6000), `session_id` không phải UUID |
| 429 | `rate_limit_exceeded` | Quá giới hạn tần suất: 10 request/phút/user với `POST /api/trials` và `POST /turn`; 60/phút với các route khác |
| 429 | `trial_daily_case_limit` | Đã tạo đủ 5 vụ trong ngày (ngày tính theo giờ Việt Nam). Đếm mọi lần tạo vụ **thành công** trong ngày; **xóa phiên không trả lại lượt** |
| 429 | `trial_active_session_limit` | Đã có 3 phiên đang dở dang |
| 429 | `trial_global_daily_limit` | Toàn hệ thống đã tạo đủ số vụ cho phép trong ngày (giờ Việt Nam). `message` là câu thân thiện, hiển thị nguyên văn. **Chỉ chặn tạo vụ mới**; phiên đang dở vẫn chơi tiếp bình thường. Kiểm sau hai hạn mức của người dùng |
| 500 | `internal_server_error` / `data_read_failed` | Lỗi server, hoặc lỗi đọc dữ liệu không tự hết |
| 503 | `data_unavailable` | Supabase tạm lỗi; thử lại được |
| 503 | `trial_usage_log_unavailable` | Chỉ ở `POST /api/trials`: server không đọc được sổ hạn mức nên **từ chối tạo vụ** (không bỏ qua hạn mức). `message` là câu thân thiện, hiển thị nguyên văn kèm nút thử lại sau. Phiên đang dở không bị ảnh hưởng |

Lỗi xảy ra **sau khi** SSE đã bắt đầu thì không có mã HTTP: server gửi sự kiện `error` rồi đóng stream (Mục 4).

---

## 3. Các route

### 3.0 `HEAD /api/trials` — dò cờ tính năng

Trả `204` (không có body) khi tính năng bật cho người gọi và token hợp lệ; `404` khi `TRIAL_ENABLED` tắt, hoặc khi `TRIAL_ALLOWED_EMAILS` khác rỗng mà người gọi không có trong danh sách hay không có token hợp lệ (giống route không tồn tại); `401` chỉ khi tính năng bật cho mọi người (danh sách rỗng) mà thiếu hoặc sai token. Route này **không** chạy bước dọn phiên quá hạn và **không** đếm hạn mức, nên rẻ hơn `GET`. Dùng để quyết định có hiện mục "Phiên tòa giả định" trong sidebar.

### 3.1 `GET /api/trials` — danh sách phiên + cấu hình

Gọi route này cũng tự chuyển sang `abandoned` mọi phiên `active` không cập nhật quá 14 ngày (lazy, không có cron).

```json
{
  "sessions": [
    {
      "session_id": "3f6c…-uuid",
      "title": "<tên vụ án giả định>",
      "crime_key": "blhs_173",
      "user_role": "ksv",
      "current_step": 5,
      "status": "active",
      "updated_at": "2026-10-19T08:12:03.123456+00:00"
    }
  ],
  "config": {
    "crimes": [
      { "crime_key": "blhs_173", "crime_name": "Tội trộm cắp tài sản", "dieu": "173", "allowed_khoan": ["1", "2"] },
      { "crime_key": "blhs_174", "crime_name": "Tội lừa đảo chiếm đoạt tài sản", "dieu": "174", "allowed_khoan": ["1", "2"] },
      { "crime_key": "blhs_171", "crime_name": "Tội cướp giật tài sản", "dieu": "171", "allowed_khoan": ["1", "2"] },
      { "crime_key": "blhs_134", "crime_name": "Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác", "dieu": "134", "allowed_khoan": ["1", "2"] }
    ],
    "user_roles": ["ksv", "luat_su", "nguoi_xem", "thu_ky"],
    "limits": { "max_cases_per_day": 5, "max_active_sessions": 3, "max_witnesses": 2, "abandon_after_days": 14 },
    "remaining": { "cases_today": 3, "active_sessions": 1, "usage_available": true }
  }
}
```

- `sessions` sắp xếp theo `updated_at` mới nhất trước. `status`: `active` | `completed` | `abandoned`.
- `config.crimes` lấy từ cấu hình server. **Không hardcode** danh sách tội trong frontend.
- `remaining.cases_today` = số vụ còn được tạo hôm nay: 5 trừ số lần tạo vụ thành công từ 0 giờ (giờ Việt Nam). Tạo thất bại không tính; xóa phiên không trả lại lượt. Khi server không đọc được sổ hạn mức thì `cases_today = 0` **và** `usage_available = false`: lúc đó **không** được báo "đã tạo đủ 5 vụ"; hãy báo "Tạm thời chưa tạo được vụ án mới, bạn vui lòng thử lại sau" (khóa nút tạo vụ như khi hết lượt). `usage_available = true` là bình thường. `remaining.active_sessions` = số phiên dở dang còn được mở thêm. Bằng 0 thì khóa nút "Phiên tòa mới" và hiện lý do.
- Bộ chọn vai chỉ hiện các vai trong `config.user_roles` (nguồn duy nhất; server từ chối 422 mọi vai khác). Các vai chưa bật (Chủ tọa, Bị cáo) nếu muốn hiện thì để mờ, nhãn "Sắp có". Thẻ "Người xem": mô tả "Theo dõi trọn một phiên tòa do hệ thống đóng mọi vai"; không có pill Điều. Thẻ "Thư ký phiên tòa": pill "Điều 47, 258 BLTTHS"; mô tả gợi ý "Báo cáo sự có mặt, ghi chép và tự viết biên bản phiên tòa".

### 3.2 `POST /api/trials` — tạo vụ án và phiên (SSE)

Body (mọi trường thừa đều bị 422; **không có ô mô tả tự do**):

```json
{ "crime_key": "blhs_173", "user_role": "ksv", "victim_present": true, "witness_count": 1, "has_related_party": false }
```

| Trường | Mặc định | Ràng buộc |
|---|---|---|
| `crime_key` | bắt buộc | Một `crime_key` trong `config.crimes` (sai thì 400) |
| `user_role` | bắt buộc | Một giá trị trong `config.user_roles`: `ksv`, `luat_su`, `nguoi_xem` |
| `victim_present` | `true` | `false` nghĩa là bị hại vắng mặt, có đơn xin xét xử vắng mặt. Vụ án vẫn có bị hại, nhưng không ai hỏi bị hại tại phiên |
| `witness_count` | `1` | 0–2 |
| `has_related_party` | `false` | Có người có quyền lợi, nghĩa vụ liên quan |

Kiểm trước khi stream (có mã HTTP thật): 400, 401, 422, 429 (`trial_daily_case_limit`, `trial_active_session_limit`, `trial_global_daily_limit`, `rate_limit_exceeded`), 503 (`trial_usage_log_unavailable`).

Stream thành công, theo thứ tự:
1. `status` ("Đang chuẩn bị hồ sơ pháp lý của vụ án...")
2. `status` ("Đang dựng hồ sơ vụ án giả định...")
3. `session` `{ "session_id": "...", "title": "..." }`
4. `utterance` × n (lời Thư ký báo cáo sự có mặt ở bước 1)
5. `state`
6. `done`

Thất bại: `status`… rồi `error` ("Chưa dựng được hồ sơ vụ án hợp lệ. Bạn vui lòng thử lại."), stream đóng, **không có phiên nào được tạo** và không bị tính vào hạn mức ngày.

Thời gian: thường 10–25 giây (một lời gọi tạo vụ ~10s, có thể sinh lại 1 lần). Giao diện cần trạng thái chờ rõ ràng: hiện câu `status`, và sau 7s hiện nhắc "máy chủ đang khởi động" (dùng lại `useSlowRequestNotice`).

### 3.3 `GET /api/trials/{session_id}` — chi tiết phiên

Dùng khi mở trang phiên, sau khi tải lại trang, và sau mỗi 409. Cũng chạy bước tự chuyển `abandoned` như 3.1.

```json
{
  "state": { "...": "xem Mục 5" },
  "title": "<tên vụ án>",
  "crime_key": "blhs_173",
  "user_role": "ksv",
  "disclaimer": "Mô phỏng học tập · Không phải phiên tòa hay bản án thật · Nhân vật và tình tiết đều là giả định.",
  "court": { "name": "<tên Tòa án>", "hearing_date": "19/10/2026", "venue": "phường A, tỉnh X" },
  "participants": {
    "CHU_TOA": { "id": "CHU_TOA", "role": "Thẩm phán - Chủ tọa phiên tòa", "name": "<tên giả định>", "gender": "nam" },
    "BI_CAO":  { "id": "BI_CAO",  "role": "Bị cáo", "name": "<tên giả định>", "gender": "nu" }
  },
  "case_file": { "...": "xem Mục 7" },
  "steps": [ { "number": 1, "title": "Thư ký báo cáo sự có mặt", "legal_basis": ["300", "288", "..."] } ],
  "utterances": [ { "...": "xem Mục 4, sự kiện utterance" } ]
}
```

- `participants` gồm các id: `CHU_TOA`, `HOI_THAM_1`, `HOI_THAM_2`, `THU_KY`, `KSV`, `LUAT_SU`, `BI_CAO`, `BI_HAI`, `NLC_1`, `NLC_2` (nếu có), `NLQ` (nếu có). Tên người do code gán, là tên giả định. `participants[].name` là **tên đầy đủ**, chỉ dùng cho diễn biến phiên tòa (nhãn người nói). **Panel hồ sơ vụ án không dùng `participants`**: tên ở panel lấy từ `case_file.display_names` hoặc `case_file.<người>.name`, đã ẩn danh (Mục 7).
- `steps[].legal_basis` là số Điều của **Bộ luật Tố tụng hình sự**, dùng cho tooltip trên thanh tiến trình.
- `utterances` là toàn bộ diễn biến từ đầu, đã sắp theo `seq`.
- `court.name` là tên Tòa án đã cấu hình (mặc định `Tòa án nhân dân khu vực 1, tỉnh X`); cáo trạng, lời Chủ tọa và biên bản dùng đúng tên này và tên Viện kiểm sát tương ứng.
- **Không có** trường thẻ nhân vật (`role_brief`, `stance`, `knowledge`, `demeanor`) và không có quyết định nghị án, với **mọi** vai hiện có, kể cả `nguoi_xem` và `thu_ky`. (Thẻ `role_brief` chỉ sẽ có ở vai Bị cáo, chặng sau.)
- **Không có** ghi chép hay bản nháp biên bản của Thư ký; lấy bằng `GET /notes` (3.8) và `GET /record` (3.7).

### 3.4 `POST /api/trials/{session_id}/turn` — một lượt (SSE)

Body:

```json
{ "expected_step": 5, "expected_version": 17, "action": "speak", "text": "<lời người dùng>", "addressee": "BI_CAO", "target_step": null }
```

| `action` | Dùng khi `allowed_actions` có | Trường cần gửi | Ý nghĩa |
|---|---|---|---|
| `speak` | `speak` hoặc `speak:<ids>` | `text`; thêm `addressee` nếu dạng `speak:<ids>` | Người dùng nói |
| `end_slot` | `end_slot` | — | Kết thúc phần của mình trong slot hiện tại (xong phần hỏi, xong đối đáp, hoặc bỏ qua lượt nêu ý kiến không bắt buộc) |
| `advance` | `advance:<N>` | `target_step = N` | Sang bước kế tiếp. Chỉ có khi bước hiện tại đã xong |
| `continue` | `continue` | — | Cho AI làm tiếp lượt còn dở: sau lần tạm nghỉ do guard, sau khi mất kết nối, hoặc sau khi tải lại trang |

Vai `nguoi_xem` chỉ dùng `advance` và `continue`. `speak`/`end_slot` luôn nhận 409 `trial_action_not_allowed` (hoặc `trial_not_your_turn` khi AI đang nợ lượt). Vai `thu_ky` dùng `speak` đúng một lần (báo cáo bước 1, Mục 5.2), sau đó chỉ `advance` và `continue`.

`expected_step` và `expected_version` phải bằng `state.current_step` và `state.version` mới nhất.

Giới hạn `text` (đếm theo ký tự). **Lấy từ `state.text_limits`**, không tự suy ở client. Bảng dưới chỉ để tham khảo; nguồn duy nhất là `trial_state_machine.text_limits`:

| Slot | min | max |
|---|---|---|
| Bước 1: Thư ký báo cáo sự có mặt (chỉ vai `thu_ky`) | 100 | 3000 |
| Bước 2: ý kiến về thay đổi người tiến hành tố tụng | 1 | 1500 |
| Bước 3: công bố cáo trạng | 100 | **6000** |
| Bước 5: câu hỏi | 1 | 1500 |
| Bước 6: luận tội / Bước 7: bào chữa | 300 | 6000 |
| Bước 8: đối đáp | 1 | 6000 |

Lỗi khi vượt giới hạn:
- Vượt `max` của slot: 409 `trial_text_too_long`.
- Dưới `min` của slot: 409 `trial_text_too_short`.
- Chuỗi rỗng: 409 `trial_empty_text`.
- Trên 6000: luôn 422, do schema chặn trước.

Kiểm trước khi stream: 401, 404, 409 (Mục 6), 422, 429 (`rate_limit_exceeded`).

Stream, theo thứ tự:
1. `utterance` cho lời người dùng vừa nói (server trả lại để client hiển thị đúng `seq`). Với `continue`/`advance` thì không có.
2. Nếu người dùng đòi nhảy cóc bằng lời: thêm `utterance` `kind: "notice"` (Chủ tọa nhắc), rồi `state`, `done`. **Không có lời gọi AI nào.**
3. Với mỗi lượt AI còn nợ: `status` (tên bước + "..."), rồi các `utterance` của lượt đó.
4. `state`, `done`.

Nếu AI không vượt được guard sau khi sinh lại: `utterance` `kind: "notice"` ("Hội đồng xét xử tạm nghỉ…"), rồi `state` với `allowed_actions: ["continue"]` (hoặc `[]` nếu đã chạm cầu chì, Mục 6), rồi `done`.

Lỗi giữa chừng: `error`, stream đóng, không có `state`. Gọi lại `GET /{id}` để lấy trạng thái thật.

Độ trễ đo được: lượt thoại thường ~2s; bài phát biểu dài 3–8s; một `advance` có thể chạy 2 lượt AI liền nhau, khoảng 5–15s. Với `nguoi_xem`, một `advance` chạy **mọi** lượt AI của bước mới rồi mới trả `state`: bước 5 có 2 đoạn hỏi (~5–10s), bước 8 có 2 bài đối đáp liền nhau (~6–14s), bước 11 gồm nghị án + tuyên án + lập biên bản (có thể tới ~30s). Cứ hiện `status` của từng lượt.

### 3.5 `POST /api/trials/{session_id}/abandon`

Không có body. Phiên `active` chuyển thành `abandoned`; phiên đã kết thúc thì giữ nguyên. Trả về **object state** (Mục 5), không bọc trong trường nào.

### 3.6 `DELETE /api/trials/{session_id}`

Xóa cứng phiên, hồ sơ vụ án và toàn bộ lời thoại. Thành công trả `204` không có body. Phiên không tồn tại hoặc của người khác trả 404. Nên hỏi xác nhận trước khi gọi.

### 3.7 `GET /api/trials/{session_id}/record` — biên bản

Chỉ khi `status = completed`; nếu chưa xong thì 409 `trial_not_completed`.

Phiên `nguoi_xem`: `record.preamble = ["Phiên tòa mô phỏng do hệ thống đóng mọi vai; người học quan sát."]` (ngoài mẫu). Phiên `thu_ky` chưa chốt: `preamble = ["Bản nháp: Thư ký chưa chốt biên bản."]` và `record.draft = true`. Các trường hợp khác: `preamble = []`, `draft = false`.

**Phiên `thu_ky`** (Mục 5.2): IV.2 và IV.3 là phần **người dùng viết**, không có tóm tắt AI và không có nguyên văn: `content = "user"`, `summary` = văn bản người dùng (là `null` khi mục còn trống), `author_note = "Do Thư ký (người học) ghi"` (hiện nhãn nhỏ dưới tiêu đề mục; bản `text` in dòng `(Do Thư ký (người học) ghi)`). Mọi phần khác vẫn do code dựng như các vai khác; chữ ký Thư ký là tên đã gán cho vai. Response có thêm trường `clerk` (object như 3.9: `iv2`, `iv3`, `finalized`, `notices`, `limits`...) để dựng màn soạn; các vai khác `clerk = null`. Chưa chốt thì in vẫn được, có dòng "Bản nháp" trong `preamble`. Không có bản tóm tắt AI để đối chiếu (quyết định 7). Tên Tòa án và Viện kiểm sát lấy từ cấu hình; không còn chỗ giữ chỗ "[giả định]".

Biên bản dựng bằng code theo bố cục **Mẫu số 22-HS** (Nghị quyết 05/2017/NQ-HĐTP), nội dung theo Điều 258 BLTTHS, từ hồ sơ vụ án, thành phần, lời thoại và thời điểm của phiên. Dùng **tên đầy đủ** (không ẩn danh). Notice không vào biên bản. Route này **không** gọi LLM.

Mục IV.2 (hỏi và trả lời) và IV.3 (tranh luận) có thể là **bản tóm tắt** do Thư ký AI ghi. Bản tóm tắt được tạo đúng một lần mỗi phiên, ngay sau lời tuyên án, trong luồng SSE của lượt cuối (xem sự kiện `status` "Đang lập biên bản..." ở Mục 4). Code kiểm tra: không có số, Điều hay người nào ngoài nguồn; không markdown; tối đa 40% độ dài nguyên văn và 2500 ký tự. Nếu sai, lỗi hoặc quá hạn thì mục đó dùng nguyên văn. IV.1 (cáo trạng) và IV.4 (lời nói sau cùng) luôn là nguyên văn.

```json
{
  "session_id": "...",
  "text": "<bản văn bản thuần của record, để sao chép và in>",
  "record": {
    "disclaimer": "Mô phỏng học tập · ...",
    "form_reference": "Mẫu số 22-HS (Ban hành kèm theo Nghị quyết số 05/2017/NQ-HĐTP ...)",
    "preamble": [],
    "court_name": "Tòa án nhân dân khu vực 1, tỉnh X",
    "national_header": ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc"],
    "title": "BIÊN BẢN",
    "subtitle": "PHIÊN TÒA HÌNH SỰ SƠ THẨM",
    "opening": [ { "label": "Vào hồi", "value": "08 giờ 05 phút ngày 19 tháng 10 năm 2026", "simulated": true } ],
    "sections": [
      { "heading": "I. Những người tiến hành tố tụng", "fields": [ { "label": "...", "value": "...", "simulated": false } ],
        "entries": [], "notes": [], "subsections": [] },
      { "heading": "II. Những người tham gia tố tụng", "fields": [ "..." ] },
      { "heading": "III. Phần thủ tục bắt đầu phiên tòa", "entries": [ { "seq": 1, "step": 1, "speaker_role": "Thư ký", "speaker_name": "<tên>", "text": "<lời>" } ] },
      { "heading": "IV. Phần tranh tụng tại phiên tòa",
        "subsections": [
          { "heading": "1. Kiểm sát viên công bố bản cáo trạng ...", "content": "verbatim", "entries": [ "..." ] },
          { "heading": "2. Hỏi và trả lời tại phiên tòa", "content": "summary", "summary": "<1-3 đoạn>", "entries": [] },
          { "heading": "3. Tranh luận tại phiên tòa", "content": "verbatim", "summary_fallback": true, "entries": [ "..." ] },
          { "heading": "4. Lời nói sau cùng của bị cáo", "content": "verbatim", "entries": [ "..." ] } ],
        "notes": ["Hội đồng xét xử vào phòng nghị án để nghị án.", "..."] }
    ],
    "draft": false,
    "closing": [ { "label": "Những sửa đổi, bổ sung ...", "value": null }, { "label": "Phiên tòa kết thúc vào hồi", "value": "...", "simulated": true } ],
    "signatures": [ { "title": "THƯ KÝ GHI BIÊN BẢN PHIÊN TÒA", "note": "(Ký tên, ghi rõ họ tên)", "name": "<tên>" },
                    { "title": "THẨM PHÁN - CHỦ TỌA PHIÊN TÒA", "note": "(Ký tên, ghi rõ họ tên, đóng dấu)", "name": "<tên>" } ],
    "appendix": [ { "heading": "PHỤ LỤC (ngoài Mẫu số 22-HS): Lời tuyên án",
                    "notes": ["Phụ lục do hệ thống mô phỏng đính kèm, chép nguyên văn lời tuyên án tại phiên tòa."],
                    "entries": [ { "seq": 80, "step": 11, "speaker_role": "Chủ tọa", "speaker_name": "<tên>", "text": "<lời tuyên án>" } ] } ]
  },
  "clerk": null
}
```

Mục IV.2 trong phiên `thu_ky`:

```json
{ "heading": "2. Hỏi và trả lời tại phiên tòa", "content": "user", "summary": "<văn bản Thư ký viết>",
  "author_note": "Do Thư ký (người học) ghi", "entries": [] }
```

Thứ tự hiển thị: dòng mô phỏng → `preamble` (nếu có, chữ nhỏ) → `court_name` (trái) và `national_header` (phải) → `title`, `subtitle` (giữa) → `opening` → `sections` theo thứ tự → `closing` → `signatures` (hai cột) → `appendix` → dòng mô phỏng.

| Thành phần | Ý nghĩa |
|---|---|
| `fields[].value = null` | Không có dữ liệu. Hiển thị **dòng chấm trống** như mẫu (`......`), không tự điền |
| `fields[].simulated = true` | Giá trị do code gán cho mô phỏng (ngày giờ, nơi xét xử, "công khai"). Tên Viện kiểm sát lấy từ cấu hình nên không còn `simulated`. Có thể in nghiêng hoặc thêm chú thích "giả định" |
| Dấu `......` bên trong `value` | Phần của mẫu không có dữ liệu (ví dụ "dân tộc", "con ông ... và bà ...", Văn phòng luật sư) |
| `content` | `"summary"`: hiển thị `summary` (văn bản theo quy ước 4.1, đã có tên đầy đủ), kèm nhãn nhỏ "Tóm tắt". `"user"` (chỉ phiên `thu_ky`): hiển thị `summary` (văn bản Thư ký viết, đã làm sạch) kèm `author_note`; `summary = null` thì hiện dòng chấm trống. `"verbatim"`: hiển thị `entries`. Không có trường này hoặc `null` thì coi là `"verbatim"` |
| `draft` | `true` = biên bản của Thư ký chưa chốt (Mục 3.10) |
| `summary_fallback` | `true` = đã thử tóm tắt nhưng không đạt kiểm tra, nên dùng nguyên văn. Chỉ để thông tin; không cần báo lỗi cho người dùng |
| `appendix` | **Ngoài mẫu**: lời tuyên án nguyên văn. Hiển thị sau phần chữ ký, có tiêu đề rõ là phụ lục, tách khỏi thân biên bản |
| Thứ tự trong **một mục** (`sections[]`, `subsections[]`) | `heading` → `fields` → nội dung (`summary` nếu `content = "summary"`, nếu không thì `entries`) → `subsections` → `notes`. Tức là **notes đứng SAU nội dung**, ví dụ các câu "Hội đồng xét xử vào phòng nghị án..." nằm sau mục 4 của phần IV |
| Thứ tự trong **phụ lục** (`appendix[]`) | Ngoại lệ: `heading` → `notes` → `entries`. `notes` ở đây là câu giới thiệu phụ lục nên đứng **TRƯỚC** lời tuyên án |
| `sections[].entries` | Lời trong phiên, nguyên văn, theo `seq`. Phần III = bước 1–2. Phần IV chia 4 mục: 1 = bước 3, 2 = bước 4–5, 3 = bước 6–8, 4 = bước 9. `text` theo quy ước văn bản ở 4.1 |
| `sections[].notes` | Câu cố định của mẫu. Theo hướng dẫn (29) của mẫu, biên bản **không chép phần quyết định** của bản án; lời tuyên án vẫn có trong `utterances` bước 11 |
| `signatures` | Tên đầy đủ của Thư ký và Chủ tọa |

`text` là bản thuần của chính `record` (mục tóm tắt là đoạn tóm tắt; phụ lục nằm sau chữ ký): dòng mô phỏng ở đầu và cuối, các dòng `preamble` ngay sau dòng mô phỏng đầu; tiêu đề phần (I–IV) in hoa trên một dòng riêng; mỗi trường một dòng `"<nhãn>: <giá trị>"` (trống thì `......`); mỗi lời một dòng `"<Vai> <Tên>: <lời>"`. Frontend nên render từ `record`; `text` dùng cho nút sao chép và cho bản in dự phòng. Có nút "In / lưu PDF" dùng chức năng in của trình duyệt. **Không** sửa, không cắt, không bỏ hai dòng mô phỏng.

### 3.8 `GET`, `PUT /api/trials/{session_id}/notes` — ghi chép của Thư ký

Chỉ phiên `thu_ky`. Ghi chép **không phải lời nói tại phiên tòa**: không đi qua `/turn`, không đổi `state` hay `version`, không bao giờ vào prompt của AI, không có trong `GET /{id}`, `GET /api/trials`, SSE hay biên bản. Chỉ hai route này trả lại ghi chép, cho chính chủ phiên.

`PUT` body (trường thừa thì 422):

```json
{ "text": "<toàn bộ ghi chép, 0-20000 ký tự>" }
```

`GET` và `PUT` cùng trả:

```json
{ "notes": "<ghi chép đã lưu>", "updated_at": "2026-10-29T08:12:03.123456+00:00", "max_chars": 20000 }
```

- `PUT` **thay toàn bộ** ghi chép (không nối thêm). Gửi chuỗi rỗng để xóa. Server chỉ chuẩn hóa xuống dòng (`\r\n` → `\n`) và bỏ ký tự điều khiển; trả lại văn bản đã lưu.
- Lưu được khi phiên `active` hoặc `completed`, kể cả lúc AI đang sinh lượt (không đụng khóa sinh, không gây `trial_busy`). Phiên `abandoned`: 409 `trial_not_active`.
- Chưa có ghi chép thì `GET` trả `{"notes": "", "updated_at": null, "max_chars": 20000}`.
- Gợi ý giao diện (THIET-KE 11.3.7): tự lưu khi ngừng gõ 2 giây; hiện "Đã lưu lúc …" từ `updated_at`. Giới hạn tần suất chung 60 request/phút.
- Lỗi: 404 (phiên không có hoặc của người khác), 409 `trial_not_clerk` (phiên vai khác), 409 `trial_not_active`, 422 (`text` thiếu hoặc dài hơn 20000).

### 3.9 `PUT /api/trials/{session_id}/record/draft` — Thư ký soạn mục IV.2, IV.3

Chỉ phiên `thu_ky` đã `completed` và chưa chốt. Body (trường thừa thì 422; bỏ một mục hoặc gửi `null` thì giữ nguyên nội dung đã lưu của mục đó):

```json
{ "iv2": "<mục 2. Hỏi và trả lời tại phiên tòa>", "iv3": "<mục 3. Tranh luận tại phiên tòa>" }
```

Trả `TrialClerkDraft`:

```json
{
  "iv2": "Chủ tọa hỏi bị cáo <tên> về diễn biến vụ án; bị cáo khai ...",
  "iv3": "",
  "updated_at": "2026-10-29T08:40:10.000000+00:00",
  "finalized": false,
  "finalized_at": null,
  "notices": [
    { "section": "iv2", "code": "unknown_amount", "message": "Mục 2 nêu 5.000.000 đồng; con số này không xuất hiện trong phần hỏi và trả lời." },
    { "section": "iv3", "code": "empty", "message": "Mục 3 chưa có nội dung." }
  ],
  "limits": { "min": 200, "max": 4000, "hard_max": 6000 }
}
```

- Server **làm sạch** văn bản trước khi lưu và trả lại bản đã làm sạch (client thay nội dung textarea bằng bản này): chuẩn hóa xuống dòng, bỏ ký tự điều khiển, bỏ dấu markdown (`**`, `__`, `` ` ``, `#` đầu dòng), đổi `* `/`+ ` đầu dòng thành `- `, gộp nhiều dòng trống thành một, cắt khoảng trắng đầu/cuối. Không đổi chữ nào khác.
- `notices` là các **"Lưu ý"** (chỉ phản hồi, không chặn, không chấm điểm), tính lại mỗi lần lưu, 0 lời gọi AI. `message` là câu tiếng Việt hiển thị nguyên văn cạnh mục tương ứng. Các `code`:

| `code` | Khi nào |
|---|---|
| `empty` | Mục chưa có chữ nào |
| `too_short` / `too_long` | Ngắn hơn `limits.min` (200) / dài hơn `limits.max` (4000) ký tự |
| `unknown_amount` / `unknown_percent` | Số tiền / tỷ lệ % không có trong lời nói ở các bước của mục đó (IV.2 = bước 4–5, IV.3 = bước 6–8) |
| `citation_missing_law` | Viện dẫn "Điều N" mà không ghi Bộ luật Hình sự hay Bộ luật Tố tụng hình sự |
| `citation_not_in_section` | Viện dẫn một Điều mà không ai viện dẫn trong các bước của mục đó |
| `unknown_name` | Có một tên người không thuộc phiên tòa (tên đầy đủ của người trong phiên thì hợp lệ) |

- Mỗi mục tối đa `limits.hard_max` = 6000 ký tự; dài hơn thì 422. Từ 4001 đến 6000 vẫn lưu được, kèm lưu ý `too_long`.
- Lỗi: 404, 409 `trial_not_clerk`, 409 `trial_not_completed` (phiên chưa xong), 409 `trial_record_finalized` (đã chốt, không sửa được nữa), 422.

### 3.10 `POST /api/trials/{session_id}/record/finalize` — chốt biên bản

Chỉ phiên `thu_ky` đã `completed`. Không có body. Chốt **bản nháp đã lưu** (client lưu bằng 3.9 trước khi gọi). Trả **giống hệt `GET /record`** (3.7) với `record.draft = false` và `clerk.finalized = true`.

- Lưu ý **không chặn** chốt. Chỉ chặn khi một trong hai mục còn trống: 409 `trial_record_section_empty`.
- Idempotent: gọi lại sau khi đã chốt trả đúng biên bản cũ (cùng `finalized_at`), không lỗi.
- Sau khi chốt: `PUT /record/draft` nhận 409 `trial_record_finalized`; ghi chép (3.8) vẫn sửa được nhưng không ảnh hưởng biên bản.
- Lỗi: 404, 409 `trial_not_clerk`, `trial_not_completed`, `trial_record_section_empty`.

---

## 4. Sự kiện SSE

Mỗi khối có dạng `event: <tên>\ndata: <JSON>\n\n`. Header của response là `Content-Type: text/event-stream`.

| Sự kiện | Payload | Ghi chú |
|---|---|---|
| `status` | `{ "message": "Đang dựng hồ sơ vụ án giả định..." }` | Câu báo tiến trình. Hiện ở dòng chờ (3 chấm + câu); không lưu vào diễn biến. Ở lượt cuối, sau `utterance` tuyên án sẽ có `status` "Đang lập biên bản..." (tối đa ~60 giây), rồi mới tới `state` (completed) và `done` (trừ phiên `thu_ky`: không có bước này). Phiên đã lưu là completed **trước** bước này: nếu stream đứt ở đây thì chỉ cần `GET /{id}`; biên bản vẫn mở được (có thể là nguyên văn) |
| `session` | `{ "session_id": "uuid", "title": "<tên vụ án>" }` | Chỉ ở `POST /api/trials`. Nhận được thì chuyển sang URL `/trial/<session_id>` |
| `utterance` | xem dưới | Một lời trong phiên tòa |
| `state` | object state (Mục 5) | Luôn là state mới nhất; thay toàn bộ state ở client |
| `error` | `{ "message": "<câu tiếng Việt cho người dùng>" }` | Sau đó stream đóng. Hiện khung lỗi + nút "Thử lại" (gọi `GET /{id}`) |
| `done` | `{}` | Kết thúc stream bình thường |

**Không có sự kiện `notice` riêng.** Notice là `utterance` có `kind: "notice"`.

Payload `utterance`:

```json
{
  "seq": 42,
  "step": 5,
  "speaker_id": "BI_CAO",
  "speaker_role": "Bị cáo",
  "speaker_name": "<tên giả định>",
  "is_user": false,
  "kind": "speech",
  "text": "<lời thoại>",
  "addressee": null
}
```

| Trường | Ý nghĩa |
|---|---|
| `seq` | Thứ tự trong phiên, tăng dần, duy nhất. Dùng làm key khi render; sự kiện trùng `seq` thì bỏ qua |
| `step` | Bước 1–11 mà lời này thuộc về |
| `speaker_id` | Một trong các id ở 3.3 |
| `speaker_role` | Nhãn vai tiếng Việt (Chủ tọa, Hội thẩm, Thư ký, Kiểm sát viên, Luật sư bào chữa, Bị cáo, Bị hại, Người làm chứng, Người có quyền lợi, nghĩa vụ liên quan) |
| `speaker_name` | Tên giả định |
| `is_user` | `true` = lời của người dùng (bong bóng phải, nền primary). Phiên `nguoi_xem` không bao giờ có `true`; phiên `thu_ky` chỉ có đúng một lời `true` (báo cáo bước 1) |
| `kind` | `speech` = lời thoại thường; `procedural` = câu thủ tục soạn sẵn (báo cáo của Thư ký, "kết thúc phần xét hỏi"...), hiển thị dạng dòng thủ tục nhỏ; `notice` = Chủ tọa nhắc trật tự hoặc tạm nghỉ, hiển thị kiểu riêng, **không** thuộc biên bản |
| `text` | Lời của AI đã có tên thật thay cho placeholder. Lời người dùng giữ nguyên văn đã gửi |
| `addressee` | Chỉ có ở câu hỏi của người dùng tại bước 5: id người được hỏi |

### 4.1 Quy ước văn bản (lời AI, cáo trạng, biên bản)

Server chuẩn hóa bằng code sau khi sinh, nên frontend có thể dựa vào:

- Các **đoạn** cách nhau đúng **một dòng trống** (`\n\n`). Không có hai dòng trống liền nhau.
- Dòng bắt đầu bằng `"- "` là **gạch đầu dòng**. Các dòng liền nhau bằng một `\n` (không có dòng trống) là ngắt dòng trong cùng một khối, ví dụ phần đầu cáo trạng (Viện kiểm sát, số, ngày) hoặc tiêu đề mục rồi tới dòng đầu tiên.
- **Không có markdown**: không `**`, `#`, `*`. Hiển thị văn bản thuần; không chạy trình render markdown.
- Lời dài (luận tội, bào chữa, đối đáp, tuyên án, lời khai mạc hoặc giải thích quyền dài hơn 600 ký tự) có nhiều đoạn, thường mở đầu bằng cụm dẫn kết thúc bằng dấu hai chấm ("Về hành vi phạm tội:"). Lời ngắn (hỏi, đáp, lời khai) chỉ có một đoạn.
- Lời người dùng giữ nguyên văn đã gửi, không chuẩn hóa.

Gợi ý render: tách theo `\n\n` thành đoạn; trong mỗi đoạn, nhóm các dòng `"- "` liên tiếp thành danh sách; các dòng còn lại là dòng thường.

---

## 5. State

```json
{
  "session_id": "uuid",
  "current_step": 5,
  "step_title": "Kiểm sát viên và luật sư xét hỏi",
  "status": "active",
  "awaiting": "user",
  "allowed_actions": ["speak:BI_CAO|BI_HAI|NLC_1", "end_slot"],
  "version": 17,
  "text_limits": { "min": 1, "max": 1500 },
  "procedure_note": null,
  "clerk_prompt": null,
  "clerk_report": null
}
```

| Trường | Ý nghĩa |
|---|---|
| `current_step` | 1–11, xem bảng dưới |
| `status` | `active` / `completed` / `abandoned` |
| `awaiting` | `user`: đến lượt người dùng. `ai`: AI còn nợ một lượt (thường chỉ thấy khi stream bị đứt, hoặc sau lần tạm nghỉ). `none`: phiên đã kết thúc |
| `allowed_actions` | Danh sách hành động duy nhất được phép. Giao diện **chỉ** hiện nút hoặc ô nhập tương ứng |
| `version` | Tăng sau mỗi thay đổi. Gửi lại đúng giá trị này trong `expected_version` |
| `text_limits` | `{min, max}` số ký tự cho lần `speak` kế tiếp ở slot hiện tại; `null` khi không có action nói. Dùng cho bộ đếm, khóa nút gửi và câu nhắc ("cần ít nhất 300 ký tự"). Vai `nguoi_xem`: luôn `null` |
| `procedure_note` | Chỉ vai `nguoi_xem`: chú giải thủ tục của `current_step` (Mục 5.1). Các vai khác: luôn `null` |
| `clerk_prompt` | Chỉ vai `thu_ky`: câu nhắc ghi chép của `current_step` (Mục 5.2). Các vai khác: luôn `null` |
| `clerk_report` | Chỉ vai `thu_ky`, chỉ khi báo cáo bước 1 đang chờ người dùng: lời mẫu điền sẵn và danh sách có mặt (Mục 5.2). Mọi lúc khác: `null` |

Các dạng `allowed_actions`:

| Giá trị | Giao diện |
|---|---|
| `speak` | Ô nhập lời. Bước 3: textarea, có thể điền sẵn `case_file.indictment_text` cho KSV đọc. Bước 6/7: textarea lớn có bộ đếm. Bước 8: ô đối đáp. Ngưỡng lấy từ `text_limits` |
| `speak:ID1\|ID2\|...` | Bước 5: chọn người được hỏi trong các id liệt kê (gửi `addressee`), cùng ô nhập câu hỏi |
| `end_slot` | Nút "Kết thúc phần hỏi của tôi" (bước 5), "Kết thúc đối đáp" (bước 8), hoặc "Không có ý kiến" (bước 2) |
| `advance:N` | Nút "Chuyển sang phần tiếp theo" (gửi `target_step: N`) |
| `continue` | Nút "Tiếp tục" |
| `[]` khi `awaiting = "ai"` | Cầu chì tạm nghỉ đã chạm (Mục 6). Không có nút tiếp; chỉ cho hủy hoặc xóa phiên |
| `[]` khi `awaiting = "none"` | Phiên đã xong hoặc đã hủy. Phiên `completed` thì hiện link biên bản |

Bước và vai được nói (★ = lượt người dùng, tùy vai):

| Bước | Tiêu đề (`step_title`) | Lượt của KSV | Lượt của luật sư |
|---|---|---|---|
| 1 | Thư ký báo cáo sự có mặt | — (vai `thu_ky`: ★ báo cáo, Mục 5.2) | — |
| 2 | Khai mạc phiên tòa | ★ ý kiến về thay đổi người tiến hành tố tụng (không bắt buộc) | ★ như KSV |
| 3 | Công bố cáo trạng | ★ đọc cáo trạng | — |
| 4 | Hội đồng xét xử xét hỏi | — | — |
| 5 | Kiểm sát viên và luật sư xét hỏi | ★ hỏi (ít nhất 1 câu, tối đa 8) | ★ hỏi, sau khi AI KSV hỏi xong |
| 6 | Kiểm sát viên luận tội | ★ luận tội | — |
| 7 | Luật sư bào chữa | — | ★ bào chữa |
| 8 | Tranh luận, đối đáp | ★ mở đối đáp, AI luật sư đáp (1–3 vòng) | ★ AI KSV mở, người dùng đáp (1–3 vòng) |
| 9 | Bị cáo nói lời sau cùng | — | — |
| 10 | Nghị án | — | — |
| 11 | Tuyên án | — | — |

Các bước không có ★ do AI làm hết. Người dùng chỉ thấy `advance:N` khi bước đã xong.

### 5.1 Vai Người xem (`nguoi_xem`)

- Không có lượt nói nào: không ô nhập, không chọn người được hỏi. `allowed_actions` chỉ có `advance:N` (khi bước đã xong) hoặc `continue` (sau tạm nghỉ hay mất kết nối); `text_limits` luôn `null`.
- Nhịp: mỗi `advance` chạy hết các lượt AI của bước mới rồi dừng chờ người dùng bấm tiếp. AI không dừng giữa các phần trong cùng một bước.
- AI đóng cả KSV và luật sư: bước 3 KSV đọc cáo trạng nguyên văn; bước 5 KSV hỏi rồi luật sư hỏi; bước 6 luận tội; bước 7 bào chữa; bước 8 **một vòng đối đáp** = KSV rồi luật sư, hai `utterance` riêng.
- Chỗ ô soạn hiển thị thẻ **"Chú giải thủ tục"** từ `state.procedure_note` cùng nút "Chuyển sang phần tiếp theo":

```json
"procedure_note": {
  "step": 5,
  "title": "Kiểm sát viên và luật sư xét hỏi",
  "text": "<đoạn văn tĩnh, tối đa 80 từ>",
  "legal_basis": ["307", "317", "318"],
  "reviewed": false
}
```

| Trường | Ý nghĩa |
|---|---|
| `step`, `title` | Trùng `current_step`, `step_title` |
| `text` | Văn bản thuần, một đoạn, cố định (không do AI sinh) |
| `legal_basis` | Số Điều **Bộ luật Tố tụng hình sự**; có thể hiện bằng pill mở `ArticleModal` |
| `reviewed` | `false` = bản nháp chưa được nhóm luật duyệt. Khi `false` hiện nhãn nhỏ "Bản nháp, đang chờ nhóm luật duyệt" |

- `state` mới đến sau mỗi `advance` (sự kiện `state` cuối stream) đã mang chú giải của bước mới; không cần gọi thêm route nào.
- Panel hồ sơ vụ án giữ nguyên như các vai khác (đầy đủ, đã ẩn danh, không có thẻ nhân vật).
- Phiên đã `completed`: `procedure_note` là của bước 11.

### 5.2 Vai Thư ký (`thu_ky`)

Người dùng là Thư ký phiên tòa (THIET-KE 11.3). AI đóng mọi vai còn lại, như Người xem (cả KSV, luật sư, đối đáp AI–AI một vòng).

**Bước 1 — lượt nói duy nhất.** Khi tạo phiên, server **không** chạy lượt AI nào: state đầu tiên có `awaiting = "user"`, `allowed_actions = ["speak"]` (không có `end_slot`, không bỏ qua được), `text_limits = {"min": 100, "max": 3000}`, và `clerk_report`:

```json
"clerk_report": {
  "prefill": "Thưa Hội đồng xét xử, theo giấy triệu tập của Tòa án, tại phiên tòa hôm nay có mặt: Kiểm sát viên <tên>; bị cáo <tên>; ... Thư ký phiên tòa đã phổ biến nội quy phiên tòa. Báo cáo Hội đồng xét xử.",
  "attendance": [
    { "speaker_id": "KSV", "role": "Kiểm sát viên", "name": "<tên>", "present": true },
    { "speaker_id": "BI_CAO", "role": "Bị cáo", "name": "<tên>", "present": true },
    { "speaker_id": "LUAT_SU", "role": "Luật sư bào chữa", "name": "<tên>", "present": true },
    { "speaker_id": "BI_HAI", "role": "Bị hại", "name": "<tên>", "present": false },
    { "speaker_id": "NLC_1", "role": "Người làm chứng", "name": "<tên>", "present": true }
  ]
}
```

- Textarea điền sẵn `prefill` (tên đầy đủ), người dùng sửa được; bên cạnh là danh sách `attendance` để đối chiếu (`present: false` = vắng mặt, có đơn đề nghị xét xử vắng mặt).
- Gửi bằng `speak` như mọi lời nói. Lời được lưu và đưa vào biên bản (phần III) **nguyên văn**, `speaker_id = "THU_KY"`, `is_user = true`. Báo cáo sai người có mặt không bị chặn; Chủ tọa AI ở bước 2 kiểm tra theo hồ sơ.
- Lỗi: dưới 100 ký tự 409 `trial_text_too_short`; trên 3000 409 `trial_text_too_long`; `advance` trước khi báo cáo 409 `trial_slot_not_finished`; `continue` 409 `trial_not_ai_turn`.
- `clerk_report` chỉ có khi báo cáo đang chờ người dùng; mọi lúc khác là `null`.

**Bước 2–11.** Không có lượt nói: `allowed_actions` chỉ có `advance:N` hoặc `continue`, `text_limits` luôn `null`; `speak`/`end_slot` nhận 409 `trial_action_not_allowed`. Nhịp giống Người xem: mỗi `advance` chạy hết lượt AI của bước mới.

**Câu nhắc ghi chép.** Ở mọi bước, `state.clerk_prompt` cho biết Thư ký nên ghi gì (văn bản tĩnh, không do AI sinh):

```json
"clerk_prompt": { "step": 4, "text": "Ghi cho mục IV.2: ai hỏi, hỏi ai, nội dung chính của câu hỏi và câu trả lời; ...", "reviewed": false }
```

`reviewed: false` = chưa được nhóm luật duyệt: hiện nhãn nhỏ "Bản nháp, đang chờ nhóm luật duyệt". Vai `thu_ky` có `procedure_note = null`.

**Ghi chép** trong phiên: route 3.8. **Sau tuyên án**: phiên `completed` như mọi vai, nhưng **không** có lời gọi tóm tắt biên bản (không có `status` "Đang lập biên bản..."). Màn biên bản mở ở chế độ soạn: `GET /record` (3.7) trả bản nháp, người dùng viết IV.2 và IV.3 (3.9), xem `notices`, rồi chốt (3.10).

---

## 6. 409, khóa sinh và cầu chì tạm nghỉ

Body của 409:

```json
{ "error": { "code": "trial_version_mismatch", "message": "Trạng thái phiên tòa đã thay đổi hoặc thao tác không hợp lệ ở bước hiện tại." },
  "state": { "...": "state hiện tại trên server" } }
```

| `error.code` | Nghĩa | Frontend làm gì |
|---|---|---|
| `trial_version_mismatch`, `trial_step_mismatch` | State ở client đã cũ (bấm hai lần, mở hai tab) | Thay state bằng `state` trong body, rồi gọi `GET /{id}` để đồng bộ `utterances` |
| `trial_busy` | Một stream khác đang chạy lượt AI của phiên này (khóa tối đa 180s) | Báo "Phiên tòa đang xử lý ở cửa sổ khác", đợi vài giây rồi `GET /{id}` |
| `trial_not_your_turn`, `trial_not_ai_turn` | Gửi hành động không đúng lượt | Đồng bộ lại như dòng đầu |
| `trial_skip_not_allowed` | `advance` tới bước không phải bước kế tiếp | Không nên xảy ra nếu chỉ dựng nút từ `allowed_actions` |
| `trial_slot_not_finished` | `advance` hoặc `end_slot` khi phần hiện tại chưa đủ điều kiện (ví dụ chưa hỏi câu nào) | Hiện câu nhắc nhẹ |
| `trial_action_not_allowed`, `trial_turn_limit` | Hành động không thuộc slot, hoặc đã hết số lượt hỏi/đối đáp. Vai `nguoi_xem` gửi `speak`/`end_slot` | Đồng bộ lại |
| `trial_missing_addressee` | Câu hỏi bước 5 thiếu `addressee` hợp lệ (ví dụ hỏi bị hại vắng mặt) | Bắt chọn người được hỏi |
| `trial_empty_text`, `trial_text_too_short`, `trial_text_too_long` | Lời trống, ngắn hơn ngưỡng, hoặc dài quá ngưỡng của slot | Chặn ngay ở client theo ngưỡng ở 3.4; 409 chỉ là lớp dự phòng |
| `trial_not_active` | Phiên đã `completed` hoặc `abandoned` (kể cả vừa tự chuyển sau 14 ngày). Với ghi chép (3.8): chỉ khi `abandoned` | Chuyển giao diện sang chế độ chỉ xem |
| `trial_not_completed` | Gọi biên bản, soạn hoặc chốt biên bản (3.9, 3.10) khi phiên chưa xong | Ẩn link biên bản cho tới khi `completed` |
| `trial_not_clerk` | Gọi route của Thư ký (3.8–3.10) trên phiên vai khác | Không nên xảy ra; chỉ hiện các route này cho phiên `thu_ky` |
| `trial_record_finalized` | Sửa bản nháp sau khi đã chốt | Chuyển màn biên bản sang chế độ xem |
| `trial_record_section_empty` | Chốt khi IV.2 hoặc IV.3 còn trống | Khóa nút "Chốt biên bản" khi một mục trống; 409 chỉ là lớp dự phòng |
| `trial_guard_exhausted` | Cầu chì: AI đã tạm nghỉ 3 lần liên tiếp ở cùng một chỗ | Xem dưới |

**Tạm nghỉ do guard.** Mọi lời AI đều được kiểm trước khi gửi: không nói bằng vai người dùng; chỉ viện dẫn Điều có trong ngữ cảnh, kèm đúng tên luật; không nêu số tiền ngoài hồ sơ; không tự đặt tên người. Lỗi được sinh lại 1 lần. Vẫn lỗi thì server gửi notice "Hội đồng xét xử tạm nghỉ…" và `allowed_actions: ["continue"]`. Người dùng bấm "Tiếp tục" để thử lại.

**Cầu chì.** Sau **3 notice tạm nghỉ liên tiếp** ở cùng một chỗ, `allowed_actions` thành `[]` dù `awaiting = "ai"`, và mọi `continue` nhận 409 `trial_guard_exhausted`. Giao diện báo: "Phiên tòa không thể tiếp tục ở bước này. Bạn có thể hủy phiên và tạo vụ án mới." Kèm nút Hủy hoặc Xóa. Không tự gửi `continue` lặp lại.

**Mất kết nối giữa chừng.** Những lượt AI đã xong trước khi mất kết nối đều đã được lưu; lượt đang chạy thì bị bỏ, không lưu nửa chừng. Khi người dùng quay lại hoặc tải lại trang: gọi `GET /{id}`. Nếu `allowed_actions` là `["continue"]` thì hiện nút "Tiếp tục". **Không tự động gửi** `continue` khi tải trang; để người dùng bấm.

---

## 7. `case_file` (panel hồ sơ vụ án)

Có trong `GET /{id}`. Tên người đã điền sẵn **và đã ẩn danh** (dưới đây). Nơi cư trú do code gán từ danh sách địa danh giả định ("phường A, tỉnh X"...), giống cách gán tên người; model không đặt nơi cư trú. Server **không bao giờ** trả quyết định nghị án (`verdict_json`), lý do nghị án, các tham số dựng vụ án, hay "thẻ nhân vật". Nội dung phần quyết định chỉ xuất hiện dưới dạng lời tuyên án trong `utterances` ở bước 11.

```json
{
  "title": "...", "incident_summary": "...",
  "defendant": { "id": "BI_CAO", "gender": "nam", "age": 27, "occupation": "...", "residence_place": "phường A, tỉnh X",
                 "statement_summary": "...", "education": "...", "prior_record": "...", "preventive_measure": "..." },
  "victim":    { "id": "BI_HAI", "gender": "nu", "age": 41, "occupation": "...", "residence_place": "...", "statement_summary": "..." },
  "witnesses": [ { "id": "NLC_1", "...": "cùng các trường như victim" } ],
  "related_party": null,
  "facts":    [ { "id": "F1", "time": "...", "place": "...", "description": "..." } ],
  "evidence": [ { "id": "E1", "type": "vat_chung", "description": "...", "value_vnd": null, "injury_percent": null, "fact_id": "F1" } ],
  "pretrial_statements": [ { "person_id": "BI_CAO", "summary": "...",
                             "inconsistencies": [ { "text": "...", "claimed_amount_vnd": null } ] } ],
  "charge": { "dieu": "173", "khoan": "1", "diem": [], "crime_name": "Tội trộm cắp tài sản" },
  "measure_value": 35000000,
  "compensation_vnd": null,
  "extra_amounts": [ { "label": "...", "amount_vnd": 7000000, "evidence_id": "E1" } ],
  "mitigating":  [ { "khoan": "1", "diem": "s", "fact_ids": ["F2"] } ],
  "aggravating": [ { "khoan": "1", "diem": "g", "fact_ids": ["F3"] } ],
  "civil_claim": { "claimant_id": "BI_HAI", "amount_vnd": 2000000, "basis": "..." },
  "indictment_text": "<cáo trạng, theo quy ước 4.1>",
  "display_names": { "CHU_TOA": "Nguyễn Văn An", "KSV": "...", "BI_CAO": "Trần Đức H", "BI_HAI": "Huỳnh Hữu V" }
}
```

Mỗi object người (`defendant`, `victim`, `witnesses[]`, `related_party`) có thêm trường `name` (tên hiển thị trên panel).

**Ẩn danh trong panel.** Bị cáo, bị hại, người làm chứng, người có quyền lợi, nghĩa vụ liên quan hiển thị dạng họ + tên đệm + chữ cái đầu của tên ("Trần Đức Hùng" → "Trần Đức H"). Chủ tọa, Hội thẩm, Thư ký, Kiểm sát viên, luật sư giữ tên đầy đủ. Server đã thay trong **mọi** trường văn bản của `case_file` (tóm tắt, cáo trạng, chứng cứ, lời khai, nhân thân). Frontend:
- lấy tên người trong panel từ `display_names[id]` (ví dụ `claimant_id`, `pretrial_statements[].person_id`), **không** từ `participants`;
- không tự ghép lại tên đầy đủ trong panel.
Ẩn danh chỉ áp dụng cho panel. Diễn biến phiên tòa (`utterances`) và biên bản dùng tên đầy đủ.

**Cáo trạng** (`indictment_text`, vụ tạo từ chặng 3D): phần đầu gồm Viện kiểm sát, số cáo trạng, ngày, mỗi thông tin một dòng; sau đó bốn mục, tiêu đề trên dòng riêng: "I. Nội dung vụ án", "II. Hành vi phạm tội và chứng cứ", "III. Nhân thân và tình tiết", "IV. Kết luận và truy tố"; chứng cứ là gạch đầu dòng. Có thể in đậm các dòng tiêu đề này. Vụ cũ có thể là một khối liền, nên frontend phải hiển thị được cả hai dạng. Khi người dùng là KSV, cáo trạng điền sẵn ở bước 3 là chính văn bản này.

| Trường | Ghi chú hiển thị |
|---|---|
| `evidence[].type` | `vat_chung` vật chứng · `giam_dinh` kết luận giám định · `dinh_gia` kết luận định giá · `tai_lieu` tài liệu |
| `measure_value` | Số quyết định khoản: **đồng** với tội 171/173/174, **% tổn thương cơ thể** với tội 134 |
| `charge.dieu`, `mitigating`, `aggravating` | Điều tội danh thuộc **Bộ luật Hình sự**. `mitigating` thuộc Điều 51 BLHS, `aggravating` thuộc Điều 52 BLHS. Có thể hiện bằng pill mở `ArticleModal` sẵn có |
| Số tiền | Số nguyên đồng; định dạng `12.500.000 đồng` ở client |

Gợi ý tab của panel: Tóm tắt (`title`, `incident_summary`, `charge`), Người tham gia, Lời khai (`pretrial_statements`), Chứng cứ (`evidence`, `extra_amounts`), Căn cứ pháp lý.

---

## 8. Dòng nhắc mô phỏng

Chuỗi nằm trong `disclaimer` (3.3). Bắt buộc hiện ở **mọi** màn hình của tính năng, dưới dạng banner cố định, nền muted, không dùng màu đỏ/vàng chức năng. Biên bản đã có sẵn dòng này ở đầu và cuối do server chèn.

---

## 9. Điều frontend KHÔNG được làm

1. **Không lưu lời thoại, hồ sơ vụ án hay biên bản** vào `localStorage`, `sessionStorage`, IndexedDB, cache của service worker, URL hay query string. Chỉ được lưu trong bộ nhớ của trang và lấy lại bằng `GET /{id}`. Bản nháp người dùng đang gõ cũng không lưu. Ghi chép và bản nháp biên bản của Thư ký lưu **ở server** (3.8, 3.9), không ở trình duyệt.
13. **Không đưa ghi chép của Thư ký vào bất kỳ request nào khác** ngoài `PUT /notes` (không gửi kèm `/turn`, không ghép vào lời báo cáo).
2. **Không ghi lời thoại hay nội dung người dùng nhập** vào `console.log`, công cụ analytics, Sentry, log lỗi hay bất kỳ dịch vụ bên thứ ba nào. Khi báo lỗi chỉ ghi mã lỗi, `session_id` và số bước.
3. **Không tự dựng nút hành động** ngoài `state.allowed_actions`. Không suy ra bước kế tiếp ở client. Không cho chuyển bước bằng cách gõ lời.
4. **Không tự động lặp lại `continue`** hay gửi lại request sau 409 hoặc `error`. Luôn đồng bộ bằng `GET /{id}` và để người dùng bấm.
5. **Không hiển thị lời AI trước khi nhận sự kiện `utterance`**. Server gửi lời đã qua guard thành từng khối; không có streaming token, và frontend không được giả lập chữ chạy như thể đang sinh.
6. **Không sửa, cắt hay tóm tắt** lời trong `utterances` hoặc trong biên bản; không bỏ dòng mô phỏng. Không render markdown (4.1).
7. **Không hardcode** danh sách tội, giới hạn, tên bước hay tên Tòa án. Lấy từ `config`, `steps`, `step_title`, `court`.
8. **Không dùng `EventSource`** cho các route SSE (cần POST + Authorization); dùng `fetch` + reader.
9. **Không gửi trường thừa** trong body (server trả 422) và **không gửi văn bản tự do** khi tạo vụ án (bản đầu không có ô mô tả).
10. **Không hiển thị như thật**: không gọi kết quả là "bản án", "phán quyết" ngoài khung mô phỏng; không chấm điểm người dùng.
11. **Không gọi Gemini hay Supabase trực tiếp** cho tính năng này, và không đọc ghi các bảng `mock_trial_*` từ client. RLS chặn sẵn, mọi thứ phải đi qua backend.
12. **Không hiện tên đầy đủ trong panel hồ sơ vụ án**: không lấy tên panel từ `participants`, dùng `case_file.display_names` (Mục 7).
