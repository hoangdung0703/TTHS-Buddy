---
name: gemini-live-run
description: Dùng trước mọi lần chạy có gọi Gemini thật (e2e thật, bench, probe, đo trước/sau) và khi viết hoặc sửa script gọi LLM thật.
---

# Chạy Gemini thật an toàn và đo được

Số dư Gemini là **trả trước và dùng chung** cho Chat, Vở ghi, Phiên tòa. Hết số dư (402) là hỏng cả ba trên production.

## Trước khi chạy
- Mặc định **0 lời gọi**. Chỉ chạy khi prompt cho phép và nêu trần. Không có trần thì hỏi.
- **Ước lượng** số lời gọi mỗi phiên và tổng, ghi vào báo cáo trước khi chạy.
- Thử trước bằng **LLM giả** (fake). Chỉ dùng Gemini thật cho phần cần số đo thật.
- Chạy thử script với 0 lời gọi (kiểm tham số, đường dẫn đầu ra) trước lần chạy thật. Đã từng có lần chạy hỏng vì zsh tách tham số sai.

## Trong script
- **Bộ đếm lời gọi với trần cứng** nằm trong code; chạm trần thì dừng và vẫn lưu kết quả đã có.
- **Breaker**: dừng sau 3 lần tạm nghỉ hoặc lỗi liên tiếp.
- Gặp **402 hoặc 429: dừng ngay**, không vòng thử lại.
- Không in nội dung phiên ra console.
- Lưu đầu ra thô (lời thoại, câu bị guard bắt, quyết định nghị án) vào **thư mục tạm ngoài repo**. Không commit, không in. Lưu đủ lời thoại để có thể chạy lại guard offline sau này.
- Tài khoản test nếu cần: tạo qua Admin API với tên `tthsdiag-*` và xóa khi xong; hoặc chạy in-process không cần tài khoản.

## Thiết kế đo
- So sánh trước/sau thì **cố định cấu hình vụ án** (tội danh, khoản, seed, knobs; dùng lại cùng một vụ đã sinh nếu được) và cùng số phiên. Ghi rõ phần nào vẫn ngẫu nhiên.
- Dùng lại script có sẵn trong `backend/evaluation/` (ví dụ `run_trial_guard_bench.py`, các `run_trial_*_e2e.py`) trước khi viết script mới.
- Số liệu mỗi phiên:
  - lời gọi, token vào / ra / thinking;
  - số lần guard loại và sinh lại **theo từng lý do** (Rule 9, từng mã verdict guard, money guard, name, khác);
  - cảnh báo mềm, tạm nghỉ, breaker;
  - độ trễ trung vị và p90;
  - với vai có người dùng: số thao tác người dùng.

## Sau khi chạy
- Với mỗi lần guard bắt hoặc mỗi cờ đo: tự đọc nguyên văn ở thư mục ngoài repo, phân loại **bắt đúng / bắt oan**, và nhóm lý do.
- Báo cáo chỉ ghi **số lượng và nhóm lý do**, không chép nội dung phiên.
- Mẫu nhỏ thì nói rõ là mẫu nhỏ; không kết luận tỉ lệ từ 1-2 phiên.

## Báo cáo
- Ước lượng và thực tế số lời gọi; có gặp 402/429 không.
- Bảng số liệu theo phiên (trước/sau nếu có).
- Phân loại các lần bắt (đúng/oan, nhóm lý do).
- Đường dẫn thư mục dữ liệu đo ngoài repo.
