# Vai Chủ tọa (backend) — Kế hoạch pha 1

Trạng thái: **kế hoạch, chưa code**. Nhánh `muc5-chu-toa-backend` (từ `origin/main` af1b073). Pha này không gọi Gemini (0 lời gọi), không sửa `backend/` hay `frontend/`, không đọc `data/private/`.

Nguồn đúng: `THIET-KE.md` Mục 11.4 và quyết định 11.8 (đặc biệt 13–17, 19–21). Tài liệu này chỉ cụ thể hóa cách làm; chỗ nào thiết kế thiếu hoặc mâu thuẫn với code hay văn bản luật thì ghi ở Mục 0.2 và Mục 10, kèm phương án mặc định an toàn, **không** đổi quyết định đã chốt.

Mọi căn cứ pháp lý dưới đây đã đối chiếu với `ingestion/chunks.json` (BLTTHS 2015 sửa đổi 2021 và 2025, BLHS văn bản hợp nhất 2025). Bảng đối chiếu đầy đủ ở Phụ lục A. Điều nào corpus không có thì ghi "corpus không đủ".

Quy ước: **B** = mục thủ tục bắt buộc, **T** = tùy chọn. "Lời gọi" = lời gọi sinh Gemini. Tên kiểu lượt trong yêu cầu ("executive") chính là kiểu slot `preside` của thiết kế 11.0(c); code dùng tên `preside`.

---

## 0. Tóm tắt

### 0.1 Mười điểm chính

1. **Một slot điều hành cho mỗi bước.** Với vai `chu_toa`, mỗi bước 2–11 chỉ có một slot `preside` (lượt người dùng). Việc của người dùng là làm các **mục thủ tục** (B/T) theo danh mục trong code. Lời AI chỉ chạy khi người dùng hỏi hoặc mời. Bước 1 giữ nguyên (Thư ký AI, lời mẫu, 0 lời gọi).
2. **Trạng thái điều hành nằm trong `user_work.preside`**, không cần migration. Ghi cùng `version` qua `update_state`/`claim_and_update` (chống ghi đè). Riêng vai Chủ tọa phải bỏ quy ước "user_work không đi với version" của `trial_repository` (Mục 2.1).
3. **AI không nói thay Chủ tọa, nhờ cấu trúc.** `CHU_TOA` không có trong mọi enum người nói. Mọi câu do code chèn mà hiện đang gán `CHU_TOA` (tạm nghỉ, nhắc nhảy cóc, câu hỏi dự phòng, lời mẫu kết thúc phần) chuyển sang người nói `HE_THONG` hoặc thành lời của người dùng. `usurps_presiding` (AI chiếm quyền điều hành) chỉ ở **mức đo**, chưa chặn, theo quyết định 14.
4. **Chuyển bước chỉ bằng nút.** `advance` khi còn thiếu mục B trả 409 `trial_procedure_incomplete` kèm `missing_items`. Bộ phát hiện nhảy cóc bằng lời **tắt** cho vai này. Người dùng im lặng thì không có gì xảy ra: không hẹn giờ, không có lời nhắc của AI.
5. **Lời mẫu do code dựng, 0 lời gọi.** Mỗi mục có `template` (đã điền tên) trả trong `state`. Phần trả lời mang tính thủ tục (lý lịch bị cáo, "không có đề nghị thay đổi", cam đoan của người làm chứng, "không yêu cầu xét hỏi thêm") cũng dựng bằng code. Bước 2 vì vậy còn 0 lời gọi, thay vì 3 lời gọi như bảng 11.4.1.
6. **Form quyết định (phương án A)** gồm các trường của `Verdict`, cộng thêm xử lý vật chứng và án phí (hiện `Verdict` chưa có hai phần này). `PUT /decision` lưu và kiểm tra, 0 lời gọi. `decide` (qua `/turn`) chốt quyết định, bị chặn khi còn lỗi cứng. Kiểm tra cứng giữ nguyên `check_verdict`, thêm 4 luật có căn cứ trong corpus: sàn Điều 54 khoản 1, Điều 54 khoản 3, tù tối thiểu 03 tháng, phạt tiền tối thiểu. Các kiểm tra còn lại chỉ là cảnh báo mềm (Mục 3).
7. **Không có "phán quyết ẩn" trong phiên Chủ tọa.** Hồ sơ vụ án **không** chứa phán quyết mẫu: `verdict_json` chỉ do lời gọi nghị án AI tạo ở bước 10 của các vai khác. Phiên Chủ tọa **không bao giờ** gọi lời nghị án AI. Đề xuất không sinh quyết định AI nào để so sánh, kể cả sau khi chốt (Mục 4).
8. **Bước 11:** hệ thống soạn lời tuyên từ quyết định đã chốt (1 lời gọi, `tuyen_an` hiện có). Người dùng đọc trước, rồi bấm "Tuyên án". Lời này ghi là lời của Chủ tọa (`is_user`), kèm cờ `system_drafted`. Điều 327 cho phép Chủ tọa đọc bản án.
9. **Điều 323:** đề xuất chỉ cho trở lại xét hỏi **ở bước 8**, tối đa 1 lần mỗi phiên, sau đó về bước 8. Cách này khớp bảng 11.4.1 và giao diện 11.4.7, tránh bỏ sót luận tội hoặc bào chữa (Mục 6). Biên bản: IV.2 thêm ghi chú cố định; thêm phụ lục "Biên bản nghị án" (Điều 259) dựng bằng code. `GET /record` vẫn không gọi LLM.
10. **Chi phí:** phiên điển hình ~17–20 lời gọi (gồm tạo vụ và tóm tắt biên bản), ~210–260K token vào. Phiên dùng mọi mục tùy chọn và trở lại xét hỏi: ~30–33 lời gọi, ~380–420K token vào. Người dùng làm khoảng **33 thao tác** ở mức tối thiểu, ~40–45 ở mức điển hình (Bị cáo: 13–15). Đây là rủi ro lớn nhất về trải nghiệm. Đo ở pha 2: ~60 lời gọi, **trần cứng 80**.

### 0.2 Mâu thuẫn và khoảng trống phát hiện được (không tự sửa quyết định)

| # | Chỗ | Vấn đề | Đề xuất mặc định |
|---|---|---|---|
| M1 | Yêu cầu pha 1, mục 4 | Yêu cầu viết "hồ sơ vụ án có phán quyết mẫu ẩn". Code thì khác: `case_json` chỉ có `knobs` (khoản, lập trường, điểm tình tiết do code chọn, không trả ra ngoài). `verdict_json` do lời gọi `_deliberate` sinh ở bước 10 (vai KSV, Luật sư, Người xem, Thư ký, Bị cáo) | Phiên Chủ tọa không gọi `_deliberate` lần nào. Có test bảo đảm (Mục 4) |
| M2 | 11.4.6 và 11.4.1/11.4.7 | 11.4.6 cho trở lại xét hỏi "từ bước 6–8, rồi quay thẳng về bước 8". Bảng 11.4.1 và giao diện 11.4.7 thì chỉ đặt nút ở bước 8. Nếu trở lại từ bước 6 hoặc 7 rồi về thẳng bước 8 thì phiên **bỏ mất** luận tội hoặc bào chữa | Chỉ cho ở bước 8 (câu hỏi Q3) |
| M3 | Bảng 11.4.1 bước 2 | Thiếu việc Chủ tọa "phải hỏi" có ai yêu cầu triệu tập thêm người làm chứng, đưa thêm vật chứng, hay hoãn phiên tòa khi có người vắng mặt (Điều 305 BLTTHS) | Thêm mục `hoi_yeu_cau` ở mức **T** cho tới khi nhóm luật duyệt (Q6) |
| M4 | Bảng 11.4.1 bước 2 | Ghi "AI phản hồi 1 lời gọi" cho các mục căn cước, thay đổi người tiến hành tố tụng, cam đoan | Dùng câu trả lời mẫu, 0 lời gọi (Q5). Chỉ gọi AI khi người dùng tự hỏi câu căn cước bằng lời riêng |
| M5 | `check_verdict` và Điều 298 khoản 2 | Văn bản: "Tòa án có thể xét xử bị cáo theo khoản khác với khoản mà Viện kiểm sát đã truy tố trong cùng một điều luật…" (không có chữ "nhẹ hơn"). Code chỉ cho khoản đã truy tố hoặc khoản nhẹ hơn | Giữ cách chặt hơn của code (an toàn, giống 11.4.4). Nhóm luật xác nhận (Q9) |
| M6 | `check_verdict` và Điều 54 | Thiếu sàn "phải trong khung hình phạt liền kề nhẹ hơn" (khoản 1). Không hỗ trợ khoản 3 (khung nhẹ nhất: dưới mức thấp nhất hoặc "chuyển sang một hình phạt khác thuộc loại nhẹ hơn"), nên chặn oan, ví dụ Điều 171 khoản 1 kèm Điều 54 sang cải tạo không giam giữ | Thêm cả hai, **chỉ ở chế độ người dùng**, để không đổi số đo của vai AI (Q10) |
| M7 | `check_verdict` và Điều 38, 35 BLHS | Chưa kiểm tù tối thiểu 03 tháng, chưa kiểm mức phạt tiền ≥ 1.000.000 đồng | Thêm ở chế độ người dùng |
| M8 | `Verdict` | Không có trường xử lý vật chứng hay án phí. Ở các vai khác, lời tuyên AI tự viết phần này | Thêm `DecisionExtras` riêng cho Chủ tọa (Mục 3.1), không đổi `Verdict` |
| M9 | `trial_repository` (docstring) | "user_work … never with the state fields, and without touching version" là quy ước cho Thư ký | Vai Chủ tọa ghi `user_work` cùng version (Mục 2.1). Quy ước của Thư ký giữ nguyên |
| M10 | `trial_turn_service`, `api/trials.py` | Code chèn câu mang tên `CHU_TOA`: `GUARD_PAUSE_TEXT`, `skip_refusal_text`, `_TEMPLATES` (kết thúc xét hỏi/tranh luận, vào nghị án), `INVITATIONS`, `fallback_question`. Instruction `answer_question` cũng cho phép `{CHU_TOA}` nhắc nhở. Ở phiên Chủ tọa, những câu này thành **hệ thống nói thay người dùng** | Tạm nghỉ và notice dùng người nói `HE_THONG`. Lời mẫu của Chủ tọa chỉ ghi khi người dùng làm mục. `answer_question` có biến thể không có `CHU_TOA` |
| M11 | `_dispatch` (`tuyen_an`) | Gọi `_deliberate_if_needed`: nếu thiếu quyết định thì AI tự nghị án | Với `chu_toa`: thiếu quyết định thì ném lỗi, không bao giờ nghị án AI |
| M12 | Quyết định 15 và Điều 326 khoản 1 | Luật: "Hội thẩm biểu quyết trước, Thẩm phán biểu quyết sau cùng". Thiết kế: Hội thẩm chỉ nêu ý kiến tham khảo, không biểu quyết đè | Hội thẩm góp ý **trên bản nháp** của người dùng, không tự đưa ra mức án (tránh "mỏ neo"). Ghi rõ chỗ lệch thứ tự so với luật (Q7) |
| M13 | Điều 322 khoản 3 | "Chủ tọa phiên tòa không được hạn chế thời gian tranh luận". Thiết kế giới hạn tối đa 2 vòng | Giữ 2 vòng vì là giới hạn của bản mô phỏng; chú giải ghi rõ đây là giới hạn của mô phỏng (Q12) |

