// Fictional, layout-only fixtures for the mocked browser suite. Not real trial content: every name,
// place and sentence here is invented for the checks.
export const FAKE = "11111111-2222-3333-4444-555555555555";

export const steps = [
  "Thư ký báo cáo sự có mặt", "Khai mạc phiên tòa", "Công bố cáo trạng", "Hội đồng xét xử xét hỏi",
  "Kiểm sát viên và luật sư xét hỏi", "Kiểm sát viên luận tội", "Luật sư bào chữa", "Tranh luận, đối đáp",
  "Bị cáo nói lời sau cùng", "Nghị án", "Tuyên án"
].map((title, i) => ({ number: i + 1, title, legal_basis: ["306"] }));

export const FULL = { BI_CAO: "Trần Đức Hùng", BI_HAI: "Huỳnh Hữu Vinh", NLC_1: "Lý Thị Hoa" };
export const SHORT = { BI_CAO: "Trần Đức H", BI_HAI: "Huỳnh Hữu V", NLC_1: "Lý Thị H" };
export const participants = {
  CHU_TOA: { id: "CHU_TOA", role: "Thẩm phán - Chủ tọa phiên tòa", name: "Nguyễn Văn An" },
  HOI_THAM_1: { id: "HOI_THAM_1", role: "Hội thẩm", name: "Đoàn Thị Mai" },
  KSV: { id: "KSV", role: "Kiểm sát viên", name: "Vũ Xuân Việt" },
  LUAT_SU: { id: "LUAT_SU", role: "Luật sư bào chữa", name: "Trịnh Thị Thảo" },
  BI_CAO: { id: "BI_CAO", role: "Bị cáo", name: FULL.BI_CAO },
  BI_HAI: { id: "BI_HAI", role: "Bị hại", name: FULL.BI_HAI },
  NLC_1: { id: "NLC_1", role: "Người làm chứng", name: FULL.NLC_1 }
};

export const LONG_SPEECH = [
  "Thưa Hội đồng xét xử,",
  "Về hành vi phạm tội: Qua phần xét hỏi công khai tại phiên tòa, lời khai của bị cáo phù hợp với lời khai của bị hại, người làm chứng và các tài liệu có trong hồ sơ. Đây là đoạn văn mẫu dùng để kiểm tra bố cục đọc đoạn dài, không phải nội dung thật.",
  "Về chứng cứ:\n- Biên bản thu giữ vật chứng E1 lập ngày 19/04/2026.\n- Kết luận định giá tài sản E2 xác định giá trị 15.000.000 đồng.\n- Lời khai của người làm chứng tại cơ quan điều tra.",
  "Về tình tiết giảm nhẹ: Bị cáo thành khẩn khai báo, ăn năn hối cải và đã tự nguyện bồi thường toàn bộ thiệt hại cho bị hại.",
  "Vì các lẽ trên, Viện kiểm sát giữ nguyên quan điểm truy tố và đề nghị Hội đồng xét xử xem xét theo quy định của pháp luật."
].join("\n\n");

export const INDICTMENT = [
  "VIỆN KIỂM SÁT NHÂN DÂN KHU VỰC 1, TỈNH X\nSố: 12/CT-VKS\nNgày 01 tháng 10 năm 2026",
  `I. Nội dung vụ án\nVào ngày 19/04/2026, tại phường A, tỉnh X, ${SHORT.BI_CAO} đã lén lút lấy tài sản của ${SHORT.BI_HAI}. Đoạn văn mẫu kiểm tra bố cục.`,
  "II. Hành vi phạm tội và chứng cứ\nHành vi được chứng minh bằng các chứng cứ sau:\n- Vật chứng E1: 01 máy tính xách tay.\n- Kết luận định giá E2: 15.000.000 đồng.",
  `III. Nhân thân và tình tiết\n${SHORT.BI_CAO} chưa có tiền án, tiền sự; thành khẩn khai báo.`,
  `IV. Kết luận và truy tố\nViện kiểm sát truy tố ${SHORT.BI_CAO} về tội trộm cắp tài sản theo khoản 1 Điều 173 Bộ luật Hình sự.`
].join("\n\n");

