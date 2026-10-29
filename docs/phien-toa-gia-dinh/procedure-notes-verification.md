# Đối chiếu 11 chú giải thủ tục với văn bản luật

Đối tượng: các đoạn `PROCEDURE_NOTES` trong `backend/app/services/trial_procedure_notes.py` (bản trước khi sửa, commit `923fb65`).
Người đối chiếu: developer, ngày 2026-10-29. Không gọi mô hình; chỉ đọc corpus cục bộ.

**Nguồn:** `ingestion/chunks.json`, `source_document = "Bộ luật TTHS.pdf"`. Các Điều 288-335, 260, 34, 55 được đọc nguyên văn. Mọi số Điều, khoản và câu trích bên dưới lấy từ corpus, không lấy từ trí nhớ.

**Lưu ý về phiên bản:** metadata `law_version` của cả 623 đoạn BLTTHS ghi "sửa đổi bổ sung 2021". Tuy vậy, văn bản đã có chú thích sửa đổi của Luật 99/2025/QH15. Trong vùng 288-333, các chú thích này nằm ở Điều 290 khoản 1 và điểm a khoản 2, Điều 332 và Điều 333. Ngoài ra còn chú thích của Luật TCTAND 34/2024 (bãi bỏ khoản 7 Điều 326) và Luật Tư pháp người chưa thành niên 59/2024 (Điều 330). Nghĩa là metadata đã cũ nhưng nội dung là bản hợp nhất mới. Xem thêm mục "Giới hạn" ở cuối.

## Tóm tắt

Bản cũ có 64 nhận định:

| Kết luận | Số lượng |
|---|---|
| ĐÚNG | 44 |
| MỘT PHẦN | 18 |
| KHÔNG CÓ CĂN CỨ | 1 |
| MÂU THUẪN | 1 |

Chỉ có một nhận định sai hẳn so với luật: bước 3 nói Tòa "chỉ" xét xử theo tội danh Viện kiểm sát truy tố. Điều 298 khoản 2-3 cho phép xử theo khoản khác, tội bằng hoặc nhẹ hơn, và tội nặng hơn sau khi trả hồ sơ. Một nhận định không có căn cứ trong BLTTHS: bước 5 nói Kiểm sát viên "làm rõ yếu tố cấu thành tội phạm". Các nhận định MỘT PHẦN đa số do thiếu điều kiện hoặc thu hẹp/mở rộng đối tượng.

### Thay đổi đã thực hiện trong `trial_procedure_notes.py`

Mỗi đoạn vẫn ≤ 80 từ. `PROCEDURE_NOTES_REVIEWED` vẫn là `False`.