---

## 1. Phạm vi theo bước

AI đóng: 2 Hội thẩm, Thư ký (lời mẫu), KSV, Luật sư, bị cáo, bị hại, người làm chứng, người có quyền lợi, nghĩa vụ liên quan. Người dùng là `CHU_TOA`. Kiểu lượt: **mục** (`item`, thủ tục, có lời mẫu), **hỏi** (`ask`, câu hỏi cho một người), **mời** (`invite`, chạy một phần AI có sẵn), **phát biểu khác** (`remark`, có hoặc không có người nhận). Không có "đoạn xen" kiểu Bị cáo: AI không đặt câu hỏi cho Chủ tọa.

| Bước | Mục (khóa · B/T · kiểu) | Phản hồi (lời gọi) | Thứ tự bắt buộc | Căn cứ (BLTTHS) |
|---|---|---|---|---|
| 1 | — | Thư ký báo cáo, lời mẫu (0) | | 300, 301 kh.2 |
| 2 | `khai_mac` B item · `kiem_tra_can_cuoc` B item (hỏi `BI_CAO`) · `kiem_tra_co_mat` B item (kèm giới thiệu thành phần) · `giai_thich_quyen` B item · `hoi_thay_doi` B item · `cam_doan_nlc` B item (khi có người làm chứng) · `hoi_yeu_cau` **T** item (M3) | căn cước: bị cáo trả lời lý lịch dựng từ hồ sơ (0; 1 nếu người dùng tự viết câu hỏi) · thay đổi: KSV, luật sư, bị cáo "không có đề nghị" (0) · cam đoan: từng người làm chứng (0) · hỏi yêu cầu: "không có yêu cầu" (0) | `khai_mac` trước tiên | 301, 302, 304, 305 |
| 3 | `moi_cong_bo_cao_trang` B invite | KSV đọc nguyên văn cáo trạng (0) | | 306 |
| 4 | `hoi_bi_cao` B ask (≥1 câu cho `BI_CAO`) · `cong_bo_loi_khai_bi_hai` B item (khi bị hại vắng mặt; lời mẫu từ lời khai trước phiên tòa) · hỏi bị hại, người làm chứng, người có quyền lợi liên quan: T ask · `moi_hoi_tham_hoi` T invite | mỗi câu hỏi 1 · Hội thẩm hỏi 1 đoạn (1) | | 307, 308 kh.2 đ.d, 309–311 |
| 5 | `moi_ksv_hoi` B invite · `moi_ls_hoi` B invite · `ket_thuc_xet_hoi` B item | mỗi lời mời 1 đoạn `ai_qa_loop` (1) · kết thúc: "không yêu cầu xét hỏi thêm" (0) | `ket_thuc_xet_hoi` sau cùng | 307 kh.2, 318 |
| 6 | `moi_luan_toi` B invite | luận tội (1) | | 320 kh.1, 321 |
| 7 | `moi_bao_chua` B invite · `moi_bi_hai_trinh_bay` B invite (khi bị hại có mặt) · `hoi_bi_cao_bo_sung` T invite | 1 mỗi lời mời | (gợi ý, không chặn: bào chữa trước bị hại, theo khoản 2 rồi khoản 3 Điều 320) | 320 kh.2–3 |
| 8 | `moi_doi_dap` B invite (vòng 1) · `vong_2` T invite · `tro_lai_xet_hoi` T (Điều 323, 1 lần/phiên) · `ket_thuc_tranh_luan` B item | mỗi vòng 2 (KSV rồi luật sư) | `ket_thuc_tranh_luan` sau cùng | 322, 323, 324 kh.1 |
| 9 | `moi_loi_sau_cung` B invite | bị cáo (1). Sau đó **không** cho hỏi bị cáo (Điều 324 kh.2) | | 324 |
| 10 | `vao_nghi_an` B item · `y_kien_hoi_tham` T invite · `chot_quyet_dinh` B (`decide`) | Hội thẩm góp ý trên bản nháp (1, tùy chọn) · chốt (0) | `vao_nghi_an` trước tiên; ý kiến Hội thẩm phải trước khi chốt | 326, 259 |
| 11 | `tuyen_an` B: `prepare_pronouncement` rồi `pronounce` | soạn lời tuyên (1) · tuyên (0) · tóm tắt biên bản (1, như KSV) | soạn trước rồi mới tuyên | 327, 260, 298 |

"Phát biểu khác" (`remark`): ở bước 2–9, tối đa 5 lần mỗi bước (quyết định 13). Có người nhận (KSV, luật sư, bị cáo, bị hại, người làm chứng, người có quyền lợi liên quan có mặt) thì tốn 1 lời gọi; không có người nhận thì 0. Bước 10–11 không có (đang nghị án hoặc tuyên án). Ở bước 9, sau lời sau cùng, `remark` gửi tới `BI_CAO` trả 409 (Điều 324 khoản 2: "Không được đặt câu hỏi khi bị cáo nói lời sau cùng").

Trần: bước 4 tối đa 10 câu hỏi (quyết định 13). Trở lại xét hỏi: người dùng tối đa 3 câu, mỗi lời mời KSV hoặc luật sư hỏi tối đa 3 câu (11.4.6).

---

## 2. Kiểu lượt điều hành (`preside`)

### 2.1 Mô hình trạng thái

`SessionState` thêm một trường, chỉ có giá trị khi vai là `chu_toa`:

```
PresideState (frozen dataclass, lưu ở mock_trial_sessions.user_work["preside"])
  done: tuple[str, ...]          # khóa mục đã làm ở bước hiện tại
  questions: int                 # số câu hỏi đã hỏi ở bước hiện tại (trần bước 4: 10; khi trở lại xét hỏi: 3)
  remarks: int                   # số lần phát biểu khác ở bước hiện tại (trần 5)
  rounds: int                    # số vòng đối đáp đã xong ở bước 8
  job: Job | None                # việc AI đang nợ; awaiting = "ai" khi job khác None
  returned: bool                 # đã dùng Điều 323 chưa
  in_return: bool                # đang ở bước 5 sau khi trở lại xét hỏi
Job = {kind: "answer"|"invite"|"assessor"|"pronounce_draft", key, addressee?, item?, progress: int}
```

- `slot_index` luôn là 0 (một slot `preside` mỗi bước). `slot_user_turns` không dùng. `pending_ai` = `job is not None`. Cột cũ giữ nguyên nghĩa với mọi vai khác.
- Khi chuyển bước thì `done`, `questions`, `remarks`, `rounds` về 0. `returned` giữ nguyên suốt phiên.
- **Lưu không cần migration:** `user_work` (jsonb, migration 0013 đã chạy) có thêm các khóa `preside`, `decision_draft`, `pronouncement_draft`. Với vai `chu_toa`, `state_fields(ctx)` trả thêm `user_work`, nên khóa này được ghi **cùng** `version` qua `claim_and_update`/`update_state`. Mọi lần ghi `user_work` khác của vai này (`PUT /decision`) cũng đi qua `update_state` có kiểm `expected_version`, và bị từ chối với 409 `trial_busy` khi khóa sinh đang giữ. Nhờ vậy luồng SSE và việc lưu bản nháp không ghi đè lẫn nhau. Vai Thư ký giữ nguyên `update_user_work` không kèm version.
- Phương án dự phòng, nếu người duyệt muốn tách bạch: migration `0015` thêm `mock_trial_sessions.preside_state jsonb null`. **Không đề xuất**, vì cách trên đã đủ an toàn.
- `utterances.procedure_item` (cột của 0013, đang null): ghi khóa mục cho lời của người dùng và lời mẫu. Thêm vào `Utterance`, `utterance_rows`, `utterance_from_row` và repo trong bộ nhớ.

### 2.2 Hành động, `allowed_actions`, `awaiting`

Thêm vào `TrialTurnRequest.action`: `item`, `ask`, `invite`, `remark`, `return_to_questioning`, `decide`, `prepare_pronouncement`, `pronounce`. Thêm trường `item: str | None` (≤ 40 ký tự). Các trường `text`, `addressee`, `target_step` giữ nguyên.

| Hành động | Trường | Kết quả | Lời gọi |
|---|---|---|---|
| `item` | `item`; `text` (null hoặc rỗng = dùng lời mẫu) | Ghi lời Chủ tọa (`is_user`, `procedure_item`) + câu trả lời mẫu nếu có; đánh dấu đã làm | 0 (trừ căn cước tự viết: 1) |
| `ask` | `addressee`, `text` | Ghi câu hỏi; `job = answer` | 1 |
| `invite` | `item` | Ghi lời mời (lời mẫu, hoặc `text` nếu có); `job = invite` | 1–2 |
| `remark` | `text`, `addressee?` | Ghi lời; có người nhận thì `job = answer` | 0–1 |
| `return_to_questioning` | `text?` | Mục 6 | 0 |
| `decide` | — | Chốt `decision_draft` (Mục 3) | 0 |
| `prepare_pronouncement` | — | `job = pronounce_draft` | 1 |
| `pronounce` | — | Ghi lời tuyên, phiên `completed` | 0 (+1 tóm tắt biên bản) |
| `advance`, `continue` | như cũ | | |

`allowed_actions` của vai `chu_toa` (khi `awaiting = user`):
- `item:<k1>|<k2>…`: các mục còn làm được (chưa làm, đủ điều kiện, đúng thứ tự).
- `ask:<ids>`: người có thể hỏi. Có ở bước 2 (chỉ `BI_CAO`, qua mục căn cước), bước 4, và bước 5 khi đang trở lại xét hỏi. Còn trần thì mới có.
- `invite:<k1>|…`, `remark` (còn trần), `return_to_questioning` (Mục 6), `decide` (bản nháp không còn lỗi cứng), `prepare_pronouncement`/`pronounce` (bước 11), `advance:N` (chỉ khi đủ mục B).
- Khi `awaiting = ai`: như cũ, `["continue"]` hoặc `[]` (cầu chì).

