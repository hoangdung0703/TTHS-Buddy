# Định dạng ngân hàng đề trắc nghiệm

File dữ liệu thật: `ingestion/question_bank.json`. Hiện đang **rỗng** (`[]`) — chờ ngân hàng đề mới.

File này mô tả định dạng cần nhập. Mọi câu hỏi trong ví dụ dưới đây là **câu giả**, không phải đề thật.

## Cấu trúc tổng thể

`question_bank.json` là **một mảng JSON phẳng**, mỗi phần tử là một câu hỏi. Không có object bọc ngoài, không chia nhóm lồng nhau — việc chia bộ đề thực hiện qua field `quiz_set` của từng câu.

```json
[
  { ...câu hỏi 1... },
  { ...câu hỏi 2... }
]
```

File rỗng hợp lệ là `[]`. Hệ thống chạy bình thường khi rỗng (trang Trắc nghiệm hiện trạng thái "đang cập nhật").

## Các field của một câu hỏi

Mọi câu hỏi phải có **đủ 9 field** dưới đây. Field tùy chọn vẫn phải xuất hiện, nếu không có giá trị thì ghi `null` — **không được bỏ hẳn field ra khỏi object**.

| Field | Bắt buộc có giá trị | Kiểu | Ghi chú |
|---|---|---|---|
| `question_id` | Có | string | Mã riêng, **không được trùng** với bất kỳ câu nào khác trong file. Xem quy ước đặt tên bên dưới |
| `question_text` | Có | string | Nội dung câu hỏi |
| `question_type` | Có | string | Hiện chỉ nhận đúng một giá trị: `"mcq_4choice"` |
| `mcq_options` | Có | mảng 4 string | Đúng **4** đáp án, **không được trùng nhau** |
| `mcq_correct` | Có | string | Phải **giống y hệt** (từng ký tự) một phần tử trong `mcq_options` |
| `quiz_set` | Có | số nguyên | Câu này thuộc bộ đề số mấy. Xem phần "Cách đặt bộ đề" |
| `dieu_number` | Không | string hoặc `null` | Số Điều làm căn cứ, dạng chuỗi: `"119"`, không phải số `119` |
| `topic_category` | Không | string hoặc `null` | Tên chủ đề. Dùng cho thống kê "Chủ đề cần ôn lại" ở Dashboard |
| `explanation` | Không | string hoặc `null` | Giải thích hiện ra sau khi sinh viên nộp bài |

### Câu sai định dạng sẽ bị bỏ qua, không báo lỗi

Khi tải ngân hàng đề, hệ thống **tự loại** câu nào: `question_type` khác `"mcq_4choice"`, hoặc `mcq_options` không đúng 4 phần tử, hoặc 4 đáp án có phần trùng nhau, hoặc `mcq_correct` không khớp đáp án nào. Câu bị loại **biến mất khỏi bộ đề một cách im lặng** (chỉ ghi vào log server). Vì vậy sau khi nhập xong cần kiểm tra số câu mỗi bộ hiện ra trên trang Trắc nghiệm có đúng như mong đợi không.

### Hai lỗi dễ mắc nhất

1. **`mcq_correct` lệch so với `mcq_options`** — chỉ cần thừa một dấu cách, thiếu dấu chấm cuối câu, hoặc viết hoa khác là câu đó bị loại. An toàn nhất: copy-paste nguyên văn từ `mcq_options` sang.
2. **`dieu_number` ghi dạng số** — phải là `"119"` (có ngoặc kép), không phải `119`.

## Cách đặt bộ đề

Không có file cấu hình danh sách bộ đề. Hệ thống **tự suy ra** số bộ đề và số câu mỗi bộ từ chính dữ liệu:

- Có bao nhiêu giá trị `quiz_set` khác nhau thì có bấy nhiêu bộ đề.
- Mỗi bộ có bao nhiêu câu là đếm số câu mang `quiz_set` đó.

Nghĩa là nhóm luật **tự do quyết định** số bộ và số câu mỗi bộ — 10 bộ × 10 câu, 20 bộ × 5 câu, hay các bộ dài ngắn khác nhau đều chạy được, không cần ai sửa code.

Lưu ý: `quiz_set` nên đánh số **liên tục từ 1** (1, 2, 3...). Nhảy số vẫn chạy nhưng trang Trắc nghiệm sẽ hiện đúng số đó (ví dụ để `quiz_set: 1` và `quiz_set: 7` thì sinh viên thấy "Bộ đề 01" và "Bộ đề 07", không có bộ 02–06).

## Quy ước đặt `question_id`

Khuyến nghị dạng `<loại>-set<số bộ>-q<số câu trong bộ>`, ví dụ `mcq4-set1-q1`, `mcq4-set1-q2`, `mcq4-set2-q1`. Quy ước này không bị hệ thống kiểm tra — yêu cầu bắt buộc duy nhất là **không trùng nhau**.

Cảnh báo: lịch sử làm bài của sinh viên lưu theo `question_id`. Nếu sau này đổi `question_id` của một câu đã có người làm, lượt làm cũ sẽ không còn khớp được với câu hỏi nữa. Nên coi `question_id` là cố định sau khi đã đưa vào sử dụng.

## Ví dụ đầy đủ: 1 bộ đề gồm 2 câu giả

```json
[
  {
    "question_id": "mcq4-set1-q1",
    "question_text": "Câu hỏi mẫu số một — nội dung giả dùng để minh họa định dạng?",
    "question_type": "mcq_4choice",
    "mcq_options": [
      "Đáp án mẫu A.",
      "Đáp án mẫu B.",
      "Đáp án mẫu C.",
      "Đáp án mẫu D."
    ],
    "mcq_correct": "Đáp án mẫu B.",
    "quiz_set": 1,
    "dieu_number": "119",
    "topic_category": "Chủ đề mẫu",
    "explanation": "Giải thích mẫu — hiện ra sau khi sinh viên nộp bài."
  },
  {
    "question_id": "mcq4-set1-q2",
    "question_text": "Câu hỏi mẫu số hai — câu này không ghi căn cứ Điều luật?",
    "question_type": "mcq_4choice",
    "mcq_options": [
      "Đáp án mẫu một.",
      "Đáp án mẫu hai.",
      "Đáp án mẫu ba.",
      "Đáp án mẫu bốn."
    ],
    "mcq_correct": "Đáp án mẫu một.",
    "quiz_set": 1,
    "dieu_number": null,
    "topic_category": null,
    "explanation": null
  }
]
```

## Kiểm tra file trước khi dùng

Chạy trong thư mục gốc dự án:

```
python3 -c "import json;d=json.load(open('ingestion/question_bank.json'));print(len(d),'câu')"
```

Lệnh này báo lỗi ngay nếu file sai cú pháp JSON (thiếu dấu phẩy, thừa dấu phẩy cuối mảng, ngoặc kép sai...). Nếu in ra số câu thì cú pháp đã đúng.