| Bước | Sửa gì | Vì sao |
|---|---|---|
| 1 | Tách hậu quả vắng mặt theo từng người | Kiểm sát viên vắng mặt (không có dự khuyết) thì *phải* hoãn, không thể xét xử vắng mặt (289.1). Bị cáo còn có áp giải; xét xử vắng mặt chỉ trong các trường hợp 290.2 |
| 2 | "người tiến hành tố tụng" → liệt kê Thẩm phán, Hội thẩm, Kiểm sát viên, Thư ký, người giám định, phiên dịch | Điều 302 gồm cả người giám định, định giá, phiên dịch, dịch thuật. Theo Điều 55, họ là người *tham gia* tố tụng chứ không phải người tiến hành tố tụng (Điều 34) |
| 2 | "kiểm tra lý lịch bị cáo" → lý lịch của người được triệu tập; thêm "Thư ký báo cáo" | 301.2, 301.3 |
| 2 | legal_basis thêm 303 | Cam đoan của người phiên dịch, giám định, định giá thuộc bước khai mạc. StepSpec bước 2 đã có 303 |
| 3 | Bỏ "chỉ ... theo tội danh"; thêm khoản khác, tội bằng/nhẹ hơn, tội nặng hơn phải trả hồ sơ | 298.2, 298.3 (MÂU THUẪN) |
| 4 | "sau đó Hội thẩm hỏi" → Thẩm phán, Hội thẩm, người khác; bị cáo *trình bày* trước rồi mới được hỏi thêm; lời khai điều tra, truy tố *chỉ* được công bố khi luật cho phép | 307.2, 309.2, 310, 308.1-2 |
| 5 | Bỏ "yếu tố cấu thành tội phạm"; "chứng cứ buộc tội" → "buộc tội, gỡ tội"; luật sư hỏi về chứng cứ liên quan đến việc bào chữa; thêm bị cáo được hỏi khi Chủ tọa đồng ý | 309.2, 309.3, 310, 311.2 |
| 5 | legal_basis: bỏ 317, thêm 309, 310, 311 | Điều 317 là về việc trình bày ý kiến để làm rõ *quyết định, hành vi tố tụng* trong điều tra, truy tố, xét xử, không phải việc Kiểm sát viên và luật sư hỏi |
| 6 | "rút quyết định truy tố" → rút *toàn bộ*, đề nghị tuyên không có tội; Hội đồng xét xử vẫn nghị án | 320.1, 325.2, 326.4 |
| 6 | legal_basis thêm 325 | Xem xét việc rút quyết định truy tố |
| 7 | Viết lại sát chữ của 322.1; thêm "đương sự" và "người đại diện của bị cáo" | Nội dung cũ ĐÚNG nhưng căn cứ là 322.1, mà 322 không có trong legal_basis |
| 7 | legal_basis thêm 322 | |
| 8 | Thêm "đối đáp đến cùng" và bị cáo; thêm quyền cắt ý kiến không liên quan/lặp lại; điều kiện trở lại xét hỏi theo đúng Điều 323 | 322.2, 322.3, 323 |
| 11 | Thêm "xử kín chỉ đọc phần quyết định" và "quyền kháng cáo" trong phần giải thích. Đương sự chỉ kháng cáo phần liên quan. Thời hạn 15 ngày tính khác với bị cáo, đương sự vắng mặt | 327, 331.3-4, 333.1 |
| 11 | Bỏ câu về nội dung bản án (vẫn ĐÚNG theo 260.2) để giữ ≤ 80 từ; legal_basis giữ 327, 331, 333 | Câu bị bỏ không sai |
| 9, 10 | Không sửa | Mọi nhận định ĐÚNG |

### Chênh lệch chưa sửa (ngoài phạm vi việc này)

`StepSpec.legal_basis` trong `trial_state_machine.py` dùng để nạp luật cho prompt, không phải cho chú giải. Nó khác legal_basis của chú giải ở ba chỗ:

- Bước 1 có 288 nhưng không có 297.
- Bước 5 vẫn có 317.
- Bước 11 có 260 và 298 nhưng không có 331 và 333.

Chưa sửa vì đổi phần này ảnh hưởng tới prompt. Có thể đồng bộ trong việc khác nếu cần.

## Các điểm được yêu cầu soi kỹ

- **(a) "Chủ tọa không được hạn chế thời gian tranh luận"** là **Điều 322 khoản 3**: "Chủ toạ phiên tòa không được hạn chế thời gian tranh luận, phải tạo điều kiện cho Kiểm sát viên, bị cáo, người bào chữa... nhưng có quyền cắt những ý kiến không liên quan đến vụ án và ý kiến lặp lại." Bản cũ thiếu vế sau, nên là MỘT PHẦN. Điều 324 khoản 2 có một quy định riêng cho lời nói sau cùng: Hội đồng xét xử "không được hạn chế thời gian đối với bị cáo".
- **(b) Bước 1.** Các Điều 289, 290, 291, 292, 293, 297 đều tồn tại, tiêu đề khớp (bảng bước 1). Nhận định gộp "vắng mặt ... có thể dẫn tới hoãn hoặc xét xử vắng mặt" sai đối với Kiểm sát viên (289.1: phải hoãn) và thiếu áp giải/tạm đình chỉ đối với bị cáo (290.1).
- **(c) Bước 4-5.** 307.1 cho Chủ tọa quyết định thứ tự "theo thứ tự hợp lý". 307.2 nêu thứ tự: Chủ tọa hỏi trước, rồi Thẩm phán, Hội thẩm, Kiểm sát viên, người bào chữa, người bảo vệ quyền lợi đương sự. "KSV rồi người bào chữa" khớp với thứ tự liệt kê, nhưng luật không bắt buộc cứng.
- **(d) Bước 10.** Khoản 1 Điều 326 ghi biểu quyết theo đa số, Hội thẩm trước, Thẩm phán sau cùng. Bốn lựa chọn khi kết thúc nghị án ở khoản 6 Điều 326 đều đúng. Khoản 7 đã bị bãi bỏ.
- **(e) Bước 11.** Thời hạn 15 ngày đúng với *bản án* sơ thẩm (333.1). Quyết định sơ thẩm có thời hạn 07 ngày (333.2). Người được kháng cáo: xem bảng bước 11.
- **(f) Bước 2.** Xem bảng bước 2.
- **(g) Bước 6.** Điều 319 cho Kiểm sát viên rút một phần hoặc toàn bộ, hoặc kết luận về tội nhẹ hơn sau khi kết thúc xét hỏi. Điều 320.1 cho trường hợp không có căn cứ kết tội: rút toàn bộ và đề nghị tuyên không có tội. Kiểm sát viên không thể chuyển sang tội nặng hơn tại phiên tòa; tội nặng hơn chỉ đi qua đường Tòa trả hồ sơ (298.3). Bản cũ không nói sai điều này.