`text_limits` hiện là một cặp `{min, max}`. Vai này cần giới hạn theo chế độ nhập, nên thêm `state.presiding.limits = {item: [1,3000], ask: [1,1500], remark: [1,1500], reasoning: [200,2000]}` (11.4.1). `text_limits` của vai này giữ `null` để client cũ không dùng nhầm.

Thêm `state.presiding` (chỉ `chu_toa`; mọi vai khác `null`, có test):

```json
"presiding": {
  "step": 4,
  "items": [ { "key": "hoi_bi_cao", "label": "Hỏi bị cáo", "required": true, "kind": "ask", "done": false,
               "available": true, "template": null, "basis": ["307", "309"] },
             { "key": "moi_hoi_tham_hoi", "label": "Mời Hội thẩm hỏi", "required": false, "kind": "invite",
               "done": false, "available": true, "template": "Mời Hội thẩm nhân dân …", "basis": ["307"] } ],
  "missing_required": ["hoi_bi_cao"],
  "counters": { "questions_left": 10, "remarks_left": 5 },
  "addressees": ["BI_CAO", "BI_HAI", "NLC_1"],
  "limits": { "item": [1, 3000], "ask": [1, 1500], "remark": [1, 1500], "reasoning": [200, 2000] },
  "return_available": false, "returned": false, "in_return": false,
  "templates_reviewed": false
}
```

### 2.3 Việc AI (job) và hàm sinh dùng lại

`run_ai_turn` với vai `chu_toa`: đọc `state.preside.job` thay vì slot, chạy hàm sinh tương ứng, rồi `complete_ai_turn` xóa job (hoặc tăng `progress`) và đánh dấu mục đã xong.

| Job | Dùng lại | Thay đổi |
|---|---|---|
| `answer` (câu hỏi của Chủ tọa) | `_generate_segment` với `speakers = (addressee,)` | Instruction `answer_question_presiding`: như `answer_question`, nhưng bỏ câu "{CHU_TOA} được nhắc nhở" (M10). Giữ quy tắc phủ nhận tiền đề sai |
| `invite:moi_hoi_tham_hoi` | `_generate_segment` | Người nói: `HOI_THAM_1`, `HOI_THAM_2` và người làm chứng/bị hại/bị cáo có mặt. Instruction mới (Hội thẩm hỏi, Chủ tọa không nói) |
| `invite:moi_ksv_hoi`, `moi_ls_hoi` | nhánh `ai_qa_loop` của `_dispatch` | Khi đang trở lại xét hỏi: chỉ dẫn "tối đa 3 câu" |
| `invite:moi_luan_toi`, `moi_bao_chua`, `moi_bi_hai_trinh_bay` | `_generate_speech` / `_generate_segment` theo `SlotSpec` có sẵn (`luan_toi`, `bao_chua`, `bi_hai_trinh_bay`) | `bi_hai_trinh_bay` bỏ `chu_toa` khỏi người nói |
| `invite:hoi_bi_cao_bo_sung`, `moi_loi_sau_cung` | `_generate_segment` (`speakers = ("BI_CAO",)`) | Instruction ngắn, chỉ bị cáo nói |
| `invite:moi_doi_dap`, `vong_2` | nhánh `is_ai_debate` (`progress` 0→1→2 thay cho `slot_user_turns`) | Lưu state sau mỗi bài như hiện tại |
| `assessor` (ý kiến Hội thẩm) | `ctx.recorder.call` mới, schema `{hoi_tham_1:{dong_y:bool, y_kien}, hoi_tham_2:{…}}` | Đầu vào: hồ sơ, diễn biến, **bản nháp của người dùng** (bọc `<<<LOI_NGUOI_HOC>>>`). Guard: Rule 9 lenient, số tiền, tên; không được nêu mức án hoặc số tháng nào không có trong bản nháp |
| `pronounce_draft` | nhánh `tuyen_an` (`_generate_speech`, strict, `_charge_citation_check`) | Lấy `ctx.verdict` từ quyết định đã chốt; **không** gọi `_deliberate_if_needed` (M11). Thêm 2 dòng: vật chứng, án phí theo `DecisionExtras`. Nhận định của người dùng bọc như lời người dùng. Kết quả lưu ở `user_work.pronouncement_draft`, **chưa** là utterance |

### 2.4 Guard chống AI nói thay hoặc điều hành thay Chủ tọa

Theo cấu trúc (chặn cứng, có ngay):
- `ai_speaker_ids` đã loại id của vai người dùng, nên `CHU_TOA` không có trong mọi enum. `_check_utterance` vẫn có `speaker_is_student` làm lớp dự phòng.
- Không có code nào tự ghi lời `CHU_TOA`. Lời mẫu chỉ được ghi khi người dùng bấm làm mục. Notice tạm nghỉ, notice cầu chì và mọi câu hệ thống dùng `HE_THONG`, nhãn "Hệ thống"; notice không vào biên bản (M10).
- Không có lời gọi nghị án AI (M11). Lời tuyên do hệ thống soạn chỉ thành lời Chủ tọa khi người dùng bấm `pronounce`.
- Chuyển bước, kết thúc phần, quyết định: chỉ qua hành động có cấu trúc. Không lời AI nào đổi được state (như mọi vai).

Theo nội dung (đo, chưa chặn; quyết định 14):
- Cờ `usurps_presiding` trên lời AI có cụm điều hành: "tuyên bố kết thúc phần", "chuyển sang phần", "Hội đồng xét xử (đã) quyết định|chấp nhận|cho phép", "Chủ tọa (đã) đồng ý", "mời … trình bày" do người khác nói. Ngoại lệ: Hội thẩm hỏi khi được mời, KSV hay luật sư nói "đề nghị Hội đồng xét xử…".
- Chỉ bật cứng (sinh lại 1 lần rồi tạm nghỉ) khi số đo cho thấy tỷ lệ bắt oan ≤ 2% (quyết định 14). Pha 2 lưu nguyên văn lời bị gắn cờ **ngoài repo** để phân loại tay, như R3.
- `speaks_for_student` thêm mẫu cho `CHU_TOA` ("Chủ tọa đã/vừa yêu cầu|tuyên bố|cho phép…" khi người dùng không nói), cũng ở mức đo.

### 2.5 Im lặng, nhảy bước, làm lại mục

- **Im lặng:** server không hẹn giờ. Phiên đứng ở `awaiting = user` tới khi người dùng thao tác, hoặc tự `abandoned` sau 14 ngày (như mọi vai). Thư ký AI không nhắc (11.4.1). Checklist cho thấy mục còn thiếu.
- **Nhảy bước bằng nút hay API:** `advance` sai bước trả `trial_skip_not_allowed`. Thiếu mục B trả `trial_procedure_incomplete` kèm `missing_items: [khóa…]` trong body 409. Mục không thuộc bước, chưa đủ điều kiện (ví dụ `cam_doan_nlc` khi không có người làm chứng) hoặc sai thứ tự trả `trial_item_not_available`.
- **Nhảy bước bằng lời:** bộ phát hiện tắt cho vai này (11.4.1). Câu "chuyển sang phần tranh luận" được ghi như một phát biểu, state không đổi.
- **Làm lại mục:** mỗi mục làm một lần (409 `trial_item_done`). Muốn nói lại thì dùng "Phát biểu khác". `invite` không chạy lần hai (11.4.8).
- **Lời mời khi AI đang chạy:** 409 `trial_not_your_turn`, như hiện tại.

---

## 3. Form quyết định (bước 10–11)

### 3.1 Trường (phương án A)

`ChairDecision` = các trường của `Verdict` (không đổi model, để guard và lời tuyên dùng lại) + `DecisionExtras`:

| Nhóm | Trường | Ghi chú form |
|---|---|---|
| Tội danh | `guilty`, `dieu` (cố định = Điều truy tố), `khoan` (chọn trong khoản đã truy tố và khoản nhẹ hơn), `diem[]` | Form chỉ cho chọn giá trị hợp lệ; guard là lớp dự phòng |
| Tình tiết | `mitigating[]`, `aggravating[]`: `{khoan, diem, fact_ids≥1}` | Chọn từ danh sách điểm Điều 51/52 có trong gói pháp lý; bắt buộc gắn sự việc |
| Hình phạt | `penalty_type` (`tu` · `cai_tao_khong_giam_giu` · `phat_tien` · `khong`), `penalty_months`, `fine_vnd`, `applies_dieu_54` | Với 4 tội hiện có (khoản 1–2) không khoản nào có phạt tiền là hình phạt chính, nên form ẩn `phat_tien`. Hình phạt bổ sung (ví dụ khoản 5 Điều 173): backlog |
| Án treo | `suspended`, `probation_months` | |
| Dân sự | `civil_amount_vnd` | Hiện kèm `civil_claim.amount_vnd` và `compensation_vnd` của hồ sơ để đối chiếu |
| Vật chứng (mới) | `exhibits[]: {evidence_id, disposition}`, `disposition ∈ {tra_lai, tich_thu_sung_ngan_sach, tich_thu_tieu_huy, luu_ho_so}` | Một dòng cho mỗi chứng cứ loại `vat_chung` |
| Án phí (mới) | `defendant_pays_criminal_fee: bool`, `defendant_pays_civil_fee: bool` | Không có ô số tiền: corpus không có văn bản về mức án phí |
| Nhận định | `reasoning_summary` (200–2.000 ký tự) | Dùng thay nhận định AI trong lời tuyên |

### 3.2 Kiểm tra

**Cứng** = chặn `decide`, hiện cạnh trường kèm câu căn cứ. **Mềm** = cảnh báo, vẫn chốt được. Mọi kiểm tra là phản hồi, không chấm điểm, không nhận xét mức án nặng hay nhẹ (11.4.6).

