---
name: deploy-main
description: Dùng khi người dùng đã duyệt một nhánh và yêu cầu rõ ràng đưa lên main hoặc deploy (merge fast-forward, push, kiểm Vercel, nhắc deploy Render). Không dùng khi prompt chưa cho phép merge hay deploy.
---

# Deploy một nhánh đã duyệt lên main

## Điều kiện trước
- Prompt hiện tại cho phép merge/push rõ ràng. Nếu không: dừng.
- Biết **hash `origin/main` dự kiến** và **danh sách commit dự kiến** của nhánh (thường có trong prompt). Nếu prompt không ghi: liệt kê những gì thấy và dừng để người dùng xác nhận.
- Bước deploy **không sửa code**. Gặp lỗi thì dừng và báo, không vá trong bước này.

## Các bước

1. **Kiểm nhánh**
   - `git fetch`
   - `origin/main` phải đúng hash dự kiến. Khác thì dừng và báo.
   - `git log --oneline origin/main..<nhánh>` phải đúng các commit dự kiến, không có commit lạ.
   - `git diff --stat origin/main..<nhánh>` để biết nhánh đổi `backend/`, `frontend/`, hay chỉ tài liệu.

2. **Chạy test trên nhánh** (theo phần bị đổi; đủ test như CLAUDE.md)
   - Đổi `backend/`: test backend toàn bộ (từ `backend/`: `python -m unittest discover -s tests -t tests`), ingestion `test_registry_templates` (từ gốc repo: `python -m unittest ingestion.test_registry_templates`).
   - Đổi `frontend/`: `tsc` (`npx tsc --noEmit`), `node --test` (`npm test`), e2e **hai lần liên tiếp** theo skill `frontend-e2e`.
   - So với số pass/tổng của báo cáo gần nhất. Có ca đỏ thì dừng.
   - Một ca chập chờn đã biết: chạy lại riêng ca đó 3 lần và báo kết quả, **không tự sửa test** ở bước deploy.

3. **Kiểm tương thích** (khi backend đổi API, thêm mã lỗi hay trường)
   - Đọc code frontend (chỉ đọc) và xác nhận frontend không vỡ, không chặn nhầm nút với dữ liệu mới. Trích file và dòng.
   - Phát hiện vỡ thì dừng, không merge.

4. **Merge và push**
   - `git checkout main`
   - `git merge --ff-only <nhánh>`; không fast-forward được thì dừng.
   - `git push origin main` (push thường, không bao giờ force).

5. **Vercel** (khi `frontend/` đổi)
   - Poll `https://tths-buddyy.vercel.app` tối đa khoảng 15 phút, không cần đăng nhập.
   - Tìm trong các chunk JS/CSS một chuỗi **chỉ có ở bản mới** (không dùng chuỗi đã có ở bản trước).
   - Chuỗi tiếng Việt trong bundle có thể bị mã hóa dạng `\xNN` hoặc `\uXXXX`: dò mọi dạng. Trước khi kết luận "chưa thấy", thử dò một chuỗi đã có ở bản cũ để chắc bộ dò đúng.

6. **Render** (khi `backend/` đổi)
   - **Không deploy Render.** Báo người dùng:
     - bấm Manual Deploy trên Render;
     - chờ khoảng 45 giây;
     - mở `https://tths-buddy.onrender.com/api/health`, kiểm `version` bắt đầu bằng 7 ký tự đầu của hash main.
   - Nhắc: nếu frontend đã lên mà backend chưa, các tính năng phụ thuộc trường mới có thể chạy dự phòng hoặc lỗi trong vài phút.

7. **Nhánh sao lưu** (chỉ khi prompt yêu cầu): `git push origin <nhánh>`, push thường.

## Báo cáo
- Commit hash trên main (dải `cũ..mới`).
- Test pass/tổng từng phần.
- Kết luận tương thích (nếu có bước 3).
- Trạng thái push, trạng thái Vercel (chuỗi đã dò và chunk chứa nó).
- Việc người dùng cần làm tiếp (Manual Deploy Render nếu backend đổi).