## Đối chiếu từng bước

Ký hiệu: Đ = ĐÚNG, MP = MỘT PHẦN, KCC = KHÔNG CÓ CĂN CỨ, MT = MÂU THUẪN. "a.b" nghĩa là Điều a khoản b.

### Bước 1. Thư ký báo cáo sự có mặt

**legal_basis cũ:** 300, 289, 290, 291, 292, 293, 297.

**Tiêu đề trong corpus:**

| Điều | Tiêu đề |
|---|---|
| 300 | Chuẩn bị khai mạc phiên tòa |
| 289 | Sự có mặt của Kiểm sát viên |
| 290 | Sự có mặt của bị cáo tại phiên tòa |
| 291 | Sự có mặt của người bào chữa |
| 292 | Sự có mặt của bị hại, đương sự hoặc người đại diện của họ |
| 293 | Sự có mặt của người làm chứng |
| 297 | Hoãn phiên tòa |

Tất cả đều liên quan. Có thể cân nhắc thêm 288 (Hội đồng xét xử, Thư ký), 294 (giám định, định giá) và 295 (phiên dịch), vì Điều 297.1.a dẫn chúng làm căn cứ hoãn. Chưa thêm vì chú giải không nói tới các người này.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Thư ký kiểm tra sự có mặt của người được triệu tập | 300.1 | "Trước khi khai mạc phiên tòa, Thư ký Tòa án phải tiến hành các công việc: 1. Kiểm tra sự có mặt của những người được Tòa án triệu tập" | Đ |
| Nêu lý do người vắng mặt | 300.1 | "nếu có người vắng mặt thì phải nêu lý do" | Đ |
| Phổ biến nội quy | 300.2 | "Phổ biến nội quy phiên tòa." | Đ |
| Kiểm sát viên vắng mặt → hoãn hoặc xét xử vắng mặt | 289.1, 289.2 | "nếu Kiểm sát viên vắng mặt thì phải hoãn phiên tòa ... Kiểm sát viên dự khuyết có mặt tại phiên tòa từ đầu được thay thế" | MP: phải hoãn (trừ khi có dự khuyết); không có xét xử vắng mặt Kiểm sát viên |
| Bị cáo vắng mặt → hoãn hoặc xét xử vắng mặt | 290.1, 290.2 | "nếu vắng mặt không vì lý do bất khả kháng ... thì bị áp giải ... Tòa án chỉ có thể xét xử vắng mặt bị cáo trong các trường hợp" | MP: thiếu áp giải và tạm đình chỉ; xét xử vắng mặt chỉ trong 4 trường hợp a-d |
| Người bào chữa vắng mặt → tùy trường hợp | 291.1 | "vắng mặt lần thứ nhất vì lý do bất khả kháng ... thì Tòa án phải hoãn phiên tòa, trừ trường hợp bị cáo đồng ý xét xử vắng mặt người bào chữa" | Đ |
| Bị hại vắng mặt → tùy trường hợp | 292.1 | "Nếu bị hại, đương sự hoặc người đại diện của họ vắng mặt thì tùy trường hợp, Hội đồng xét xử quyết định hoãn phiên tòa hoặc vẫn tiến hành xét xử." | Đ |
| Người làm chứng vắng mặt → tùy trường hợp | 293.1 | "Nếu người làm chứng về những vấn đề quan trọng của vụ án vắng mặt thì tùy trường hợp, Hội đồng xét xử quyết định hoãn phiên tòa hoặc vẫn tiến hành xét xử." | Đ |

Căn cứ chung cho việc hoãn: 297.1.a "Có một trong những căn cứ quy định tại các điều 52, 53, 288, 289, 290, 291, 292, 293, 294 và 295".