// Marker present in every short fixture line; the suite checks it never reaches the console.
export const TRANSCRIPT_MARKER = "Lời thoại ngắn mẫu số";

export const utt = (seq, step, speaker_id, text, o = {}) => ({
  seq, step, speaker_id,
  speaker_role: participants[speaker_id]?.role.replace("Thẩm phán - ", "").replace(" phiên tòa", "") ?? "Thư ký",
  speaker_name: participants[speaker_id]?.name ?? "Tạ Phương Yến", is_user: false, kind: "speech", text, addressee: null, ...o
});

export function makeUtterances(n = 24) {
  const list = [utt(1, 1, "THU_KY", "Báo cáo Hội đồng xét xử, những người được triệu tập đều có mặt.", { kind: "procedural" })];
  for (let i = 2; i <= n; i++) list.push(utt(i, Math.min(5, 2 + Math.floor(i / 6)), i % 2 ? "CHU_TOA" : "BI_CAO", `${TRANSCRIPT_MARKER} ${i}, một đoạn, dùng để kiểm tra bố cục.`));
  list.push(utt(n + 1, 5, "BI_CAO", "Ký tự HTML phải hiện nguyên: <b>không đậm</b> & <script>x</script> \"ngoặc\"."));
  list.push(utt(n + 2, 6, "LUAT_SU", LONG_SPEECH));
  return list;
}

export const caseFile = {
  title: "Vụ mẫu trộm cắp tài sản tại phường A",
  incident_summary: `Ngày 19/04/2026, ${SHORT.BI_CAO} lấy tài sản của ${SHORT.BI_HAI}.`,
  defendant: { id: "BI_CAO", name: SHORT.BI_CAO, gender: "nam", age: 32, occupation: "Lao động tự do", residence_place: "phường A, tỉnh X", education: "12/12", prior_record: "Không", preventive_measure: "Cấm đi khỏi nơi cư trú" },
  victim: { id: "BI_HAI", name: SHORT.BI_HAI, gender: "nam", age: 41, occupation: "Buôn bán", residence_place: "phường B, tỉnh X" },
  witnesses: [{ id: "NLC_1", name: SHORT.NLC_1, gender: "nu", age: 35, occupation: "Nội trợ", residence_place: "phường A, tỉnh X" }],
  related_party: null,
  facts: [{ id: "F1", time: "19/04/2026", place: "phường A, tỉnh X", description: `${SHORT.BI_CAO} lấy 01 máy tính xách tay.` }],
  evidence: [{ id: "E1", type: "vat_chung", description: "01 máy tính xách tay", value_vnd: 12000000 }, { id: "E2", type: "dinh_gia", description: "Kết luận định giá tài sản", value_vnd: 15000000 }],
  pretrial_statements: [
    { person_id: "BI_CAO", summary: `${SHORT.BI_CAO} khai đã lấy tài sản vì cần tiền trả nợ.`, inconsistencies: [] },
    { person_id: "NLC_1", summary: `${SHORT.NLC_1} khai nhìn thấy ${SHORT.BI_CAO} rời khỏi nhà bị hại.`, inconsistencies: [] }
  ],
  charge: { dieu: "173", khoan: "1", diem: [], crime_name: "Tội trộm cắp tài sản" },
  measure_value: 15000000,
  civil_claim: { claimant_id: "BI_HAI", amount_vnd: 2000000, basis: "Chi phí sửa khóa cửa" },
  indictment_text: INDICTMENT,
  display_names: { CHU_TOA: "Nguyễn Văn An", KSV: "Vũ Xuân Việt", ...SHORT }
};

export const COURT_NAME = "Tòa án nhân dân khu vực 1, tỉnh X";
export const DISCLAIMER = "Mô phỏng học tập · Không phải phiên tòa hay bản án thật · Nhân vật và tình tiết đều là giả định.";
export const OBSERVER_PREAMBLE = "Phiên tòa mô phỏng do hệ thống đóng mọi vai; người học quan sát.";

