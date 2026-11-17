---
name: frontend-e2e
description: Dùng khi chạy, thêm hoặc sửa test e2e frontend (Playwright với backend giả), và khi kiểm thử bất kỳ thay đổi nào trong frontend/.
---

# E2e frontend

## Bộ test
- Nằm ở `frontend/tests/e2e` (`suite.mjs` là runner, `build.sh` là script build, `lib.mjs` và `chair.mjs` là backend giả, `fixtures.mjs` là dữ liệu giả). Đọc `README.md` ở đó trước. Lệnh, chạy từ `frontend/`:
  ```
  tests/e2e/build.sh && node tests/e2e/suite.mjs
  ```
  Dừng server: `kill $(cat ${E2E_WORK_DIR:-$TMPDIR/ttths-e2e}/server.pid)`.
- Là **script Node dùng Playwright từ npx cache**, không phải `@playwright/test`: không có `expect`, `toBeFocused`, `--repeat-each`. Không thêm dependency để có chúng.
- Có **backend giả** trong bộ test. Không gọi backend thật, không gọi Gemini.

## Môi trường chạy
- **Chạy trong bản sao ở thư mục tạm.** Không build trong `frontend/` (người dùng có thể đang chạy `next dev`; build sẽ ghi đè `.next`). `build.sh` đã làm việc này: bản sao ở `$E2E_WORK_DIR` (mặc định `$TMPDIR/ttths-e2e`), không chép `.env*`.
- Dùng **cổng riêng**, không trùng 3000. `build.sh` mặc định cổng 3011 (`E2E_PORT`).
- Build với `NEXT_PUBLIC_USE_MOCK_DATA=false` để các trang gọi backend giả thật sự (khi bật dữ liệu mẫu, Chat không gọi route nào và lỗi thật bị che). `build.sh` đã đặt sẵn biến này; `api.ts` coi mọi giá trị khác đúng chuỗi `"false"`, kể cả không đặt, là bật dữ liệu mẫu.

## Backend giả
- Mở rộng **đúng theo `docs/phien-toa-gia-dinh/API-CONTRACT.md`**, kể cả mã lỗi và trường tùy chọn.
- Khi backend thêm trường mới: mô phỏng cả chế độ **có** và **không có** trường đó (frontend phải có dự phòng).
- Nếu sau khi mock đúng hợp đồng mà trang vẫn sai: đó có thể là **lỗi thật** của ứng dụng. Mô tả bằng số đo (URL, request, response, state) và báo, đừng che bằng mock.

## Viết ca kiểm
- Chờ có điều kiện (`waitForFunction` hoặc vòng poll có timeout, khoảng 5 giây). **Không dùng `waitForTimeout` cố định.** Ca KSV "at bottom: new lines followed" đang dùng 1200 ms cố định và từng chập chờn.
- Không skip ca, không thêm retry toàn cục, không nới điều kiện kiểm để cho xanh.
- Tách các điều kiện khác nhau thành ca hoặc lần kiểm riêng để khi hỏng biết điều kiện nào hỏng.
- Không đặt `emulateMedia("print")` trước các kiểm focus: Chromium có thể làm mất focus khi lớp phủ bị ẩn ở chế độ in.
- Ca hồi quy phải **trượt trên mã cũ** và qua trên mã mới.
- Kiểm các viewport: 1280×600, 1440×900, 1920×1080, 390×844. Không thanh cuộn ngang, không khoảng trống thừa ở đáy trang.
- Kiểm không hồi quy các vai và màn khác (Chat, Vở ghi, Trắc nghiệm, Tổng quan, các vai phiên tòa).

## Tiêu chí xong
- Tính năng hoặc sửa lỗi mới: toàn bộ e2e **ba lần liên tiếp** đều xanh.
- Bước deploy: hai lần liên tiếp.
- Kèm `tsc` (`npx tsc --noEmit`), `node --test` (`npm test`), lint (cấu hình tạm ngoài repo), đều chạy từ `frontend/`.
- Ảnh chụp lưu **ngoài repo**, không commit.

## Báo cáo
- E2e pass/tổng của từng lần chạy (ghi số thực, kể cả khi khác số kỳ vọng và giải thích).
- Ca mới thêm, ca cũ đổi kỳ vọng (và lý do).
- Ca chập chờn nếu có: điều kiện nào, tần suất, nguyên nhân (test hay ứng dụng).
- Đường dẫn ảnh và log ngoài repo.