### Bước 2. Khai mạc phiên tòa

**legal_basis cũ:** 301, 302, 304, 305.

**Tiêu đề trong corpus:**

| Điều | Tiêu đề |
|---|---|
| 301 | Khai mạc phiên tòa |
| 302 | Giải quyết việc đề nghị thay đổi Thẩm phán, Hội thẩm, Kiểm sát viên, Thư ký Tòa án, người giám định, người định giá tài sản, người phiên dịch, người dịch thuật |
| 304 | Cam đoan của người làm chứng, cách ly người làm chứng |
| 305 | Giải quyết yêu cầu về xem xét chứng cứ và hoãn phiên tòa khi có người vắng mặt |

Điều 305 liên quan tới bước này nhưng chú giải không nói tới (giới hạn 80 từ). **Đề xuất thêm:** 303 (Cam đoan của người phiên dịch, người dịch thuật, người giám định, người định giá tài sản). Đã thêm.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Chủ tọa khai mạc phiên tòa | 301.1 | "Thẩm phán chủ tọa phiên tòa khai mạc phiên tòa" | Đ |
| Đọc quyết định đưa vụ án ra xét xử | 301.1 | "và đọc quyết định đưa vụ án ra xét xử" | Đ |
| Kiểm tra sự có mặt của người được triệu tập | 301.2, 301.3 | "Thư ký Tòa án báo cáo Hội đồng xét xử về sự có mặt, vắng mặt ... Chủ tọa phiên tòa kiểm tra lại sự có mặt" | Đ (Thư ký báo cáo trước, Chủ tọa kiểm tra lại) |
| Kiểm tra lý lịch *bị cáo* | 301.3 | "kiểm tra lại sự có mặt của những người có mặt tại phiên tòa theo giấy triệu tập ... và kiểm tra lý lịch, phổ biến quyền và nghĩa vụ của họ" | MP: lý lịch của mọi người được triệu tập, không chỉ bị cáo |
| Phổ biến quyền và nghĩa vụ | 301.3 | như trên | Đ |
| Hỏi có ai đề nghị thay đổi *người tiến hành tố tụng* | 302; 34.2; 55 | "hỏi Kiểm sát viên và những người tham gia tố tụng ... có đề nghị thay đổi Thẩm phán, Hội thẩm, Kiểm sát viên, Thư ký Tòa án, người giám định, người định giá tài sản, người phiên dịch" | MP: danh sách gồm cả người giám định, định giá, phiên dịch. Họ là người tham gia tố tụng (55.14-16), không phải người tiến hành tố tụng (34.2) |
| Người làm chứng cam đoan khai đúng sự thật | 304.1 | "chủ tọa phiên tòa yêu cầu người làm chứng phải cam đoan khai trung thực" | Đ |
| Người làm chứng được cách ly trước khi được hỏi | 304.2 | "Trước khi người làm chứng được hỏi về vụ án, chủ tọa phiên tòa quyết định biện pháp để cho những người làm chứng không nghe được lời khai của nhau" | Đ |

### Bước 3. Công bố cáo trạng

**legal_basis cũ:** 306 (Công bố bản cáo trạng) và 298 (Giới hạn của việc xét xử). Cả hai đều liên quan.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Trước khi xét hỏi, Kiểm sát viên công bố cáo trạng | 306 | "Trước khi tiến hành xét hỏi, Kiểm sát viên công bố bản cáo trạng" | Đ |
| Kiểm sát viên có thể trình bày ý kiến bổ sung | 306 | "và trình bày ý kiến bổ sung (nếu có)" | Đ |
| Ý kiến bổ sung không làm xấu đi tình trạng bị cáo | 306 | "Ý kiến bổ sung không được làm xấu đi tình trạng của bị cáo." | Đ |
| Cáo trạng xác định phạm vi xét xử: những bị cáo và hành vi | 298.1 | "Tòa án xét xử những bị cáo và những hành vi theo tội danh mà Viện kiểm sát truy tố và Tòa án đã quyết định đưa vụ án ra xét xử." | MP: phạm vi còn gắn với quyết định đưa vụ án ra xét xử của Tòa |
| Tòa *chỉ* xét xử theo tội danh mà Viện kiểm sát truy tố | 298.2, 298.3 | "Tòa án có thể xét xử bị cáo theo khoản khác ... hoặc về một tội khác bằng hoặc nhẹ hơn tội mà Viện kiểm sát đã truy tố" | MT |