export const config = (overrides = {}) => ({
  crimes: [
    { crime_key: "blhs_173", crime_name: "Tội trộm cắp tài sản", dieu: "173", allowed_khoan: ["1", "2"] },
    { crime_key: "blhs_134", crime_name: "Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác", dieu: "134", allowed_khoan: ["1", "2"] }
  ],
  user_roles: ["ksv", "luat_su", "nguoi_xem"],
  limits: { max_cases_per_day: 5, max_active_sessions: 3, max_witnesses: 2, abandon_after_days: 14 },
  remaining: { cases_today: 3, active_sessions: 2 },
  ...overrides
});

// Fictional procedure note, same shape as state.procedure_note (contract 5.1).
export const procedureNote = (step, reviewed = false) => ({
  step,
  title: steps[step - 1].title,
  text: `Chú giải mẫu cho bước ${step}: ai nói, nói gì và vì sao, viết để kiểm tra bố cục.`,
  legal_basis: ["307", "317"],
  reviewed
});

export function recordDoc({ observer = false } = {}) {
  return {
    disclaimer: DISCLAIMER,
    form_reference: "Mẫu số 22-HS (Ban hành kèm theo Nghị quyết số 05/2017/NQ-HĐTP ngày 19 tháng 9 năm 2017 của Hội đồng Thẩm phán Tòa án nhân dân tối cao)",
    preamble: observer ? [OBSERVER_PREAMBLE] : [],
    court_name: COURT_NAME,
    national_header: ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc"],
    title: "BIÊN BẢN",
    subtitle: "PHIÊN TÒA HÌNH SỰ SƠ THẨM",
    opening: [
      { label: "Vào hồi", value: "08 giờ 05 phút ngày 28 tháng 10 năm 2026", simulated: true },
      { label: "Tại", value: "Trụ sở Tòa án, phường A, tỉnh X", simulated: true },
      { label: "Xét xử", value: "công khai", simulated: true },
      { label: "Vụ án hình sự thụ lý số", value: null }
    ],
    sections: [
      { heading: "I. Những người tiến hành tố tụng", fields: [
        { label: "Thẩm phán - Chủ tọa phiên tòa", value: "Ông Nguyễn Văn An" },
        { label: "Thư ký phiên tòa", value: "Bà Tạ Phương Yến" },
        { label: "Kiểm sát viên", value: "Ông Vũ Xuân Việt - Viện kiểm sát nhân dân khu vực 1, tỉnh X" }], entries: [], notes: [], subsections: [] },
      { heading: "II. Những người tham gia tố tụng", fields: [
        { label: "Bị cáo", value: `${FULL.BI_CAO}, sinh năm 1994; dân tộc: ......; con ông ...... và bà ......; có mặt.` },
        { label: "Người bào chữa", value: "Luật sư Trịnh Thị Thảo - Văn phòng luật sư ......; có mặt." },
        { label: "Người phiên dịch", value: null }], entries: [], notes: [], subsections: [] },
      { heading: "III. Phần thủ tục bắt đầu phiên tòa", fields: [], notes: [], subsections: [], entries: [
        { seq: 1, step: 1, speaker_role: "Thư ký", speaker_name: "Tạ Phương Yến", text: "Báo cáo Hội đồng xét xử, những người được triệu tập đều có mặt." },
        { seq: 2, step: 2, speaker_role: "Chủ tọa", speaker_name: "Nguyễn Văn An", text: "Tôi tuyên bố khai mạc phiên tòa." }] },
      { heading: "IV. Phần tranh tụng tại phiên tòa", fields: [], entries: [], notes: ["Hội đồng xét xử vào phòng nghị án để nghị án.", "Hội đồng xét xử trở lại phòng xử án để tuyên án."], subsections: [
        { heading: "1. Kiểm sát viên công bố bản cáo trạng", content: "verbatim", fields: [], notes: [], subsections: [], entries: [
          { seq: 3, step: 3, speaker_role: "Kiểm sát viên", speaker_name: "Vũ Xuân Việt", text: INDICTMENT.replaceAll(SHORT.BI_CAO, FULL.BI_CAO).replaceAll(SHORT.BI_HAI, FULL.BI_HAI) }] },
        { heading: "2. Hỏi và trả lời tại phiên tòa", content: "summary", summary: `Hội đồng xét xử hỏi bị cáo ${FULL.BI_CAO} về diễn biến sự việc; bị cáo thừa nhận hành vi.\n\nKiểm sát viên hỏi người làm chứng ${FULL.NLC_1}; người làm chứng xác nhận đã nhìn thấy bị cáo rời khỏi nhà bị hại.`, fields: [], notes: [], subsections: [], entries: [] },
        { heading: "3. Tranh luận tại phiên tòa", content: "verbatim", summary_fallback: true, fields: [], notes: [], subsections: [], entries: [
          { seq: 40, step: 6, speaker_role: "Kiểm sát viên", speaker_name: "Vũ Xuân Việt", text: LONG_SPEECH },
          { seq: 41, step: 7, speaker_role: "Luật sư bào chữa", speaker_name: "Trịnh Thị Thảo", text: "Đề nghị Hội đồng xét xử xem xét các tình tiết giảm nhẹ cho bị cáo." }] },
        { heading: "4. Lời nói sau cùng của bị cáo", content: "verbatim", fields: [], notes: [], subsections: [], entries: [
          { seq: 50, step: 9, speaker_role: "Bị cáo", speaker_name: FULL.BI_CAO, text: "Bị cáo xin Hội đồng xét xử khoan hồng." }] }] }
    ],
    closing: [
      { label: "Những sửa đổi, bổ sung theo yêu cầu của Kiểm sát viên, người tham gia tố tụng", value: null },
      { label: "Phiên tòa kết thúc vào hồi", value: "10 giờ 30 phút cùng ngày", simulated: true }
    ],
    signatures: [
      { title: "THƯ KÝ GHI BIÊN BẢN PHIÊN TÒA", note: "(Ký tên, ghi rõ họ tên)", name: "Tạ Phương Yến" },
      { title: "THẨM PHÁN - CHỦ TỌA PHIÊN TÒA", note: "(Ký tên, ghi rõ họ tên, đóng dấu)", name: "Nguyễn Văn An" }
    ],
    appendix: [{ heading: "PHỤ LỤC (ngoài Mẫu số 22-HS): Lời tuyên án", content: "verbatim", fields: [], subsections: [],
      notes: ["Phụ lục do hệ thống mô phỏng đính kèm, chép nguyên văn lời tuyên án tại phiên tòa."],
      entries: [{ seq: 80, step: 11, speaker_role: "Chủ tọa", speaker_name: "Nguyễn Văn An", text: "Về tội danh: Tuyên bố bị cáo phạm tội trộm cắp tài sản (văn bản mẫu).\n\nVề án phí: Bị cáo chịu án phí theo quy định (văn bản mẫu)." }] }]
  };
}