| # | Kiểm | Loại | Có sẵn? | Căn cứ trong corpus (trích ngắn) |
|---|---|---|---|---|
| K1 | Đúng Điều đã truy tố; khoản đã truy tố hoặc khoản nhẹ hơn | Cứng | có | Điều 298 khoản 1–2 BLTTHS: "Tòa án xét xử những bị cáo và những hành vi theo tội danh mà Viện kiểm sát truy tố"; "có thể xét xử bị cáo theo khoản khác … trong cùng một điều luật". Code chặt hơn văn bản, xem M5 |
| K2 | Điểm có trong khoản; không dùng điểm liên quan người dưới 18 tuổi | Cứng | có | Văn bản Điều tội danh trong gói; loại người dưới 18 tuổi là quyết định 19/10/2026 (Chương XXVIII BLTTHS đã bãi bỏ, luật thay thế không có trong corpus) |
| K3 | Mức tù trong khung của khoản | Cứng | có | Ví dụ Điều 173 khoản 1 BLHS: "phạt cải tạo không giam giữ đến 03 năm hoặc phạt tù từ 06 tháng đến 03 năm"; khoản 2: "phạt tù từ 02 năm đến 07 năm" |
| K4 | Dưới mức thấp nhất của khung chỉ khi có Điều 54 và ≥ 2 tình tiết khoản 1 Điều 51 | Cứng | có | Điều 54 khoản 1 BLHS: "khi người phạm tội có ít nhất hai tình tiết giảm nhẹ quy định tại khoản 1 Điều 51" |
| K5 | **Mới:** áp dụng Điều 54 khoản 1 thì mức tù vẫn ≥ mức thấp nhất của khung liền kề nhẹ hơn (ví dụ khoản 2 → sàn là 06 tháng của khoản 1) | Cứng | **chưa** | Điều 54 khoản 1: "nhưng phải trong khung hình phạt liền kề nhẹ hơn của điều luật" |
| K6 | **Mới:** khung đã là khung nhẹ nhất (khoản 1): được dưới mức thấp nhất, hoặc chuyển sang hình phạt nhẹ hơn (cải tạo không giam giữ) dù khoản không có loại đó | Nới (bỏ chặn oan) | **chưa** | Điều 54 khoản 3: "khung hình phạt đó là khung hình phạt nhẹ nhất, thì Tòa án có thể quyết định hình phạt dưới mức thấp nhất … hoặc chuyển sang một hình phạt khác thuộc loại nhẹ hơn. Lý do của việc giảm nhẹ phải được ghi rõ trong bản án" |
| K7 | **Mới:** tù có thời hạn ≥ 03 tháng | Cứng | **chưa** | Điều 38 khoản 1 BLHS: "mức tối thiểu là 03 tháng và mức tối đa là 20 năm" |
| K8 | Cải tạo không giam giữ 06 tháng–03 năm, và khoản có loại này (trừ K6) | Cứng | có | Điều 36 khoản 1 BLHS: "từ 06 tháng đến 03 năm đối với người phạm tội ít nghiêm trọng, phạm tội nghiêm trọng" |
| K9 | Phạt tiền chính chỉ khi khoản có; **mới:** ≥ 1.000.000 đồng và trong khung của khoản | Cứng | một phần | Điều 35 khoản 1, 3 BLHS: "không được thấp hơn 1.000.000 đồng" |
| K10 | Án treo: tù ≤ 03 năm, thử thách 01–05 năm | Cứng | có | Điều 65 khoản 1 BLHS: "Khi xử phạt tù không quá 03 năm … ấn định thời gian thử thách từ 01 năm đến 05 năm" |
| K11 | **Mới:** án treo mà không có tình tiết giảm nhẹ nào | Mềm | chưa | Điều 65 khoản 1: "căn cứ vào nhân thân của người phạm tội và các tình tiết giảm nhẹ". Điều kiện chi tiết (Nghị quyết 02/2018/NQ-HĐTP): **corpus không đủ** |
| K12 | Tình tiết trỏ tới sự việc có thật | Cứng | có | Điều 326 khoản 2 BLTTHS: "chỉ được căn cứ vào những chứng cứ, tài liệu đã được thẩm tra tại phiên tòa" |
| K13 | **Mới:** tình tiết tăng nặng hoặc giảm nhẹ trùng dấu hiệu định khung | Mềm | chưa | Điều 52 khoản 2 BLHS: "Các tình tiết đã được Bộ luật này quy định là dấu hiệu định tội hoặc định khung hình phạt thì không được coi là tình tiết tăng nặng"; Điều 51 khoản 3 (giảm nhẹ). Bảng đối chiếu điểm định khung ↔ điểm Điều 51/52: nhóm luật lập |
| K14 | **Mới:** dùng điểm của khoản 2 Điều 51 ("tình tiết khác") thì nhắc ghi lý do trong nhận định | Mềm | chưa | Điều 51 khoản 2: "phải ghi rõ lý do giảm nhẹ trong bản án" |
| K15 | Có tội thì phải có hình phạt; không có tội thì không có hình phạt, không có án treo | Cứng | có | Điều 326 khoản 3 điểm c, d BLTTHS; miễn hình phạt (Điều 59 BLHS) ngoài phạm vi mô phỏng |
| K16 | **Mới:** bồi thường không vượt số tiền bị hại yêu cầu (`civil_claim`) | **Mềm** cho tới khi nhóm luật xác nhận (quyết định 18) | chưa | Điều 30 BLTTHS (giải quyết vấn đề dân sự cùng vụ án hình sự); Điều 48 khoản 1 BLHS ("bồi thường thiệt hại vật chất đã được xác định"). Nguyên tắc "không vượt yêu cầu" (Bộ luật Dân sự, Bộ luật Tố tụng dân sự): **corpus không đủ** |
| K17 | **Mới:** mỗi vật chứng có một cách xử lý | Cứng | chưa | Điều 326 khoản 3 điểm e BLTTHS: nghị án phải giải quyết "xử lý vật chứng"; Điều 106 khoản 1: "do Hội đồng xét xử quyết định nếu vụ án đã đưa ra xét xử" |
| K18 | **Mới:** tịch thu tài sản bị chiếm đoạt (vật chứng có giá trị bằng `measure_value`, tội 171/173/174) | Mềm | chưa | Điều 47 khoản 2 BLHS: "Đối với vật, tiền bị người phạm tội chiếm đoạt … thì không tịch thu mà trả lại cho chủ sở hữu"; Điều 106 khoản 2–3 BLTTHS |
| K19 | **Mới:** không có tội mà bị cáo chịu án phí hình sự | Cứng | chưa | Điều 136 khoản 2 BLTTHS: "Án phí do người bị kết án hoặc Nhà nước chịu". Mức án phí (Nghị quyết 326/2016/UBTVQH14): **corpus không đủ**, nên form không có ô số tiền |
| K20 | **Mới:** vụ Điều 134 khoản 1 tuyên không có tội: nhắc trường hợp bị hại chịu án phí | Mềm | chưa | Điều 136 khoản 3 BLTTHS và Điều 155 khoản 1 BLTTHS (khởi tố theo yêu cầu bị hại, khoản 1 Điều 134) |
| K21 | **Mới:** nhận định 200–2.000 ký tự | Cứng (chỉ độ dài) | chưa | Điều 260 khoản 2 điểm d BLTTHS (bản án phải có nhận định) |
| K22 | Không tách được khung (`penalty_unchecked`) | Cho qua kèm dòng "Hệ thống chưa kiểm được khung của khoản này" | có | quyết định 17 |
| K23 | Bị cáo đang tạm giam mà quyết định không phải tù hoặc có án treo: lời tuyên phải có trả tự do | Mềm (chỉ đưa vào chỉ dẫn lời tuyên) | chưa | Điều 328 khoản 3–4 BLTTHS. Backlog nếu cần kiểm |

Cài đặt: `check_verdict(verdict, case, pack, mode="ai"|"user")`. K5–K7, K9 (phần mới), K17, K19, K21 chạy **chỉ khi `mode="user"`**, để không đổi số đo của các vai đã chạy (nguyên tắc Mục 11). Có nên áp cho nghị án AI không là câu hỏi Q10. `VerdictCheck` thêm `warnings` và mỗi mục có `{field, message, basis}`, để form hiện lỗi cạnh trường.

### 3.3 Luồng

1. Bước 10: `item:vao_nghi_an` (lời mẫu "Hội đồng xét xử vào phòng nghị án…"). Mục này phải làm trước.
2. `PUT /api/trials/{id}/decision` (body `{expected_version, decision}`): kiểm schema, chạy `check_verdict(mode="user")`, lưu `user_work.decision_draft` cùng kết quả kiểm, tăng `version`, trả `{draft, check, state}`. Không gọi LLM. Chỉ nhận ở bước 10, khi chưa chốt, `awaiting = user`. Khóa sinh đang giữ thì 409 `trial_busy`.
3. Tùy chọn `invite:y_kien_hoi_tham`: chỉ khi bản nháp hiện tại **không còn lỗi cứng**. 1 lời gọi. Kết quả lưu ở `user_work.assessor_opinions` và hiện trong `state.decision`. Không thành utterance, vì nghị án là bí mật (Điều 326) và diễn biến phiên tòa không có phần này. Sửa bản nháp sau đó không gọi lại AI; ý kiến được gắn nhãn "về bản nháp lúc …".
4. `decide` (qua `/turn`, SSE không có lượt AI): kiểm lại. Còn lỗi cứng thì 409 `trial_decision_invalid` kèm `errors`. Đạt thì lưu `verdict_json = {…Verdict, "source": "user", "extras": {...}, "assessor_opinions": {...}}`, đánh dấu `chot_quyet_dinh`. Không sửa được nữa (409 `trial_decision_locked`).
5. `advance:11`, rồi `prepare_pronouncement` (1 lời gọi) để có `state.decision.pronouncement_preview`. Người dùng đọc trước, rồi `pronounce`: ghi utterance `CHU_TOA` (`is_user: true`, `kind: speech`, cờ `system_drafted`), phiên `completed`, chạy tóm tắt biên bản (1 lời gọi) như vai KSV. Nếu lời tuyên bị guard chặn 2 lần thì tạm nghỉ như mọi lời dài, và `prepare_pronouncement` trở lại `allowed_actions`.

`state.decision` (chỉ `chu_toa`, bước 10–11): `{draft, check:{errors, warnings, flags}, locked, assessor_opinions, pronouncement_preview}`. Đây là quyết định **của chính người dùng**. Không vai nào khác có khóa này (test như quyết định 9).

### 3.4 Phương án C (sau, quyết định 16)

Dùng cùng form. Thêm `pronounce` có `text` (300–6.000 ký tự). Code đối chiếu lời tuyên với quyết định đã chốt **để phản hồi**: `missing_charge_citation`, các số tháng và số tiền khớp form, Rule 9 strict ở chế độ chỉ báo. 0 lời gọi. Không làm ở pha 2.

---

## 4. `verdict_json` và "phán quyết ẩn"