### Bước 4. Hội đồng xét xử xét hỏi

**legal_basis cũ:**

| Điều | Tiêu đề |
|---|---|
| 307 | Trình tự xét hỏi |
| 308 | Công bố lời khai trong giai đoạn điều tra, truy tố |
| 309 | Hỏi bị cáo |
| 310 | Hỏi bị hại, đương sự hoặc người đại diện của họ |
| 311 | Hỏi người làm chứng |

Tất cả đều liên quan.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Hội đồng xét xử phải làm rõ đầy đủ từng sự việc và từng người | 307.1 | "Hội đồng xét xử phải xác định đầy đủ những tình tiết về từng sự việc, từng tội trong vụ án và từng người." | Đ (bản cũ thiếu "từng tội") |
| Chủ tọa điều hành việc hỏi | 307.1 | "Chủ tọa phiên tòa điều hành việc hỏi, quyết định người hỏi trước, hỏi sau theo thứ tự hợp lý." | Đ |
| Chủ tọa hỏi trước | 307.2 | "Khi xét hỏi từng người, chủ tọa phiên tòa hỏi trước" | Đ |
| Sau đó Hội thẩm hỏi | 307.2 | "sau đó quyết định để Thẩm phán, Hội thẩm, Kiểm sát viên, người bào chữa, người bảo vệ quyền và lợi ích hợp pháp của đương sự thực hiện việc hỏi" | MP: Chủ tọa quyết định; còn Thẩm phán (nếu có hai Thẩm phán) |
| Bị cáo được hỏi về hành vi của mình | 309.2 | "Bị cáo trình bày ý kiến về bản cáo trạng và những tình tiết của vụ án. Hội đồng xét xử hỏi thêm về những điểm mà bị cáo trình bày chưa đầy đủ" | MP: bị cáo trình bày trước, rồi mới được hỏi thêm |
| Bị hại được hỏi về những gì họ biết | 310 | "Bị hại, đương sự hoặc người đại diện của họ trình bày những tình tiết của vụ án có liên quan đến họ. Sau đó ... hỏi thêm" | MP: trình bày trước; nội dung là tình tiết liên quan đến họ |
| Người làm chứng được hỏi về những gì họ biết | 311.2 | "Chủ tọa phiên tòa yêu cầu người làm chứng trình bày rõ những tình tiết của vụ án mà họ đã biết, sau đó hỏi thêm" | Đ |
| Lời khai giai đoạn điều tra có thể được công bố khi mâu thuẫn hoặc vắng mặt | 308.1, 308.2 a, d | "Chỉ được công bố những lời khai trong giai đoạn điều tra, truy tố khi thuộc một trong các trường hợp: a) ... mâu thuẫn ... d) Người được xét hỏi vắng mặt hoặc đã chết." | MP: thiếu nguyên tắc cấm ở 308.1 ("không được công bố" khi người đó có mặt), thiếu giai đoạn truy tố và các trường hợp b, c |

### Bước 5. Kiểm sát viên và luật sư xét hỏi

**legal_basis cũ:**

| Điều | Tiêu đề |
|---|---|
| 307 | Trình tự xét hỏi |
| 317 | Điều tra viên, Kiểm sát viên, người khác có thẩm quyền tiến hành tố tụng, người tham gia tố tụng trình bày ý kiến |
| 318 | Kết thúc việc xét hỏi |

