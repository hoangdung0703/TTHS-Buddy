---
name: legal-citation-check
description: Dùng khi viết, sửa hoặc kiểm bất kỳ nội dung nào có nêu Điều, khoản, điểm, mức hình phạt, thời hạn hay thủ tục của BLTTHS/BLHS: chú giải, câu mẫu, prompt, luật kiểm (guard, form quyết định), test, tài liệu, báo cáo.
---

# Đối chiếu điều luật với corpus

Đây là ứng dụng học luật: một số Điều sai là lỗi nội dung, không phải lỗi nhỏ. Mọi khẳng định pháp lý phải có câu luật trong corpus làm bằng chứng.

## Nguồn
- **Chỉ dùng `ingestion/chunks.json`** (gitignored, có trên máy). Đọc cấu trúc file trước (các trường như văn bản nguồn, số Điều) rồi mới tìm. Hiện là một mảng JSON các chunk, trường chính: `source_type` (`legal_text` hoặc `academic_reference`), `source_document` (tên PDF), `law_version` (tên văn bản, ví dụ BLTTHS hay BLHS; `null` với `academic_reference`), `dieu_number` và `khoan_number` (chuỗi, có thể `null`), `dieu_title`, `chuong_number`, `chuong_title`, `chunk_text`.
- **Không dựa vào trí nhớ**, kể cả khi "chắc chắn".
- Phiên bản: BLTTHS 2015 (sửa đổi 2021) và BLHS trong corpus. Corpus có chú thích của Luật 99/2025/QH15 nhưng **không chắc đã hợp nhất đủ** các sửa đổi; nếu khẳng định phụ thuộc vào luật sửa đổi này thì ghi rõ.
- Đã biết **corpus không đủ** cho: biểu án phí (NQ 326/2016/UBTVQH14), điều kiện chi tiết của án treo (NQ 02/2018/NQ-HĐTP), bồi thường không vượt yêu cầu (BLDS, BLTTDS), mẫu bản án và mẫu biên bản nghị án (NQ 05/2017/NQ-HĐTP).

## Cách đối chiếu
1. Tách nội dung thành các **nhận định riêng lẻ**, mỗi nhận định một ý kiểm được.
2. Với mỗi nhận định: tìm Điều/khoản/điểm làm căn cứ, **trích nguyên văn** câu bằng chứng (tối đa khoảng 30 từ).
3. Kết luận một trong bốn:
   - **ĐÚNG**: có câu chứng minh;
   - **MỘT PHẦN**: đúng nhưng thiếu hoặc thừa điều kiện;
   - **KHÔNG CÓ CĂN CỨ**: không tìm thấy trong corpus;
   - **MÂU THUẪN**: luật nói khác.
4. Căn cứ thật có thể nằm ở Điều khác với Điều đang dẫn. Ghi Điều đúng.
5. Kiểm số Điều có tồn tại và đúng tiêu đề trong corpus.

## Khi viết luật kiểm (guard, form quyết định)
- **Chặn cứng** chỉ khi có câu luật rõ ràng trích được.
- Mơ hồ, corpus không đủ, hay mô hình dữ liệu không phân biệt được trường hợp: **cảnh báo mềm**, không chặn.
- Lý do: đã từng có guard chặn oan quyết định hợp pháp (Điều 54 khoản 3 BLHS; khoản khác cùng Điều theo Điều 298 khoản 2 BLTTHS; phạt tiền bổ sung theo Điều 32 BLHS).
- Mỗi luật kiểm mang mã, mức (cứng/mềm) và căn cứ (Điều, khoản, câu trích).
- Luật kiểm pháp lý về hình phạt dùng chung một module cho nghị án AI và form Chủ tọa (`backend/app/services/trial_sentencing_rules.py`). Không tạo bản sao luật ở chỗ khác.
- Có bảng ca kiểm offline (hợp lệ và trái luật, mỗi ca có kết quả mong đợi và căn cứ). Thêm ca cho cả hai chiều khi sửa một luật.
- Nên có test tự động xác nhận các câu trích căn cứ thật sự có trong `chunks.json`.

## Không được
- Không bịa số Điều hay câu luật để lấp chỗ trống: ghi "corpus không đủ".
- Không đổi thuật ngữ trong câu trích (ví dụ corpus ghi "nhận mình có tội", không phải "thừa nhận").

## Báo cáo
- Bảng: nhận định | Điều, khoản, điểm | câu trích | kết luận.
- Tóm tắt số lượng theo kết luận, danh sách thay đổi đề xuất.
- Những chỗ corpus không đủ để kết luận (nói rõ, không suy đoán).
- Văn bản luật là công khai nên được trích trong báo cáo và tài liệu; dữ liệu sinh viên thì không.