- **Hiện trạng (M1):** hồ sơ vụ án không có phán quyết. Phần ẩn của hồ sơ là `knobs` (khoản, lập trường, điểm tình tiết do code chọn) và thẻ nhân vật. `student_case_view` không trả ra hai phần này. `verdict_json` do AI tạo ở bước 10 (các vai khác), kèm `record_summary`. API không bao giờ trả `verdict_json`.
- **Đề xuất cho Chủ tọa: không dùng quyết định AI nào**, kể cả sau khi chốt. Lý do:
  - một quyết định AI để "so sánh" sẽ thành đáp án, trái nguyên tắc không chấm điểm và cùng lý do với quyết định 7 của Thư ký;
  - phương án B (AI đề xuất) đã bị loại;
  - không tốn lời gọi;
  - không có gì để lộ.
  Nếu nhóm luật muốn đối chiếu thì để backlog: nút riêng **sau khi `pronounce`**, nhãn "một cách quyết định tham khảo, không phải đáp án", thêm 1 lời gọi có thinking (Q8).
- **Bảo đảm không lộ, không có quyết định AI:**
  1. `_deliberate` không bao giờ chạy với `user_role = chu_toa`. Nhánh `tuyen_an` ném lỗi khi thiếu quyết định đã chốt. Test: đếm `call_type == "verdict"` = 0 trên cả phiên.
  2. `verdict_json` của phiên Chủ tọa chỉ được ghi bởi `decide`, và có `source = "user"`.
  3. `state.decision` chỉ chứa dữ liệu người dùng nhập, ý kiến Hội thẩm về bản nháp đó, và lời tuyên soạn từ quyết định đã chốt.
  4. Prompt ý kiến Hội thẩm không có `knobs` (`_case_block` chỉ có `draft`) và không có lời gọi nghị án. Hội thẩm không được nêu mức án hay số tháng của riêng mình (guard số).
- **Bước 11, ai đọc:** Chủ tọa (người dùng) tuyên, bằng lời hệ thống soạn từ quyết định của người dùng (phương án A). Điều 327 BLTTHS: "Chủ tọa phiên tòa hoặc một thành viên khác của Hội đồng xét xử đọc bản án". Phụ lục biên bản ghi rõ "Lời tuyên do hệ thống soạn từ quyết định của Chủ tọa (người học)".
- **Biên bản IV.1–IV.4:** xem Mục 7.

---

## 5. "Dùng lời mẫu"

- **Ở đâu:** `items[].template` trong `state.presiding`, đã thay tên đầy đủ. Bấm "Dùng lời mẫu" thì client điền ô nhập để người dùng sửa, hoặc gửi `item` không kèm `text` để server dùng nguyên lời mẫu. Biên bản ghi lời mẫu dưới tên Chủ tọa (11.4.5).
- **Sinh ra sao:** code thuần, file mới `backend/app/services/trial_presiding.py`, 0 lời gọi. Có cờ `TEMPLATES_REVIEWED = False` cho tới khi nhóm luật duyệt (quyết định 19). Dùng lại các câu sẵn có: `_TEMPLATES` (`ket_thuc_xet_hoi`, `ket_thuc_tranh_luan`, `vao_nghi_an`), `INVITATIONS`, `FALLBACK_QUESTIONS`, `attendance_report`, `identity_prefill`.
- **Danh sách:**

| Mục | Lời mẫu Chủ tọa (dựng từ) | Câu trả lời mẫu (0 lời gọi) |
|---|---|---|
| `khai_mac` | tên Tòa án, số quyết định đưa vụ án ra xét xử giả định, họ tên bị cáo, tội danh, điểm/khoản/Điều truy tố (`charge`) | — |
| `kiem_tra_can_cuoc` | "Đề nghị bị cáo cho biết họ tên…" (`FALLBACK_QUESTIONS`) | `identity_prefill` (lời bị cáo) |
| `kiem_tra_co_mat` | danh sách có mặt/vắng mặt (`attendance`), giới thiệu HĐXX, KSV, Thư ký, luật sư | — |
| `giai_thich_quyen` | quyền, nghĩa vụ của bị cáo (Điều 61), bị hại (62), người làm chứng (66), người có quyền lợi liên quan (65), chỉ cho người có mặt. **Chỉ nêu số Điều**, không chép điểm, khoản, vì nhóm luật duyệt câu chữ | — |
| `hoi_thay_doi` | câu hỏi theo Điều 302 | KSV, luật sư: `_TEMPLATES`; bị cáo: "Bị cáo không có đề nghị thay đổi…" |
| `cam_doan_nlc` | yêu cầu cam đoan, quyết định cách ly (Điều 304) | từng người làm chứng: "Tôi xin cam đoan khai báo trung thực." |
| `hoi_yeu_cau` (T) | câu hỏi theo Điều 305 | KSV, luật sư, bị cáo: "Không có yêu cầu." |
| `moi_cong_bo_cao_trang` | lời mời | KSV đọc nguyên văn cáo trạng (có sẵn) |
| `cong_bo_loi_khai_bi_hai` | "Do bị hại vắng mặt, Hội đồng xét xử công bố lời khai của bị hại trong giai đoạn điều tra: …" + `pretrial_statements[BI_HAI].summary` | — |
| `moi_*` (bước 4–9) | câu mời một dòng cho từng phần | (AI, xem 2.3) |
| `ket_thuc_xet_hoi` | câu hỏi "còn ai yêu cầu xét hỏi không" + câu kết thúc (Điều 318) | KSV, luật sư, bị cáo: "Không có yêu cầu xét hỏi thêm." |
| `tro_lai_xet_hoi` | "Xét thấy còn tình tiết chưa được làm sáng tỏ, Hội đồng xét xử quyết định trở lại việc xét hỏi." | — |
| `ket_thuc_tranh_luan` | `_TEMPLATES` | — |
| `vao_nghi_an` | `_TEMPLATES` | — |

- **Chi phí:** 0 lời gọi cho mọi lời mẫu và câu trả lời mẫu. Lời gọi chỉ phát sinh khi người dùng tự hỏi (`ask`, `remark` có người nhận, hoặc `kiem_tra_can_cuoc` tự viết) hay mời một phần AI (`invite`).
- **Thời điểm dựng:** khi dựng `state` (rẻ, xác định). Không lưu lời mẫu trong DB cho tới khi dùng.

---

## 6. Điều 323 — trở lại xét hỏi

- **Corpus:** Điều 323 BLTTHS: "Nếu qua tranh luận mà thấy còn có tình tiết vụ án chưa được hỏi, chưa được làm sáng tỏ thì Hội đồng xét xử phải quyết định trở lại việc xét hỏi. Xét hỏi xong phải tiếp tục tranh luận." Luật không giới hạn số lần; "1 lần mỗi phiên" là giới hạn của bản mô phỏng (quyết định 20). Điều 324 khoản 2 còn một trường hợp nữa: trở lại xét hỏi khi lời sau cùng có tình tiết mới quan trọng (backlog).
- **Điều kiện (đề xuất, M2):** chỉ ở bước 8, khi `awaiting = user`, `returned = false`, đã xong ít nhất 1 vòng đối đáp (đúng nghĩa "qua tranh luận"), và chưa làm `ket_thuc_tranh_luan`. Nếu chọn cho cả bước 6–7 (đúng câu chữ 11.4.6), thì về lại **bước đã rời**, không về thẳng bước 8, để không mất luận tội hay bào chữa.
- **Cơ chế:** hành động `return_to_questioning` (`text` hoặc lời mẫu, ghi `procedure_item = tro_lai_xet_hoi` ở bước 8):
  - Code đặt `returned = true`, `in_return = true`, `current_step = 5`, xóa bộ đếm của bước, `version + 1`.
  - Bước 5 thu gọn: `ask` (người dùng tối đa 3 câu), `invite:moi_ksv_hoi` và `invite:moi_ls_hoi` (mỗi lời mời tối đa 3 câu, đều T), `ket_thuc_xet_hoi` (B).
  - Ngoại lệ duy nhất của quy tắc "chỉ tiến 1 bước": khi `in_return` thì `advance` từ bước 5 có đích là 8 (`allowed_actions: advance:8`). Vào lại bước 8: `in_return = false`, bộ đếm về 0, bắt buộc lại ít nhất 1 vòng đối đáp ("phải tiếp tục tranh luận"), `tro_lai_xet_hoi` không còn.
  - Gọi `return_to_questioning` lần hai trả 409 `trial_return_used`; gọi ngoài điều kiện trả 409 `trial_return_not_allowed`.
- **Ảnh hưởng tới bước và hiển thị:** `state.presiding.in_return = true`; thanh tiến trình hiện "Bước 5 (trở lại xét hỏi)". Lời trong lúc trở lại có `step = 5`.
- **Biên bản:** câu quyết định trở lại xét hỏi nằm ở IV.3 (bước 8, nguyên văn). Các lời hỏi sau đó vào IV.2 theo `seq`. IV.2 thêm ghi chú cố định "Hội đồng xét xử quyết định trở lại việc xét hỏi (Điều 323 Bộ luật Tố tụng hình sự)." khi `returned`. Tóm tắt IV.2/IV.3 tự gồm các lời này vì chọn theo bước.
- **Chi phí:** +5–7 lời gọi (người dùng hỏi ≤ 3, KSV 1, luật sư 1, đối đáp lại 2), cao hơn ước tính +3–5 của 11.4.2 vì phải đối đáp lại.

---

## 7. Biên bản

- **III và IV:** lời thủ tục của Chủ tọa là lời người dùng, nguyên văn; lời mẫu ghi dưới tên Chủ tọa. Câu trả lời mẫu (bị cáo khai lý lịch, cam đoan) ghi như lời của người đó. Notice (`HE_THONG`) không vào biên bản. IV.1 (bước 3) và IV.4 (bước 9) giữ nguyên văn. IV.2/IV.3 là tóm tắt (1 lời gọi sau tuyên án, như KSV), hoặc nguyên văn nếu không đạt kiểm tra.
- **Ghi chú `DELIBERATION_NOTES`** (vào nghị án, tuyên án) giữ nguyên. Theo hướng dẫn (29) của mẫu, biên bản không chép phần quyết định.
- **Phụ lục "Lời tuyên án"** như hiện tại, thêm dòng "Lời tuyên do hệ thống soạn từ quyết định của Chủ tọa (người học)".
- **Phụ lục mới "Biên bản nghị án" (ngoài Mẫu 22-HS)**, chỉ vai `chu_toa`, dựng bằng code từ `verdict_json`, 0 lời gọi. Bố cục theo Điều 259 khoản 2 BLTTHS: (a) giờ, ngày, tên Tòa án; (b) họ tên Thẩm phán, Hội thẩm; (c) vụ án; (d) "kết quả biểu quyết … về từng vấn đề … quy định tại khoản 3 Điều 326, ý kiến khác (nếu có)":
  - vấn đề form có: điểm c (căn cứ kết tội, điểm/khoản/Điều), d (hình phạt, bồi thường, dân sự), e (án phí, xử lý vật chứng);
  - điểm a, b, đ, g, h ghi "Không xem xét trong phạm vi mô phỏng";
  - Hội thẩm `dong_y = false` thì ghi "Ý kiến thiểu số của Hội thẩm …: …" (quyết định 15);
  - nhận định của người dùng ghi nguyên văn.
  Không trái Điều 326, vì người đọc chính là người đã nghị án (11.4.5).