Điều 317 không phải căn cứ của nhận định nào: nội dung của nó là "trình bày ý kiến để làm rõ những quyết định, hành vi tố tụng trong giai đoạn điều tra, truy tố, xét xử". **Đề xuất:** bỏ 317, thêm 309, 310, 311. Đã sửa.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Sau Hội đồng xét xử, Kiểm sát viên rồi người bào chữa lần lượt hỏi theo điều hành của Chủ tọa | 307.1, 307.2 | "quyết định để Thẩm phán, Hội thẩm, Kiểm sát viên, người bào chữa, người bảo vệ quyền và lợi ích hợp pháp của đương sự thực hiện việc hỏi" | MP: thứ tự do Chủ tọa quyết định "theo thứ tự hợp lý"; thiếu người bảo vệ quyền lợi đương sự |
| Kiểm sát viên làm rõ yếu tố cấu thành tội phạm | (không có) | Các Điều 307-318 không có cụm này. Trong 623 đoạn BLTTHS, "cấu thành" chỉ xuất hiện ở Điều 157, 443, 500, không liên quan tới xét hỏi | KCC |
| Kiểm sát viên làm rõ chứng cứ buộc tội | 309.2 | "Kiểm sát viên hỏi bị cáo về những chứng cứ, tài liệu, đồ vật liên quan đến việc buộc tội, gỡ tội" | MP: cả gỡ tội |
| Luật sư làm rõ tình tiết có lợi cho bị cáo | 309.2 | "Người bào chữa hỏi bị cáo về những chứng cứ, tài liệu, đồ vật liên quan đến việc bào chữa và tình tiết khác của vụ án." | MP |
| Đã xem xét đầy đủ và không ai yêu cầu hỏi thêm thì Chủ tọa kết thúc xét hỏi | 318 | "chủ tọa phiên tòa hỏi Kiểm sát viên, bị cáo, người bào chữa ... có yêu cầu xét hỏi vấn đề gì nữa không. Nếu không có yêu cầu xét hỏi thì kết thúc việc xét hỏi" | Đ |

### Bước 6. Kiểm sát viên luận tội

**legal_basis cũ:**

| Điều | Tiêu đề |
|---|---|
| 320 | Trình tự phát biểu khi tranh luận |
| 321 | Luận tội của Kiểm sát viên |
| 319 | Kiểm sát viên rút quyết định truy tố hoặc kết luận về tội nhẹ hơn tại phiên tòa |

Tất cả đều liên quan. **Đề xuất thêm:** 325 (Xem xét việc rút quyết định truy tố hoặc kết luận về tội nhẹ hơn tại phiên tòa). Đã thêm.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Kết thúc xét hỏi chuyển sang tranh luận; Kiểm sát viên luận tội | 320.1 | "Sau khi kết thúc việc xét hỏi, Kiểm sát viên trình bày luận tội" | Đ |
| Luận tội phân tích chứng cứ | 321.2 | "phân tích, đánh giá khách quan, toàn diện, đầy đủ những chứng cứ xác định có tội, chứng cứ xác định vô tội" | Đ |
| Đề nghị kết tội theo toàn bộ hay một phần cáo trạng hoặc tội nhẹ hơn | 321.3 | "Đề nghị kết tội bị cáo theo toàn bộ hay một phần nội dung bản cáo trạng hoặc kết luận về tội nhẹ hơn" | Đ |
| Đề nghị hình phạt, trách nhiệm dân sự, xử lý vật chứng | 321.3 | "đề nghị mức hình phạt chính, hình phạt bổ sung, biện pháp tư pháp, trách nhiệm bồi thường thiệt hại, xử lý vật chứng" | Đ |
| Không còn căn cứ kết tội thì Kiểm sát viên rút quyết định truy tố | 320.1; 325.2; 326.4 | "nếu thấy không có căn cứ để kết tội thì rút toàn bộ quyết định truy tố và đề nghị Tòa án tuyên bố bị cáo không có tội" | MP: rút *toàn bộ* và đề nghị tuyên không có tội. Hội đồng xét xử vẫn giải quyết vụ án (326.4) |

### Bước 7. Luật sư bào chữa

**legal_basis cũ:** 320 (Trình tự phát biểu khi tranh luận). **Đề xuất thêm:** 322 (Tranh luận tại phiên tòa) vì đó là căn cứ của nhận định về nội dung bào chữa. Đã thêm.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Sau luận tội, bị cáo và người bào chữa trình bày lời bào chữa | 320.2 | "Bị cáo trình bày lời bào chữa; người bào chữa trình bày lời bào chữa cho bị cáo" | Đ |
| Bị cáo có quyền bổ sung ý kiến | 320.2 | "bị cáo, người đại diện của bị cáo có quyền bổ sung ý kiến bào chữa" | Đ |
| Luật sư phản bác điểm buộc tội chưa vững | 322.1 | "đưa ra chứng cứ, tài liệu và lập luận của mình để đối đáp với Kiểm sát viên về những chứng cứ xác định có tội, chứng cứ xác định vô tội" | Đ (căn cứ là 322, không phải 320) |
| Nêu tình tiết giảm nhẹ, đề nghị mức xử lý có lợi | 322.1 | "những tình tiết tăng nặng, giảm nhẹ trách nhiệm hình sự, mức hình phạt ... có quyền đưa ra đề nghị của mình" | Đ |
| Bị hại, người đại diện trình bày ý kiến bảo vệ quyền lợi | 320.3 | "Bị hại, đương sự, người đại diện của họ trình bày ý kiến để bảo vệ quyền và lợi ích của mình" | Đ |