export const recordText = ({ observer = false } = {}) =>
  [`*** ${DISCLAIMER.toUpperCase()} ***`, ...(observer ? [OBSERVER_PREAMBLE] : []), COURT_NAME.toUpperCase(), "BIÊN BẢN",
    "PHIÊN TÒA HÌNH SỰ SƠ THẨM", "Vào hồi: 08 giờ 05 phút", "Vụ án hình sự thụ lý số: ......", "", "I. NHỮNG NGƯỜI TIẾN HÀNH TỐ TỤNG",
    "Thư ký phiên tòa: Bà Tạ Phương Yến", `*** ${DISCLAIMER.toUpperCase()} ***`].join("\n");

// --- Clerk role (contract 5.2, 3.7-3.10) ---------------------------------------------------------
export const CLERK_NAME = "Tạ Phương Yến";
export const CLERK_PREFILL = `Thưa Hội đồng xét xử, theo giấy triệu tập của Tòa án, tại phiên tòa hôm nay có mặt: Kiểm sát viên Vũ Xuân Việt; bị cáo ${FULL.BI_CAO}; luật sư bào chữa Trịnh Thị Thảo; người làm chứng ${FULL.NLC_1}. Vắng mặt: bị hại ${FULL.BI_HAI}, có đơn đề nghị xét xử vắng mặt. Thư ký phiên tòa đã phổ biến nội quy phiên tòa. Báo cáo Hội đồng xét xử.`;
export const clerkReport = () => ({
  prefill: CLERK_PREFILL,
  attendance: [
    { speaker_id: "KSV", role: "Kiểm sát viên", name: "Vũ Xuân Việt", present: true },
    { speaker_id: "BI_CAO", role: "Bị cáo", name: FULL.BI_CAO, present: true },
    { speaker_id: "LUAT_SU", role: "Luật sư bào chữa", name: "Trịnh Thị Thảo", present: true },
    { speaker_id: "BI_HAI", role: "Bị hại", name: FULL.BI_HAI, present: false },
    { speaker_id: "NLC_1", role: "Người làm chứng", name: FULL.NLC_1, present: true }
  ]
});
export const clerkPrompt = (step, reviewed = false) => ({ step, text: `Câu nhắc ghi chép mẫu cho bước ${step}: ghi ai nói và nội dung chính.`, reviewed });
export const CLERK_DRAFT_PREAMBLE = "Bản nháp: Thư ký chưa chốt biên bản.";
export const CLERK_AUTHOR_NOTE = "Do Thư ký (người học) ghi";