- **`GET /record` không gọi LLM:** giữ nguyên. Phụ lục nghị án dựng từ dữ liệu đã lưu.
- Lời tuyên vào phụ lục từ utterance bước 11 như hiện tại.

---

## 8. Thay đổi API, dữ liệu và từng file

### 8.1 API (sẽ thêm API-CONTRACT Mục 5.4 khi code)

| Thay đổi | Chi tiết |
|---|---|
| `config.user_roles` | thêm `chu_toa` (`ENABLED_USER_ROLES`) ở commit cuối của pha 2 |
| `POST /turn` | `action` thêm `item`, `ask`, `invite`, `remark`, `return_to_questioning`, `decide`, `prepare_pronouncement`, `pronounce`; trường mới `item`. Vai khác gửi các action này: 409 `trial_action_not_allowed` |
| `PUT /api/trials/{id}/decision` | mới (3.3). Body `{expected_version, decision}`, `extra="forbid"`. Trả `{draft, check, state}`. Lỗi: 409 `trial_not_presiding`, `trial_decision_locked`, `trial_busy`, `trial_version_mismatch`, `trial_action_not_allowed` (sai bước); 422 schema |
| `state` | thêm `presiding` và `decision` (chỉ `chu_toa`, mọi vai khác `null`). `text_limits` của vai này `null` |
| Mã 409 mới | `trial_procedure_incomplete` (+`missing_items`), `trial_item_not_available`, `trial_item_done`, `trial_return_not_allowed`, `trial_return_used`, `trial_decision_invalid` (+`errors`), `trial_decision_locked`, `trial_decision_missing`, `trial_not_presiding`, `trial_pronouncement_missing`. Hết trần câu hỏi hoặc phát biểu: dùng lại `trial_turn_limit` |
| `utterance` | `speaker_id` có thể là `HE_THONG` (notice ở phiên Chủ tọa); thêm `procedure_item` (null với vai khác) |
| `GET /record` | `appendix` thêm mục "Biên bản nghị án" (chỉ `chu_toa`); IV.2 có `notes` khi đã trở lại xét hỏi |

### 8.2 Dữ liệu

Không migration. Check `user_role` (0012/0013) đã có `chu_toa`. Dùng:
- `user_work.preside`, `.decision_draft`, `.decision_check`, `.assessor_opinions`, `.pronouncement_draft` (ghi cùng version, Mục 2.1);
- `verdict_json` có thêm khóa `source`, `extras`, `assessor_opinions` cạnh `record_summary`; `build_context` tách ra như `record_summary`;
- `utterances.procedure_item` (cột 0013).

### 8.3 Từng file backend

| File | Thay đổi |
|---|---|
| `services/trial_state_machine.py` | `PRESIDING_ROLE`; `SlotKind` thêm `preside`; `active_slots` trả một slot `preside` mỗi bước 2–11 cho `chu_toa` (bước 1 giữ slot Thư ký mẫu); `PresideState`/`Job` trong `SessionState`; `apply_user_action` rẽ sang `_apply_preside` (item, ask, invite, remark, return, decide, pronounce, advance có ngoại lệ 5→8); `allowed_actions`, `complete_ai_turn` theo job; tắt `detect_skip_request` cho vai này |
| `services/trial_presiding.py` (mới) | danh mục mục thủ tục theo bước (khóa, B/T, kiểu, điều kiện `requires`, thứ tự, căn cứ), lời mẫu, câu trả lời mẫu, `missing_items`, `presiding_view`, mẫu `usurps_presiding`, dựng phụ lục nghị án |
| `services/trial_turn_service.py` | dispatch theo job (2.3); instruction `answer_question_presiding`; lời gọi ý kiến Hội thẩm và schema; `pronounce_draft` không qua `_deliberate`; cờ đo `usurps_presiding`, mẫu `speaks_for_student` cho `CHU_TOA`; ghi `procedure_item` |
| `services/trial_verdict_guard.py` | `mode="user"`; K5–K7, K9, K11, K13–K14, K16–K21; `VerdictCheck.warnings`; mỗi lỗi có `field`, `basis` |
| `services/trial_session_service.py` | đọc/ghi `user_work.preside` cho `chu_toa`; `state_fields` thêm `user_work`; `verdict_json` thêm `source`/`extras`; `state_out` thêm `presiding`, `decision` |
| `services/trial_repository.py` | `procedure_item` trong insert/list; docstring: ngoại lệ ghi `user_work` cùng version cho Chủ tọa; repo trong bộ nhớ cũng vậy |
| `services/trial_record.py` | phụ lục "Biên bản nghị án"; ghi chú IV.2 khi đã trở lại xét hỏi; dòng "Lời tuyên do hệ thống soạn…" |
| `services/trial_record_summary.py` | không đổi logic; kiểm lại nhãn `HE_THONG` và lời `is_user` của Chủ tọa trong nguồn tóm tắt |
| `services/trial_config.py` | hằng số: `CHAIR_STEP4_QUESTIONS = 10`, `CHAIR_REMARKS_PER_STEP = 5`, `CHAIR_RETURN_QUESTIONS = 3`, `CHAIR_DEBATE_MAX_ROUNDS = 2`, giới hạn độ dài |
| `services/trial_legal_pack.py` | `slice_for_slot` cho `assessor` (= lát cắt `nghi_an`) và `pronounce_draft` (= `tuyen_an`) |
| `models/trial.py` | `UserRole` thêm `chu_toa`; `DecisionExtras`, `ExhibitDisposition`; `ChairDecision` |
| `models/trial_api.py` | `TrialTurnRequest` (action, `item`); `TrialPresidingOut`, `TrialDecisionOut`, `TrialDecisionRequest`; `TrialStateOut` thêm 2 trường; `TrialUtteranceOut.procedure_item` |
| `api/trials.py` | xử lý action mới; `PUT /decision`; notice dùng `HE_THONG` ở phiên Chủ tọa; `_record_response` truyền cờ Chủ tọa; 409 kèm `missing_items`/`errors` |
| `prompts/trial_prompts.py` | dòng quy tắc của vai Chủ tọa (câu ở 11.4.2); instruction trả lời không có `CHU_TOA`; Hội thẩm hỏi; KSV/luật sư hỏi tối đa 3 câu; prompt và schema ý kiến Hội thẩm; dòng vật chứng và án phí cho `tuyen_an` |
| `trial_rule9.py`, `trial_case_*`, `trial_knobs.py`, `trial_clerk.py`, `trial_defendant.py` | không đổi (chỉ import `identity_prefill`, `INVITATIONS`, `FALLBACK_QUESTIONS`) |
| `evaluation/run_trial_chu_toa_e2e.py` (mới) | script đo pha 2 (offline, không tài khoản test), theo mẫu `run_trial_bi_cao_e2e.py` |
| Tài liệu | API-CONTRACT 5.4 + bảng 409; THIET-KE 11.14 (báo cáo chặng) |

---

## 9. Kiểm thử và đo

### 9.1 Unit test (LLM giả, chạy trong CI)

`tests/test_trial_presiding.py`, `tests/test_trial_presiding_routes.py`, `tests/test_trial_chair_decision.py`:
- **Danh mục:** mỗi bước đúng mục theo hình vụ (có/không người làm chứng, bị hại vắng mặt, có người có quyền lợi liên quan); `advance` thiếu mục B trả `trial_procedure_incomplete` đúng `missing_items`; `khai_mac` phải trước; `ket_thuc_*` phải sau cùng; mục đã làm trả `trial_item_done`; mục ngoài bước trả `trial_item_not_available`.
- **Lời mẫu:** `item` không có `text` ghi đúng lời mẫu, `is_user`, `procedure_item`; câu trả lời mẫu 0 lời gọi (đếm lời gọi của LLM giả); căn cước tự viết thì 1 lời gọi.
- **Hỏi, mời:** mỗi `ask` đúng 1 lời gọi với enum chỉ có người được hỏi; trần 10 câu ở bước 4 và 5 phát biểu mỗi bước; `invite` không chạy hai lần; đối đáp 2 bài, vòng 2 thêm 2 bài; bước 9 sau lời sau cùng không hỏi được bị cáo.
- **Không nói thay:** không utterance AI nào có `CHU_TOA`; notice ở phiên Chủ tọa có `HE_THONG`; trên cả phiên không có lời gọi `verdict`; `tuyen_an` thiếu quyết định thì báo lỗi, không nghị án AI; bộ phát hiện nhảy cóc tắt (câu "chuyển sang tuyên án" được ghi, state không đổi).
- **`usurps_presiding`:** 6 ca dương, 6 ca âm (gồm "đề nghị Hội đồng xét xử…" của KSV, câu hỏi của Hội thẩm khi được mời); chỉ là cờ, không sinh lại.
- **Điều 323:** chỉ ở bước 8 sau ≥ 1 vòng; lần hai trả `trial_return_used`; bước 5 thu gọn với trần 3; `advance:8`; bước 8 bắt buộc đối đáp lại; biên bản có ghi chú ở IV.2.
- **Quyết định:** mỗi luật K1–K21 có ca đạt và ca lỗi (cứng chặn `decide`, mềm vẫn chốt); K6 cho qua Điều 171 khoản 1 + Điều 54 + cải tạo không giam giữ; `penalty_unchecked` cho qua; chế độ `ai` của `check_verdict` không đổi kết quả với fixture cũ (hồi quy); `PUT /decision` khi khóa sinh đang giữ trả `trial_busy`; chốt rồi không sửa được.
- **Lộ dữ liệu:** `GET /{id}` và `state` của 5 vai còn lại không có `presiding`, `decision`; phiên Chủ tọa không có `role_brief`; `verdict_json` không bao giờ có trong response; `knobs` không có trong response.
- **Biên bản:** phụ lục nghị án đúng Điều 259 khoản 2, ý kiến thiểu số khi Hội thẩm `dong_y = false`; `GET /record` 0 lời gọi.
- **Hồi quy:** 239 test hiện có vẫn xanh; số lời gọi của phiên KSV, Bị cáo bằng LLM giả không đổi.

### 9.2 Đo với Gemini thật (pha 2)

Ước tính lời gọi mỗi phiên (gồm tạo vụ và tóm tắt biên bản):