Ghi chú: 320.4 quy định khi vụ án khởi tố theo yêu cầu của bị hại, bị hại trình bày ngay sau luận tội. Chú giải không nói tới trường hợp này.

### Bước 8. Tranh luận, đối đáp

**legal_basis cũ:** 322 (Tranh luận tại phiên tòa) và 323 (Trở lại việc xét hỏi). Cả hai đều liên quan.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Kiểm sát viên phải lập luận đối với từng ý kiến của người bào chữa và người tham gia tố tụng | 322.2 | "Kiểm sát viên phải đưa ra chứng cứ, tài liệu và lập luận để đối đáp đến cùng từng ý kiến của bị cáo, người bào chữa, người tham gia tố tụng khác" | MP: thiếu bị cáo và "đến cùng" |
| Người tham gia tranh luận có quyền đáp lại | 322.2 | "Người tham gia tranh luận có quyền đáp lại ý kiến của người khác." | Đ |
| Chủ tọa không được hạn chế thời gian tranh luận | 322.3 | "không được hạn chế thời gian tranh luận ... nhưng có quyền cắt những ý kiến không liên quan đến vụ án và ý kiến lặp lại" | MP: thiếu quyền cắt ý kiến |
| Cần xem xét thêm chứng cứ thì Hội đồng xét xử quyết định trở lại xét hỏi | 323 | "Nếu qua tranh luận mà thấy còn có tình tiết vụ án chưa được hỏi, chưa được làm sáng tỏ thì Hội đồng xét xử phải quyết định trở lại việc xét hỏi. Xét hỏi xong phải tiếp tục tranh luận." | MP: điều kiện là tình tiết chưa làm sáng tỏ; "phải"; xong thì tiếp tục tranh luận |

### Bước 9. Bị cáo nói lời sau cùng

**legal_basis cũ:** 324 (Bị cáo nói lời sau cùng). Đúng.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Không ai tranh luận thêm thì Chủ tọa kết thúc tranh luận | 324.1 | "Sau khi những người tham gia tranh luận không trình bày gì thêm, chủ tọa phiên tòa tuyên bố kết thúc tranh luận." | Đ |
| Bị cáo được nói lời sau cùng | 324.2 | "Bị cáo được nói lời sau cùng." | Đ |
| Không ai được đặt câu hỏi lúc này | 324.2 | "Không được đặt câu hỏi khi bị cáo nói lời sau cùng." | Đ |
| Tình tiết mới quan trọng thì phải trở lại xét hỏi | 324.2 | "bị cáo trình bày thêm tình tiết mới có ý nghĩa quan trọng đối với vụ án thì Hội đồng xét xử phải quyết định trở lại việc hỏi" | Đ |

### Bước 10. Nghị án

**legal_basis cũ:** 326 (Nghị án). Đúng.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Chỉ Thẩm phán và Hội thẩm được nghị án | 326.1 | "Chỉ Thẩm phán và Hội thẩm mới có quyền nghị án." | Đ |
| Tại phòng nghị án | 326.1 | "Việc nghị án phải được tiến hành tại phòng nghị án." | Đ |
| Biểu quyết theo đa số về từng vấn đề | 326.1 | "giải quyết tất cả các vấn đề của vụ án bằng cách biểu quyết theo đa số về từng vấn đề" | Đ |
| Hội thẩm biểu quyết trước, Thẩm phán sau cùng | 326.1 | "Hội thẩm biểu quyết trước, Thẩm phán biểu quyết sau cùng." | Đ |
| Chỉ căn cứ chứng cứ, tài liệu đã thẩm tra tại phiên tòa | 326.2 | "Việc nghị án chỉ được căn cứ vào những chứng cứ, tài liệu đã được thẩm tra tại phiên tòa" | Đ |
| Kết thúc nghị án: ra bản án, trở lại xét hỏi, trả hồ sơ, tạm đình chỉ | 326.6 | "a) Ra bản án và tuyên án; b) Trở lại việc xét hỏi và tranh luận ...; c) Trả hồ sơ vụ án để Viện kiểm sát điều tra bổ sung ...; d) Tạm đình chỉ vụ án." | Đ (rút gọn: b gồm cả tranh luận; c gồm cả yêu cầu bổ sung tài liệu) |

