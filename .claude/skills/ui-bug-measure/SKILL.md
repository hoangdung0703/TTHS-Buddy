---
name: ui-bug-measure
description: Dùng khi sửa lỗi hiển thị, bố cục hoặc tương tác giao diện: khoảng trống thừa, phần tử đè nhau, cuộn sai, focus, z-index, hộp thoại, ngăn kéo, responsive.
---

# Sửa lỗi giao diện bằng số đo

Nguyên tắc: **chỉ ra nguyên nhân bằng số đo, không đoán**, rồi sửa ở gốc chung.

## 1. Tái hiện
- Dùng Playwright với backend giả (skill `frontend-e2e`), ở các viewport 1280×600, 1440×900, 1920×1080, 390×844.
- Chụp ảnh trước khi sửa, lưu ngoài repo.

## 2. Đo
Chọn các phép đo phù hợp với loại lỗi:
- **Chiều cao, khoảng trống:** `document.documentElement.scrollHeight`, `body.scrollHeight`, chiều cao khung layout và sidebar, `getBoundingClientRect()` của phần tử cuối.
- **Đè nhau, z-index:** `document.elementFromPoint` tại tâm từng phần tử nghi ngờ; chuỗi stacking context của các phần tử tổ tiên (`position`, `z-index`, `transform`, `isolation`, `opacity`).
- **Focus:** `document.activeElement` sau mỗi thao tác (mở, Tab, Esc, đóng).
- **Cuộn:** `scrollTop` của trang nền khi lăn chuột trong hộp thoại hoặc ngăn kéo.
- Computed style của các phần tử liên quan.

## 3. Nguyên nhân gốc
- Nêu file, dòng, class gây lỗi và số đo trước khi sửa.
- Kiểm **mọi màn dùng chung** component hoặc layout đó: `/dashboard`, `/chat`, `/chat/[conversationId]`, `/notes`, `/quiz`, `/quiz/[setId]`, `/trial`, `/trial/new`, `/trial/[id]`, `/trial/[id]/record`.

## 4. Sửa ở gốc
- Sửa ở component hoặc layout chung, không vá riêng từng màn.
- Không làm hỏng: bẫy focus và trả focus, Esc chỉ đóng lớp trên cùng, khóa cuộn nền, cuộn nội bộ của hộp thoại, chế độ in (`@media print`).

## Bài học đã biết trong repo
- Phần tử `absolute` (như `sr-only` của Tailwind) lấy khối chứa định vị gần nhất. Vùng cuộn nội dung phải `relative` (kèm `print:static`), nếu không document bị kéo dài.
- Lớp phủ và hộp thoại phải **portal ra `document.body`**; `z-index` bên trong một stacking context không vượt ra ngoài được.
- Thang z-index thống nhất trong `tailwind.config.ts`: `z-dialog` = 60 nằm trên ngăn kéo và sheet (50). Dùng thang này, không đặt số tùy ý.
- Safari không đặt focus vào nút khi click: lưu `event.currentTarget` làm nơi trả focus, không dùng `document.activeElement`. Phần tử đã bị gỡ thì focus về `body`.
- `overflow: hidden` trên `body` chưa đủ để khóa cuộn khi ngăn kéo nằm trong trang; đưa ngăn kéo ra portal.
- Hook dùng chung cho lớp phủ (khóa cuộn, bẫy focus, Esc, trả focus) đã có: `useModalLayer` (`frontend/src/hooks/useModalLayer.ts`, đang dùng ở `ArticleModal.tsx` và `TrialHearing.tsx`). Dùng lại thay vì viết mới.

## 5. Kiểm và báo cáo
- Đo lại sau khi sửa, cùng các viewport.
- Thêm ca e2e hồi quy **trượt trên mã cũ**.
- Báo cáo: nguyên nhân gốc (file, dòng, class), bảng số đo trước/sau, sửa ở component chung hay riêng, các màn đã kiểm thêm, test pass/tổng, đường dẫn ảnh trước/sau ngoài repo, rủi ro còn lại (đặc biệt iOS Safari chưa thử trên máy thật).