| Kịch bản | Lời gọi | Token vào | Token ra (+thinking) |
|---|---|---|---|
| Tối thiểu: lời mẫu, 1 câu hỏi bước 4, không mục T | ~14–16 | ~170–200K | ~12K + ~4K |
| Điển hình: 3–4 câu hỏi, Hội thẩm hỏi, ý kiến Hội thẩm, 2 phát biểu có người nhận | ~19–22 | ~240–280K | ~15K + ~5K |
| Đủ mục T + vòng 2 + trở lại xét hỏi | ~30–33 | ~380–420K | ~20K + ~5K |
| Trần lý thuyết (hỏi hết trần, phát biểu hết trần) | ~60–70 | ~800K+ | |

Cơ sở tính: ~12–13K token vào mỗi lời gọi (đo R1: ~11,3K; R3: ~13K); thinking chỉ ở tạo vụ và tuyên án (không có nghị án AI). So với 11.4.2 (26–31 lời gọi): thấp hơn nhờ câu trả lời mẫu ở bước 2 và không có lời gọi nghị án.

**Số thao tác của người dùng:**
- tối thiểu ~33: bước 1: 1 · bước 2: 6+1 · bước 3: 2 · bước 4: 2–3 · bước 5: 4 · bước 6: 2 · bước 7: 2–3 · bước 8: 3 · bước 9: 2 · bước 10: 3–4 cộng điền form · bước 11: 2;
- điển hình ~40–45 (Bị cáo: 13–15).

**Kế hoạch đo, trần cứng 80 lời gọi** (dừng ngay khi gặp 402/429; ước tính in ra trước khi chạy; mỗi phiên ghi lời gọi và token thật):
1. Phiên A, seed mới, Điều 173, có bị hại, 1 người làm chứng: toàn lời mẫu, 3 câu hỏi, Hội thẩm hỏi, ý kiến Hội thẩm, quyết định có tội, tù trong khung. ~20.
2. Phiên B, Điều 134, bị hại vắng: tự diễn đạt, 6 câu hỏi (2 câu tiền đề sai), 2 phát biểu có người nhận, vòng 2, trở lại xét hỏi (3 câu + 2 lời mời + đối đáp lại), án treo. ~32.
3. Lời tuyên từ ngữ cảnh bước 10 đã lưu của phiên A: không có tội; khoản 2 + Điều 54 (sàn khoản 1); cải tạo không giam giữ; khoản nhẹ hơn; nhận định có câu kiểu injection. ~5 + ~2 sinh lại.
4. Dự phòng sinh lại và tạm nghỉ: ~10. **Tổng ~69, trần 80.** Nếu phiên A vượt 30 thì phiên B dừng ở bước 8 (bỏ phần đo tuyên án nếu tổng chạm 70).

Chỉ số ghi lại:
- lời gọi, token, độ trễ theo loại;
- số lần guard từ chối, số lần tạm nghỉ;
- `usurps_presiding` và `speaks_for_student`: lưu nguyên văn **ngoài repo**, phân loại tay đúng/oan;
- số thao tác của người dùng script;
- K-check trên quyết định của script; biên bản đủ I–IV và hai phụ lục;
- 0 lời gọi `verdict`; 0 utterance AI mang `CHU_TOA`.

---

## 10. Câu hỏi mở

Ký hiệu: **[ND]** người dùng quyết; **[NL]** nhóm luật; **[ND+NL]** cả hai. Mọi câu đều có mặc định để pha 2 làm tiếp.

| # | Câu hỏi | Đề xuất mặc định | Lý do |
|---|---|---|---|
| Q1 [ND] | Lưu trạng thái điều hành ở `user_work.preside` (ghi cùng version) hay thêm migration `preside_state`? | `user_work`, không migration | Cột đã có; ghi cùng version là đủ an toàn; tránh chạy tay migration |
| Q2 [ND] | ~33–45 thao tác mỗi phiên. Có thêm nút "Làm các mục bắt buộc còn lại của bước bằng lời mẫu" (một thao tác, ghi từng mục) không? | Không ở pha 2; đo số thao tác thật trước | Thiết kế đặt mỗi mục là một cú bấm; gộp làm giảm giá trị học tập |
| Q3 [ND] | Điều 323: chỉ ở bước 8 (bảng 11.4.1, giao diện 11.4.7) hay ở bước 6–8 (11.4.6)? | Chỉ bước 8, sau ≥ 1 vòng đối đáp | Về thẳng bước 8 từ bước 6–7 sẽ mất luận tội hoặc bào chữa (M2). Nếu chọn 6–8 thì về lại bước đã rời |
| Q4 [ND] | Có cần trần số lời gọi AI mỗi phiên Chủ tọa (ví dụ 45, quá thì chỉ còn mục không tốn lời gọi) không? | Chưa; giữ trần theo quyết định 13; đo ở pha 2 | Trần lý thuyết ~60–70 lời gọi chỉ xảy ra khi cố tình hỏi hết trần |
| Q5 [ND+NL] | Bước 2: câu trả lời mẫu bằng code (0 lời gọi) thay cho 3 lời gọi AI ở bảng 11.4.1? | Có | Câu trả lời mang tính thủ tục, cố định; tiết kiệm 3 lời gọi; không có rủi ro bịa |
| Q6 [NL] | Thêm mục Điều 305 (hỏi yêu cầu triệu tập thêm người làm chứng, vật chứng, hoãn phiên tòa khi có người vắng mặt)? B hay T? | Thêm, mức T cho tới khi duyệt | Luật dùng chữ "phải hỏi"; danh mục đã chốt chưa có mục này (M3) |
| Q7 [ND+NL] | Ý kiến Hội thẩm: góp ý **trên bản nháp** của người dùng (không tự nêu mức án), hay biểu quyết độc lập trước như Điều 326 khoản 1? | Góp ý trên bản nháp | Tránh "mỏ neo" và đáp án AI (lý do loại phương án B); quyết định 15 đã nói Hội thẩm không biểu quyết đè. Ghi rõ chỗ lệch thứ tự so với luật |
| Q8 [ND] | Có cho xem một quyết định tham khảo của AI **sau khi tuyên án** không? | Không (backlog) | Sẽ thành đáp án; cùng lý do với quyết định 7 |
| Q9 [NL] | Điều 298 khoản 2: có cho xử theo khoản **nặng hơn** trong cùng Điều không? (Văn bản không có chữ "nhẹ hơn".) | Giữ chặn khoản nặng hơn | Code và thiết kế 5.2 đang chặn; chặt hơn thì an toàn hơn cho bản mô phỏng |
| Q10 [ND] | Các luật mới K5–K7, K9 (Điều 54 sàn và khoản 3, tù ≥ 03 tháng, phạt tiền tối thiểu): chỉ cho quyết định của người dùng, hay áp cả cho nghị án AI của các vai khác? | Chỉ người dùng ở pha 2; áp cho AI ở chặng sau cùng một lần đo | Nguyên tắc Mục 11: không đổi số đo của vai đã chạy; K5 có thể làm tăng số lần sinh lại của nghị án AI |
| Q11 [NL] | K16 (bồi thường không vượt yêu cầu): cứng hay mềm? Corpus không có căn cứ trực tiếp | Mềm cho tới khi nhóm luật xác nhận; một hằng số đổi sang cứng | Quyết định 18 nói "có, nhóm luật xác nhận"; corpus không đủ |
| Q12 [NL] | Đối đáp tối đa 2 vòng có cần chú thích "giới hạn của mô phỏng" vì Điều 322 khoản 3 cấm Chủ tọa hạn chế thời gian tranh luận không? | Có, một dòng trong `basis`/nhãn của `vong_2` | Tránh dạy sai rằng Chủ tọa được giới hạn tranh luận |
| Q13 [NL] | Câu chữ toàn bộ lời mẫu Chủ tọa, câu trả lời mẫu, câu "Không xem xét trong phạm vi mô phỏng" của phụ lục nghị án, bảng điểm định khung cho K13 | Code soạn nháp, `reviewed: false` (quyết định 19) | — |
| Q14 [NL] | Vật chứng: 4 cách xử lý (trả lại, tịch thu sung ngân sách, tịch thu tiêu hủy, lưu hồ sơ) có đủ cho các vụ 171/173/174/134 không? | Dùng 4 cách này | Điều 106 khoản 2–3 BLTTHS, Điều 47 BLHS |
| Q15 [NL] | Án phí: chỉ chọn "bị cáo chịu / không chịu", không có số tiền (mức án phí không có trong corpus) — được không? | Được; lời tuyên ghi "theo quy định của pháp luật" | Corpus không có Nghị quyết 326/2016/UBTVQH14 |
| Q16 [ND] | Ý kiến Hội thẩm có vào diễn biến phiên tòa (utterance) không? | Không; chỉ ở `state.decision` và phụ lục nghị án | Nghị án là bí mật, diễn ra trong phòng nghị án (Điều 326 khoản 1) |

---

## 11. Rủi ro và việc để sau

### 11.1 Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| **Phiên dài** (~33–45 thao tác) khiến người dùng bỏ dở | Cao | Lời mẫu một cú bấm; checklist; đo ở pha 2; Q2 |
| **Chi phí** phụ thuộc người dùng hỏi bao nhiêu (trần lý thuyết ~60–70 lời gọi) | Vừa | Trần theo quyết định 13; câu trả lời thủ tục 0 lời gọi; không có nghị án AI; hạn mức 5 vụ/ngày và trần toàn hệ thống giữ nguyên; Q4 |
| **Lộ hoặc mỏ neo phán quyết**: Hội thẩm hay lời tuyên "gợi ý" quyết định khác | Vừa | Không có quyết định AI; Hội thẩm chỉ góp ý trên bản nháp, guard số chặn mức án lạ; lời tuyên soạn **sau** khi chốt, từ chính quyết định của người dùng |
| **Bắt oan của guard**: `usurps_presiding` gắn cờ lời bình thường ("đề nghị Hội đồng xét xử…") | Vừa | Chỉ đo; phân loại tay; bật cứng khi bắt oan ≤ 2% (quyết định 14) |
| **Bắt oan của form**: chặn quyết định hợp pháp (ví dụ Điều 54 khoản 3, M6) | Vừa | K6 nới đúng luật; `penalty_unchecked` cho qua; luật thiếu căn cứ (K16) để mềm |
| Lời tuyên do AI viết trơn tru che một quyết định yếu (11.4.4) | Thấp–vừa | Phụ lục ghi rõ "hệ thống soạn"; phương án C sau |
| Bước lùi đầu tiên của máy trạng thái (Điều 323) gây lỗi trạng thái | Vừa | Chỉ một ngoại lệ (5→8, cờ `in_return`), có test riêng; `expected_step` vẫn chặn lệch |
| Ghi `user_work` cùng version làm 409 nhiều hơn khi lưu nháp | Thấp | Chỉ khóa khi AI đang chạy; client lấy `state` mới trong response |
| Người dùng gõ nhận định hoặc câu hỏi kiểu injection | Thấp | Bọc `<<<LOI_NGUOI_HOC>>>`, che Điều; quyết định có cấu trúc không đổi được bằng văn bản; Rule 9 strict ở lời tuyên |