### Bước 11. Tuyên án

**legal_basis cũ:** 327 (Tuyên án), 331 (Người có quyền kháng cáo), 333 (Thời hạn kháng cáo). Cả ba đều liên quan. Câu về nội dung bản án dựa trên 260 (Bản án), nhưng 260 không có trong legal_basis cũ. Câu đó đã bị bỏ nên không thêm 260.

| Nhận định | Điều, khoản | Câu bằng chứng | Kết luận |
|---|---|---|---|
| Chủ tọa hoặc một thành viên Hội đồng xét xử đọc bản án | 327 | "Chủ tọa phiên tòa hoặc một thành viên khác của Hội đồng xét xử đọc bản án. Trường hợp xét xử kín thì chỉ đọc phần quyết định" | Đ (bản cũ thiếu trường hợp xét xử kín) |
| Bản án gồm nhận định và quyết định về tội danh, hình phạt, dân sự, vật chứng, án phí | 260.2 d, g; 326.3 | "Quyết định của Hội đồng xét xử về từng vấn đề phải giải quyết trong vụ án, về án phí và quyền kháng cáo đối với bản án." | Đ |
| Có thể giải thích về việc chấp hành bản án | 327 | "Sau khi đọc xong có thể giải thích thêm về việc chấp hành bản án và quyền kháng cáo." | Đ (bản cũ thiếu "quyền kháng cáo") |
| Bị cáo, bị hại có quyền kháng cáo | 331.1 | "Bị cáo, bị hại, người đại diện của họ có quyền kháng cáo bản án hoặc quyết định sơ thẩm." | Đ |
| Đương sự có quyền kháng cáo | 331.3, 331.4 | "Nguyên đơn dân sự, bị đơn dân sự, người đại diện của họ có quyền kháng cáo phần bản án hoặc quyết định có liên quan đến việc bồi thường thiệt hại." | MP: chỉ phần liên quan đến họ |
| Kháng cáo trong 15 ngày kể từ ngày tuyên án | 333.1 | "Thời hạn kháng cáo đối với bản án sơ thẩm là 15 ngày kể từ ngày tuyên án. Đối với bị cáo, đương sự vắng mặt tại phiên tòa thì thời hạn kháng cáo tính từ ngày họ nhận được bản án" | MP: thiếu trường hợp vắng mặt |

Ghi chú: 331.2, 331.5 và 331.6 cho người bào chữa, người bảo vệ quyền lợi và người được tuyên không có tội quyền kháng cáo trong phạm vi hẹp. Chú giải không liệt kê vì giới hạn 80 từ. Kháng nghị của Viện kiểm sát không thuộc các Điều đã đọc và không được nhắc trong chú giải.

## Giới hạn: những chỗ corpus không đủ để kết luận

1. **Phiên bản.** Metadata `law_version` ghi "sửa đổi bổ sung 2021". Văn bản có chú thích Luật 99/2025/QH15 ở các Điều nêu trên. Corpus không cho biết mọi sửa đổi của Luật 99/2025 đã được hợp nhất hay chưa. Tôi chỉ thấy những chỗ có chú thích, và trong Điều 288-333 không có chú thích nào làm thay đổi kết luận ở trên. Muốn chắc chắn thì phải đối chiếu với văn bản Luật 99/2025 gốc; văn bản này không có trong corpus.
2. **"Yếu tố cấu thành tội phạm" (bước 5).** Đây là khái niệm học thuật. Tôi chỉ tìm trong BLTTHS, chưa tìm trong giáo trình/đề cương có trong corpus. Kết luận KCC nghĩa là "không có căn cứ trong BLTTHS", không có nghĩa là thực tiễn không làm như vậy.
3. **Điều 291.2** dẫn Điều 76 (chỉ định người bào chữa). Tôi chưa đọc Điều 76 vì chú giải không nói tới chỉ định.
4. **Thông tư, nghị quyết hướng dẫn thủ tục phiên tòa** (ví dụ các văn bản của TANDTC trong corpus) chưa được đối chiếu. Báo cáo này chỉ dựa trên BLTTHS.
5. Corpus tách Điều 326 thành 6 đoạn theo khoản và Điều 260 thành 3 đoạn. Tôi đã đọc đủ các đoạn này; không thấy đoạn nào bị cắt cụt.