// The record of a clerk session: IV.2 and IV.3 are the student's text (content "user").
export function clerkRecordDoc({ iv2 = "", iv3 = "", finalized = false } = {}) {
  const doc = recordDoc();
  doc.preamble = finalized ? [] : [CLERK_DRAFT_PREAMBLE];
  doc.draft = !finalized;
  const partIv = doc.sections[3];
  partIv.subsections[1] = { heading: "2. Hỏi và trả lời tại phiên tòa", content: "user", summary: iv2 || null, author_note: CLERK_AUTHOR_NOTE, fields: [], notes: [], subsections: [], entries: [] };
  partIv.subsections[2] = { heading: "3. Tranh luận tại phiên tòa", content: "user", summary: iv3 || null, author_note: CLERK_AUTHOR_NOTE, fields: [], notes: [], subsections: [], entries: [] };
  return doc;
}

export const clerkRecordText = ({ iv2 = "", iv3 = "", finalized = false } = {}) =>
  [`*** ${DISCLAIMER.toUpperCase()} ***`, ...(finalized ? [] : [CLERK_DRAFT_PREAMBLE]), COURT_NAME.toUpperCase(), "BIÊN BẢN",
    "2. Hỏi và trả lời tại phiên tòa", `(${CLERK_AUTHOR_NOTE})`, iv2 || "......", "3. Tranh luận tại phiên tòa", `(${CLERK_AUTHOR_NOTE})`, iv3 || "......",
    `*** ${DISCLAIMER.toUpperCase()} ***`].join("\n");