### 11.2 Để sau (backlog)

- Phương án C: tự viết lời tuyên (quyết định 16).
- Hình phạt bổ sung (ví dụ khoản 5 Điều 173/174), biện pháp tư pháp khác ngoài vật chứng và bồi thường.
- Kiểm và tuyên trả tự do hoặc tạm giam sau tuyên án (Điều 328–329).
- Trở lại xét hỏi sau lời sau cùng (Điều 324 khoản 2); trở lại xét hỏi ở bước 6–7 (nếu Q3 chọn).
- Áp K5–K7, K9 cho nghị án AI (Q10).
- Bảng điểm định khung để K13 thành kiểm chắc chắn.
- Quyết định tham khảo của AI sau khi tuyên án (Q8).
- Nút gộp lời mẫu (Q2), trần lời gọi mỗi phiên (Q4).
- KSV rút truy tố, kết luận tội nhẹ hơn (Điều 319, 325); hoãn phiên tòa thật (Điều 297).
- Giao diện Chủ tọa (chặng frontend, theo 11.4.7 và API-CONTRACT 5.4).

---

## Phụ lục A. Đối chiếu corpus

Nguồn: `ingestion/chunks.json`, `source_document` = `Bộ luật TTHS.pdf` (BLTTHS) và `Văn bản hợp nhất BLHS 2015.pdf` (BLHS). Đọc bằng script ở thư mục tạm, không ghi gì vào repo.

| Quy tắc dùng trong kế hoạch | Điều, khoản | Trích ngắn |
|---|---|---|
| Khai mạc, đọc quyết định đưa vụ án ra xét xử | BLTTHS 301 kh.1 | "Thẩm phán chủ tọa phiên tòa khai mạc phiên tòa và đọc quyết định đưa vụ án ra xét xử" |
| Kiểm tra có mặt, lý lịch, phổ biến quyền | BLTTHS 301 kh.3 | "kiểm tra lý lịch, phổ biến quyền và nghĩa vụ của họ" |
| Hỏi đề nghị thay đổi người tiến hành tố tụng | BLTTHS 302 | "Chủ toạ phiên tòa phải hỏi Kiểm sát viên và những người tham gia tố tụng … có đề nghị thay đổi" |
| Cam đoan, cách ly người làm chứng | BLTTHS 304 kh.1–2 | "yêu cầu người làm chứng phải cam đoan khai trung thực" |
| Hỏi yêu cầu chứng cứ, hoãn phiên tòa (M3) | BLTTHS 305 | "phải hỏi xem có ai yêu cầu hoãn phiên tòa hay không" |
| Công bố cáo trạng | BLTTHS 306 | "Kiểm sát viên công bố bản cáo trạng" |
| Trình tự xét hỏi, mời Hội thẩm, KSV, người bào chữa hỏi | BLTTHS 307 kh.2 | "chủ tọa phiên tòa hỏi trước sau đó quyết định để Thẩm phán, Hội thẩm, Kiểm sát viên, người bào chữa … hỏi" |
| Công bố lời khai khi vắng mặt | BLTTHS 308 kh.2 đ.d | "Người được xét hỏi vắng mặt hoặc đã chết" |
| Kết thúc xét hỏi | BLTTHS 318 | "hỏi Kiểm sát viên, bị cáo, người bào chữa … có yêu cầu xét hỏi vấn đề gì nữa không" |
| Trình tự tranh luận | BLTTHS 320 kh.1–3 | luận tội; "bị cáo … có quyền bổ sung ý kiến bào chữa"; bị hại trình bày |
| Không hạn chế thời gian tranh luận (M13) | BLTTHS 322 kh.3 | "Chủ toạ phiên tòa không được hạn chế thời gian tranh luận" |
| Trở lại xét hỏi | BLTTHS 323 | "Hội đồng xét xử phải quyết định trở lại việc xét hỏi. Xét hỏi xong phải tiếp tục tranh luận" |
| Kết thúc tranh luận; không hỏi khi nói lời sau cùng | BLTTHS 324 kh.1–2 | "chủ tọa phiên tòa tuyên bố kết thúc tranh luận"; "Không được đặt câu hỏi khi bị cáo nói lời sau cùng" |
| Nghị án, biểu quyết, ý kiến thiểu số | BLTTHS 326 kh.1 | "Hội thẩm biểu quyết trước, Thẩm phán biểu quyết sau cùng"; "Người có ý kiến thiểu số có quyền trình bày ý kiến của mình bằng văn bản" |
| Căn cứ nghị án | BLTTHS 326 kh.2 | "chỉ được căn cứ vào những chứng cứ, tài liệu đã được thẩm tra tại phiên tòa" |
| Vấn đề phải giải quyết khi nghị án | BLTTHS 326 kh.3 đ.a–h | c) căn cứ kết tội, điểm khoản điều; d) hình phạt, bồi thường; e) "Án phí hình sự, án phí dân sự; xử lý vật chứng" |
| Tuyên án | BLTTHS 327 | "Chủ tọa phiên tòa hoặc một thành viên khác của Hội đồng xét xử đọc bản án" |
| Biên bản nghị án | BLTTHS 259 kh.1–2 | "Kết quả biểu quyết … về từng vấn đề … quy định tại khoản 3 Điều 326 …, ý kiến khác (nếu có)" |
| Nội dung bản án (nhận định, quyết định, án phí, kháng cáo) | BLTTHS 260 kh.2 đ.d, g | "Nhận định của Hội đồng xét xử phải phân tích những chứng cứ…"; "về án phí và quyền kháng cáo" |
| Giới hạn xét xử (M5) | BLTTHS 298 kh.1–3 | "theo khoản khác với khoản mà Viện kiểm sát đã truy tố trong cùng một điều luật" |
| Thời hạn kháng cáo | BLTTHS 333 kh.1 | "15 ngày kể từ ngày tuyên án" |
| Xử lý vật chứng | BLTTHS 106 kh.1–3 | "do Hội đồng xét xử quyết định nếu vụ án đã đưa ra xét xử"; tịch thu, trả lại |
| Án phí | BLTTHS 135 kh.2, 136 kh.2–3 | "Án phí do người bị kết án hoặc Nhà nước chịu" |
| Khởi tố theo yêu cầu bị hại (Điều 134 kh.1) | BLTTHS 155 kh.1 | "khoản 1 các điều 134, …" |
| Dân sự trong vụ án hình sự | BLTTHS 30 | "được tiến hành cùng với việc giải quyết vụ án hình sự" |
| Trả tự do sau tuyên án | BLTTHS 328 kh.3–4 | "hình phạt không phải là hình phạt tù"; "được hưởng án treo" |
| Phân loại tội phạm | BLHS 9 kh.1 | ít nghiêm trọng ≤ 03 năm; nghiêm trọng đến 07 năm |
| Phạt tiền | BLHS 35 kh.1, 3 | "không được thấp hơn 1.000.000 đồng" |
| Cải tạo không giam giữ | BLHS 36 kh.1 | "từ 06 tháng đến 03 năm đối với người phạm tội ít nghiêm trọng, phạm tội nghiêm trọng" |
| Tù có thời hạn | BLHS 38 kh.1 | "mức tối thiểu là 03 tháng và mức tối đa là 20 năm" |
| Biện pháp tư pháp, tịch thu, trả lại, bồi thường | BLHS 46, 47 kh.1–2, 48 kh.1 | "không tịch thu mà trả lại cho chủ sở hữu"; "bồi thường thiệt hại vật chất đã được xác định" |
| Căn cứ quyết định hình phạt | BLHS 50 kh.1 | "nhân thân người phạm tội, các tình tiết giảm nhẹ và tăng nặng" |
| Tình tiết giảm nhẹ | BLHS 51 kh.1–3 | kh.2 "phải ghi rõ lý do giảm nhẹ"; kh.3 định khung không là giảm nhẹ |
| Tình tiết tăng nặng | BLHS 52 kh.1–2 | "dấu hiệu định tội hoặc định khung … không được coi là tình tiết tăng nặng" |
| Dưới mức thấp nhất của khung | BLHS 54 kh.1, 3 | "phải trong khung hình phạt liền kề nhẹ hơn"; "chuyển sang một hình phạt khác thuộc loại nhẹ hơn" |
| Miễn hình phạt (ngoài phạm vi) | BLHS 59 | "thuộc trường hợp quy định tại khoản 1 và khoản 2 Điều 54" |
| Án treo | BLHS 65 kh.1 | "xử phạt tù không quá 03 năm"; "thời gian thử thách từ 01 năm đến 05 năm" |
| Khung của 4 tội (khoản 1–2) | BLHS 173, 174 (kh.1: cải tạo không giam giữ đến 03 năm hoặc tù 06 tháng–03 năm; kh.2: tù 02–07 năm); 171 (kh.1: tù 01–05 năm; kh.2: 03–10 năm); 134 (kh.1: cải tạo không giam giữ đến 03 năm hoặc tù 06 tháng–03 năm; kh.2: tù 02–06 năm) | Không khoản nào trong số này có phạt tiền là hình phạt chính; phạt tiền chỉ là hình phạt bổ sung ở khoản 5 (Điều 173, 174, 171) |

**Corpus không đủ:**
- Mức án phí: Nghị quyết 326/2016/UBTVQH14, không có trong corpus.
- Điều kiện chi tiết cho hưởng án treo: Nghị quyết 02/2018/NQ-HĐTP, không có trong corpus.
- Nguyên tắc bồi thường không vượt yêu cầu: Bộ luật Dân sự, Bộ luật Tố tụng dân sự, không có trong corpus; BLDS chỉ được nhắc tên ở vài chỗ.
- Mẫu bản án và mẫu biên bản nghị án của NQ 05/2017: chỉ có danh mục mẫu, không có nội dung phụ lục.
- Giới thiệu thành phần HĐXX khi khai mạc: không có quy định riêng trong 301–305; đây là thực tiễn, lời mẫu đánh dấu chờ nhóm luật duyệt.
- Thủ tục người dưới 18 tuổi: Chương XXVIII BLTTHS đã bãi bỏ, luật thay thế không có trong corpus (đã loại khỏi phạm vi từ trước).