// --- Defendant role (contract 5.3, 3.3) ------------------------------------------------------------
export const ROLE_BRIEF_NOTE = "Đây là gợi ý nhập vai. Bạn có thể khai khác; Hội đồng xét xử sẽ đối chiếu với hồ sơ.";
export const roleBrief = () => ({
  stance: "Lập trường mẫu: nhận đã lấy tài sản nhưng cho rằng giá trị thấp hơn kết luận định giá.",
  knowledge: [`Biết ${SHORT.BI_HAI} để máy tính trên bàn (dữ kiện mẫu).`, "Đã bán lại tài sản cho người lạ (dữ kiện mẫu)."],
  demeanor: "Bình tĩnh, hơi lo lắng (mẫu).",
  note: ROLE_BRIEF_NOTE
});
export const DECLINE_TEXT = "Bị cáo có quyền trình bày lời khai, trình bày ý kiến, không buộc phải đưa ra lời khai chống lại chính mình hoặc buộc phải nhận mình có tội (câu mẫu).";
export const declineNote = () => ({
  text: DECLINE_TEXT,
  legal_basis: ["điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự", "điểm b khoản 2 Điều 308 Bộ luật Tố tụng hình sự"],
  reviewed: false
});
export const IDENTITY_PREFILL = `Tôi tên là ${FULL.BI_CAO}, 32 tuổi, nơi cư trú phường A, tỉnh X, nghề nghiệp lao động tự do, trình độ học vấn 12/12, chưa có tiền án, tiền sự.`;
// A question put to the defendant: the utterance and the matching pending_question.
export function defendantQuestion(seq, step, speaker_id, text, { prefill = null, decline = false } = {}) {
  const utterance = utt(seq, step, speaker_id, text);
  return {
    utterance,
    pending: {
      seq, speaker_id, speaker_role: utterance.speaker_role, speaker_name: utterance.speaker_name, text,
      prefill, decline_note: decline ? declineNote() : null
    }
  };
}

// --- Presiding judge (contract 3.7, chặng R4) -----------------------------------------------------------
export const RETURN_NOTE = "Hội đồng xét xử quyết định trở lại việc xét hỏi (Điều 323 Bộ luật Tố tụng hình sự).";
export const SYSTEM_DRAFTED_NOTE = "Lời tuyên do hệ thống soạn từ quyết định của Chủ tọa (người học).";
export const DELIBERATION_HEADING = "PHỤ LỤC (ngoài Mẫu số 22-HS): Biên bản nghị án";
export const DELIBERATION_INTRO = "Phụ lục do hệ thống mô phỏng dựng theo khoản 2 Điều 259 Bộ luật Tố tụng hình sự từ quyết định Chủ tọa (người học) đã chốt.";
export const MINORITY_NOTE = "Ý kiến thiểu số của Hội thẩm nhân dân Lâm Văn Phúc: đề nghị cân nhắc thêm tình tiết giảm nhẹ (mẫu).";

// The record of a presiding session: IV.2 notes the Điều 323 return; the judgment appendix says the
// system wrote it; a second appendix, built by code from the locked decision.
export function chairRecordDoc() {
  const doc = recordDoc();
  doc.sections[3].subsections[1].notes = [RETURN_NOTE];
  doc.appendix[0].notes = [...doc.appendix[0].notes, SYSTEM_DRAFTED_NOTE];
  doc.appendix.push({ heading: DELIBERATION_HEADING, content: null, entries: [], subsections: [],
    notes: [DELIBERATION_INTRO, "Hội thẩm nhân dân Đoàn Thị Mai đồng ý với quyết định.", MINORITY_NOTE],
    fields: [
      { label: "Tòa án", value: COURT_NAME },
      { label: "Thẩm phán - Chủ tọa phiên tòa", value: "Nguyễn Văn An" },
      { label: "Căn cứ kết tội (điểm c khoản 3 Điều 326)", value: "Bị cáo phạm tội; áp dụng khoản 1 Điều 173 Bộ luật Hình sự." },
      { label: "Hình phạt (điểm d khoản 3 Điều 326)", value: "Tù 12 tháng." },
      { label: "Các vấn đề tại điểm a, b, đ, g, h khoản 3 Điều 326", value: "Không xem xét trong phạm vi mô phỏng." },
      { label: "Nhận định của Chủ tọa", value: "Nhận định mẫu của người học (văn bản giả định)." }
    ] });
  return doc;
}

export const chairRecordText = () => [recordText(), "PHỤ LỤC (NGOÀI MẪU SỐ 22-HS): BIÊN BẢN NGHỊ ÁN"].join("\n");
