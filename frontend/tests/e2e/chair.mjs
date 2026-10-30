// Fake presiding-judge backend (contract 5.4) for the mocked browser suite: the same checklist,
// order rules, counters, Điều 323 return and 409 codes as backend/app/services/trial_presiding.py,
// for steps 1-11 and one case shape (victim present, one witness). Steps 10-11: PUT /decision with
// a subset of the checks of trial_chair_decision.py (same codes, fields and basis shapes), the
// assessors' comments (state only, never an utterance), the judgment preview and pronouncement.
// Every line is invented.
import { participants, utt } from "./fixtures.mjs";
import { baseState, fulfillError, fulfillJson, fulfillSse, sseEvent } from "./lib.mjs";

export const CHAIR_MARK = "Lời mẫu Chủ tọa giả định";
export const DEBATE_NOTE = "Giới hạn tối đa 2 vòng đối đáp là giới hạn của bản mô phỏng. Theo khoản 3 Điều 322 Bộ luật Tố tụng hình sự, Chủ tọa phiên tòa không được hạn chế thời gian tranh luận.";
const LONG_TEMPLATE = `${CHAIR_MARK}: hôm nay Tòa án nhân dân khu vực 1, tỉnh X mở phiên tòa xét xử sơ thẩm công khai vụ án hình sự đối với bị cáo Trần Đức Hùng, bị Viện kiểm sát truy tố về tội trộm cắp tài sản theo khoản 1 Điều 173 Bộ luật Hình sự. Tôi tuyên bố khai mạc phiên tòa và đọc quyết định đưa vụ án ra xét xử.`;

const I = (key, label, kind, required, basis, o = {}) => ({ key, label, kind, required, basis, first: false, last: false, after: [], ai: 0, note: null, ...o });
const STEP_ITEMS = {
  2: [
    I("khai_mac", "Khai mạc, đọc quyết định đưa vụ án ra xét xử", "item", true, ["301"], { first: true, template: LONG_TEMPLATE }),
    I("kiem_tra_can_cuoc", "Kiểm tra căn cước bị cáo", "item", true, ["301"]),
    I("kiem_tra_co_mat", "Kiểm tra sự có mặt, giới thiệu thành phần", "item", true, ["301"]),
    I("giai_thich_quyen", "Phổ biến quyền và nghĩa vụ", "item", true, ["301"]),
    I("hoi_thay_doi", "Hỏi đề nghị thay đổi người tiến hành tố tụng", "item", true, ["302"]),
    I("cam_doan_nlc", "Người làm chứng cam đoan, cách ly người làm chứng", "item", true, ["304"]),
    I("hoi_yeu_cau", "Hỏi yêu cầu triệu tập thêm, xem xét chứng cứ, hoãn phiên tòa", "item", false, ["305"])
  ],
  3: [I("moi_cong_bo_cao_trang", "Mời Kiểm sát viên công bố cáo trạng", "invite", true, ["306"])],
  4: [
    I("hoi_bi_cao", "Hỏi bị cáo (ít nhất 1 câu)", "ask", true, ["307", "309"], { ai: 1 }),
    I("hoi_nguoi_khac", "Hỏi bị hại, người làm chứng, người có quyền lợi, nghĩa vụ liên quan", "ask", false, ["310", "311"], { ai: 1 }),
    I("moi_hoi_tham_hoi", "Mời Hội thẩm hỏi", "invite", false, ["307"], { ai: 1 })
  ],
  5: [
    I("moi_ksv_hoi", "Mời Kiểm sát viên xét hỏi", "invite", true, ["307"], { ai: 1 }),
    I("moi_ls_hoi", "Mời luật sư xét hỏi", "invite", true, ["307"], { ai: 1 }),
    I("ket_thuc_xet_hoi", "Kết thúc xét hỏi", "item", true, ["318"], { last: true })
  ],
  6: [I("moi_luan_toi", "Mời Kiểm sát viên trình bày luận tội", "invite", true, ["320", "321"], { ai: 1 })],
  7: [
    I("moi_bao_chua", "Mời luật sư bào chữa", "invite", true, ["320"], { ai: 1 }),
    I("moi_bi_hai_trinh_bay", "Mời bị hại trình bày", "invite", true, ["320"], { ai: 1 }),
    I("hoi_bi_cao_bo_sung", "Hỏi bị cáo có bổ sung ý kiến bào chữa", "invite", false, ["320"], { ai: 1 })
  ],
  8: [
    I("moi_doi_dap", "Mời đối đáp (vòng 1)", "invite", true, ["322"], { ai: 2 }),
    I("vong_2", "Mời đối đáp thêm (vòng 2)", "invite", false, ["322"], { ai: 2, after: ["moi_doi_dap"], note: DEBATE_NOTE }),
    I("tro_lai_xet_hoi", "Trở lại việc xét hỏi (một lần mỗi phiên)", "return", false, ["323"], { after: ["moi_doi_dap"] }),
    I("ket_thuc_tranh_luan", "Kết thúc tranh luận", "item", true, ["324"], { last: true })
  ],
  9: [I("moi_loi_sau_cung", "Cho bị cáo nói lời sau cùng", "invite", true, ["324"], { ai: 1 })],
  10: [
    I("vao_nghi_an", "Vào phòng nghị án", "item", true, ["326"], { first: true }),
    I("y_kien_hoi_tham", "Nghe ý kiến Hội thẩm về bản nháp quyết định", "invite", false, ["326"], { ai: 1, template: null }),
    I("chot_quyet_dinh", "Chốt quyết định", "decide", true, ["326"])
  ],
  11: [I("tuyen_an", "Tuyên án", "pronounce", true, ["327"], { ai: 1 })]
};
const RETURN_ITEMS = [
  I("hoi_lai", "Hỏi lại (tối đa 3 câu)", "ask", false, ["323"], { ai: 1 }),
  I("moi_ksv_hoi", "Mời Kiểm sát viên hỏi (tối đa 3 câu)", "invite", false, ["307"], { ai: 1 }),
  I("moi_ls_hoi", "Mời luật sư hỏi (tối đa 3 câu)", "invite", false, ["307"], { ai: 1 }),
  I("ket_thuc_xet_hoi", "Kết thúc xét hỏi", "item", true, ["318"], { last: true })
];
const LAY = ["BI_CAO", "BI_HAI", "NLC_1"];
const TITLES = ["Thư ký báo cáo sự có mặt", "Khai mạc phiên tòa", "Công bố cáo trạng", "Hội đồng xét xử xét hỏi", "Kiểm sát viên và luật sư xét hỏi",
  "Kiểm sát viên luận tội", "Luật sư bào chữa", "Tranh luận, đối đáp", "Bị cáo nói lời sau cùng", "Nghị án", "Tuyên án"];
const INVITED = { moi_cong_bo_cao_trang: ["KSV"], moi_hoi_tham_hoi: ["HOI_THAM_1"], moi_ksv_hoi: ["KSV"], moi_ls_hoi: ["LUAT_SU"], moi_luan_toi: ["KSV"],
  moi_bao_chua: ["LUAT_SU"], moi_bi_hai_trinh_bay: ["BI_HAI"], hoi_bi_cao_bo_sung: ["BI_CAO"], moi_doi_dap: ["KSV", "LUAT_SU"], vong_2: ["KSV", "LUAT_SU"],
  moi_loi_sau_cung: ["BI_CAO"] };
const CODE_ANSWERS = { kiem_tra_can_cuoc: ["BI_CAO"], hoi_thay_doi: ["KSV", "LUAT_SU", "BI_CAO"], cam_doan_nlc: ["NLC_1"], hoi_yeu_cau: ["KSV", "LUAT_SU", "BI_CAO"] };

const template = (item) => (item.template !== undefined ? item.template : item.kind === "decide" || item.kind === "pronounce" ? null : `${CHAIR_MARK}: ${item.label.toLowerCase()}.`);

// The server-side session. `seq` continues after the fixture transcript.
export function newChair(o = {}) {
  return { step: 1, version: 20, done: [], questions: 0, remarks: 0, rounds: 0, returned: false, inReturn: false, seq: 200,
    draft: null, draftAt: null, assessor: null, decided: false, preview: null, completed: false, slowMs: 0, ...o };
}

const items = (c) => (c.step === 5 && c.inReturn ? RETURN_ITEMS : STEP_ITEMS[c.step] ?? []).filter((i) => !(i.kind === "return" && c.returned));
const missing = (c) => items(c).filter((i) => i.required && !c.done.includes(i.key)).map((i) => i.key);
const questioning = (c) => c.step === 4 || (c.step === 5 && c.inReturn);
const cap = (c) => (c.inReturn ? 3 : 10);

function askTo(c, item) {
  if (!questioning(c) || c.questions >= cap(c)) return [];
  if (item?.key === "hoi_bi_cao") return ["BI_CAO"];
  if (item?.key === "hoi_nguoi_khac") return LAY.filter((p) => p !== "BI_CAO");
  return LAY;
}
function available(c, item) {
  const done = c.done;
  if (done.includes(item.key) && item.kind !== "ask") return false;
  const list = items(c);
  if (list.some((i) => i.first && !done.includes(i.key) && i.key !== item.key)) return false;
  if (item.last && list.some((i) => i.required && !done.includes(i.key) && i.key !== item.key)) return false;
  if (item.after.some((key) => !done.includes(key))) return false;
  if (item.kind === "ask") return askTo(c, item).length > 0;
  if (item.kind === "return") return !done.includes("ket_thuc_tranh_luan") && c.rounds >= 1;
  if (item.kind === "decide" || item.key === "y_kien_hoi_tham") return done.includes("vao_nghi_an") && !c.decided;
  if (item.kind === "pronounce") return c.decided && !c.completed;
  return true;
}
const remarkOk = (c) => c.step >= 2 && c.step <= 9 && c.remarks < 5 && !(c.step === 2 && !c.done.includes("khai_mac"));
function remarkTo(c) {
  if (!remarkOk(c)) return [];
  const people = ["KSV", "LUAT_SU", ...LAY];
  return c.step === 9 && c.done.includes("moi_loi_sau_cung") ? people.filter((p) => p !== "BI_CAO") : people;
}
const advanceTarget = (c) => (c.step === 5 && c.inReturn ? 8 : c.step + 1);

function allowed(c) {
  if (c.completed) return [];
  if (c.step === 1) return ["advance:2"];
  // The route drops "decide" and the assessors' invitation while no clean draft is stored.
  const clean = c.draft !== null && decisionCheck(c.draft).errors.length === 0;
  const avail = items(c).filter((i) => available(c, i) && (clean || !(i.kind === "decide" || i.key === "y_kien_hoi_tham")));
  const out = [];
  const keys = (kind) => avail.filter((i) => i.kind === kind).map((i) => i.key);
  if (keys("item").length) out.push(`item:${keys("item").join("|")}`);
  if (avail.some((i) => i.kind === "ask") && askTo(c).length) out.push(`ask:${askTo(c).join("|")}`);
  if (keys("invite").length) out.push(`invite:${keys("invite").join("|")}`);
  if (remarkOk(c)) out.push("remark");
  if (avail.some((i) => i.kind === "return")) out.push("return_to_questioning");
  if (avail.some((i) => i.kind === "decide")) out.push("decide");
  if (avail.some((i) => i.kind === "pronounce")) out.push(c.preview ? "pronounce" : "prepare_pronouncement");
  if (c.step < 11 && missing(c).length === 0) out.push(`advance:${advanceTarget(c)}`);
  return out;
}

function presidingView(c) {
  if (c.step === 1) return null;
  return {
    step: c.step,
    items: items(c).map((i) => ({ key: i.key, label: i.label, kind: i.kind, required: i.required, done: c.done.includes(i.key), available: available(c, i),
      template: template(i), basis: i.basis, ai_calls: i.ai, note: i.note })),
    missing_required: missing(c),
    counters: { questions_left: questioning(c) ? Math.max(0, cap(c) - c.questions) : 0, remarks_left: c.step <= 9 ? 5 - c.remarks : 0, debate_rounds: c.rounds },
    ask_addressees: askTo(c), remark_addressees: remarkTo(c),
    limits: { item: { min: 1, max: 3000 }, ask: { min: 1, max: 1500 }, remark: { min: 1, max: 1500 }, reasoning: { min: 200, max: 2000 } },
    return_available: allowed(c).includes("return_to_questioning"), returned: c.returned, in_return: c.inReturn, templates_reviewed: false
  };
}

export function chairState(c, o = {}) {
  return baseState({ current_step: c.step, step_title: TITLES[c.step - 1], version: c.version, allowed_actions: allowed(c), text_limits: null,
    presiding: presidingView(c), decision: decisionView(c), ...(c.completed ? { status: "completed", awaiting: "none" } : {}), ...o });
}

// --- Steps 10-11: the student's own decision ---------------------------------------------------------
export const ASSESSOR_MARK = "Ý kiến Hội thẩm mẫu";
export const PRONOUNCE_MARK = "Lời tuyên mẫu do hệ thống soạn";
export const ORDER_NOTE = "Mô phỏng khác thứ tự của khoản 1 Điều 326 Bộ luật Tố tụng hình sự: theo luật, Hội thẩm biểu quyết trước, Thẩm phán biểu quyết sau cùng. Ở đây Hội thẩm chỉ góp ý trên bản nháp của Chủ tọa và không biểu quyết thay.";
const HOI_THAM_2 = "Lâm Văn Phúc";
const BLHS = "Bộ luật Hình sự";
const BLTTHS = "Bộ luật Tố tụng hình sự";
const FRAMES = {
  1: { prison_min_months: 6, prison_max_months: 36, non_custodial_max_months: 36, fine_as_main: false },
  2: { prison_min_months: 24, prison_max_months: 84, non_custodial_max_months: null, fine_as_main: false },
  3: { prison_min_months: 84, prison_max_months: 180, non_custodial_max_months: null, fine_as_main: false },
  4: null
};
export const decisionForm = () => ({
  dieu: "173", charged_khoan: "1", charged_diem: [], khoan: ["1", "2", "3", "4"],
  diem: { 1: [], 2: ["a", "b", "c", "d"], 3: ["a", "b"], 4: ["a", "b"] }, frames: FRAMES,
  mitigating_points: { 1: ["b", "i", "s"], 2: [] }, aggravating_points: { 1: ["g", "h"] },
  penalty_types: ["tu", "cai_tao_khong_giam_giu", "phat_tien", "khong"], facts: ["F1"], exhibits: ["E1"],
  dispositions: ["tra_lai", "tich_thu_sung_ngan_sach", "tich_thu_tieu_huy", "luu_ho_so"],
  civil_claim_vnd: 2000000, compensation_vnd: null, reasoning_limits: { min: 200, max: 2000 }
});

// A subset of trial_chair_decision.check_decision for Điều 173, khoản 1 charged, exhibit E1, claim 2.000.000.
export function decisionCheck(d) {
  const errors = [];
  const warnings = [];
  const err = (code, field, message, ...basis) => errors.push({ code, field, message, basis });
  const warn = (code, field, message, ...basis) => warnings.push({ code, field, message, basis });
  for (const [label, dieu, list] of [["mitigating", "51", d.mitigating], ["aggravating", "52", d.aggravating]]) {
    list.forEach((item, index) => {
      const points = (label === "mitigating" ? decisionForm().mitigating_points : decisionForm().aggravating_points)[item.khoan];
      if (points === undefined || (points.length > 0 && !points.includes(item.diem))) err("circumstance_unknown", `${label}[${index}]`, `Điểm ${item.diem || "(trống)"} khoản ${item.khoan} Điều ${dieu} ${BLHS} không tồn tại.`, `Điều ${dieu} ${BLHS}`);
      if (item.fact_ids.length === 0) err("circumstance_no_fact", `${label}[${index}]`, "Mỗi tình tiết phải gắn với ít nhất một sự việc trong hồ sơ.", `khoản 2 Điều 326 ${BLTTHS}`);
    });
  }
  if (d.mitigating.some((m) => m.khoan === "2")) warn("mitigating_other_reason", "mitigating", "Tình tiết giảm nhẹ theo khoản 2 Điều 51 phải được ghi rõ lý do trong bản án: nêu lý do trong phần nhận định.", `khoản 2 Điều 51 ${BLHS}`);
  const length = d.reasoning_summary.trim().length;
  if (length < 200 || length > 2000) err("reasoning_length", "reasoning_summary", `Nhận định cần từ 200 đến 2000 ký tự (hiện có ${length}).`, `điểm d khoản 2 Điều 260 ${BLTTHS}`);
  if (!d.exhibits.some((x) => x.evidence_id === "E1")) err("exhibit_missing", "exhibits", "Chưa quyết định xử lý vật chứng: E1.", `điểm e khoản 3 Điều 326 ${BLTTHS}`, `khoản 1 Điều 106 ${BLTTHS}`);
  if (d.exhibits.some((x) => x.disposition.startsWith("tich_thu"))) warn("exhibit_confiscated_property", "exhibits", "Nếu vật chứng là tài sản bị chiếm đoạt thì không tịch thu mà trả lại cho chủ sở hữu hoặc người quản lý hợp pháp.", `khoản 2 Điều 47 ${BLHS}`, `khoản 2, khoản 3 Điều 106 ${BLTTHS}`);
  if (d.fine_vnd !== null && d.penalty_type !== "phat_tien") err("fine_not_main", "fine_vnd", "Chỉ ghi số tiền phạt khi hình phạt chính là phạt tiền.", `khoản 1 Điều 35 ${BLHS}`);
  const civil = d.civil_amount_vnd ?? 0;
  if (civil > 2000000) warn("civil_over_claim", "civil_amount_vnd", "Số tiền bồi thường lớn hơn số tiền bị hại yêu cầu trong hồ sơ.", `Điều 30 ${BLTTHS}`, `khoản 1 Điều 48 ${BLHS}`);
  if (d.defendant_pays_civil_fee && civil <= 0) warn("civil_fee_without_claim", "defendant_pays_civil_fee", "Không có khoản bồi thường nào được quyết định mà vẫn chọn án phí dân sự.", `khoản 2 Điều 135 ${BLTTHS}`);
  if (!d.guilty) {
    if (d.penalty_type !== "khong" || d.suspended) err("acquittal_with_penalty", "penalty_type", "Tuyên không phạm tội thì không có hình phạt và không có án treo.", `điểm c, d khoản 3 Điều 326 ${BLTTHS}`);
    if (d.defendant_pays_criminal_fee) err("acquittal_criminal_fee", "defendant_pays_criminal_fee", "Bị cáo không có tội thì không phải chịu án phí hình sự.", `khoản 2 Điều 136 ${BLTTHS}`);
    return { errors, warnings, flags: [] };
  }
  if (d.dieu !== "173") {
    err("charge_article", "dieu", `Chỉ được xét xử theo Điều 173 ${BLHS} mà Viện kiểm sát đã truy tố.`, `khoản 1 Điều 298 ${BLTTHS}`);
    return { errors, warnings, flags: [] };
  }
  if (!["1", "2", "3", "4"].includes(d.khoan)) {
    err("khoan_unknown", "khoan", `Khoản ${d.khoan} Điều 173 ${BLHS} không phải khoản quy định khung hình phạt của tội này.`, `Điều 173 ${BLHS}`);
    return { errors, warnings, flags: [] };
  }
  if (Number(d.khoan) > 1) warn("khoan_heavier", "khoan", `Khoản ${d.khoan} nặng hơn khoản 1 mà Viện kiểm sát đã truy tố. Khoản 2 Điều 298 cho phép xét xử theo khoản khác trong cùng điều luật; kiểm tra lại căn cứ.`, `khoản 2 Điều 298 ${BLTTHS}`, `khoản 3 Điều 298 ${BLTTHS}`);
  if (d.penalty_type === "khong") {
    err("conviction_without_penalty", "penalty_type", "Đã tuyên có tội thì phải có hình phạt (miễn hình phạt không thuộc phạm vi mô phỏng).", `điểm d khoản 3 Điều 326 ${BLTTHS}`, `Điều 59 ${BLHS}`);
    return { errors, warnings, flags: [] };
  }
  const frame = FRAMES[d.khoan];
  const strong = d.mitigating.filter((m) => m.khoan === "1").length;
  if (d.applies_dieu_54 && strong < 2) err("dieu54_conditions", "applies_dieu_54", "Áp dụng Điều 54 cần ít nhất hai tình tiết giảm nhẹ tại khoản 1 Điều 51.", `khoản 1 Điều 54 ${BLHS}`);
  if (frame === null) warn("penalty_unchecked", "penalty_type", "Hệ thống chưa kiểm được khung hình phạt của khoản này.", `Điều 173 ${BLHS}`);
  const months = d.penalty_months;
  if (d.penalty_type === "tu") {
    if (months === null || months <= 0) err("penalty_months", "penalty_months", "Cần nhập số tháng tù lớn hơn 0.", `khoản 1 Điều 38 ${BLHS}`);
    else {
      if (months < 3 || months > 240) err("prison_general_range", "penalty_months", "Tù có thời hạn từ 03 tháng đến 20 năm.", `khoản 1 Điều 38 ${BLHS}`);
      if (frame && months > frame.prison_max_months) err("above_frame", "penalty_months", `Mức tù ${months} tháng vượt mức cao nhất của khung (${frame.prison_min_months}-${frame.prison_max_months} tháng tù).`, `Điều 173 ${BLHS}`);
      else if (frame && months < frame.prison_min_months && !d.applies_dieu_54) err("below_frame", "penalty_months", `Mức tù ${months} tháng dưới mức thấp nhất của khung (${frame.prison_min_months}-${frame.prison_max_months} tháng tù) mà không áp dụng Điều 54.`, `khoản 1 Điều 54 ${BLHS}`);
    }
  } else if (d.penalty_type === "cai_tao_khong_giam_giu") {
    if (months === null || months < 6 || months > 36) err("non_custodial_range", "penalty_months", "Cải tạo không giam giữ từ 06 tháng đến 03 năm.", `khoản 1 Điều 36 ${BLHS}`);
  } else if (d.penalty_type === "phat_tien") {
    if (d.fine_vnd === null || d.fine_vnd < 1000000) err("fine_min", "fine_vnd", "Mức phạt tiền không được thấp hơn 1.000.000 đồng.", `khoản 3 Điều 35 ${BLHS}`);
    if (!(d.khoan === "1" && d.applies_dieu_54 && strong >= 2)) err("fine_not_in_frame", "penalty_type", "Khung hình phạt của khoản này không có phạt tiền là hình phạt chính.", `khoản 1 Điều 35 ${BLHS}`, `khoản 3 Điều 54 ${BLHS}`);
  }
  if (d.suspended) {
    if (d.penalty_type !== "tu" || (months ?? 0) > 36) err("suspended_prison", "suspended", "Án treo chỉ áp dụng khi xử phạt tù không quá 03 năm.", `khoản 1 Điều 65 ${BLHS}`);
    if (d.probation_months === null || d.probation_months < 12 || d.probation_months > 60) err("probation_range", "probation_months", "Thời gian thử thách của án treo từ 01 năm đến 05 năm.", `khoản 1 Điều 65 ${BLHS}`);
    if (d.mitigating.length === 0) warn("suspended_without_mitigating", "suspended", "Cho hưởng án treo căn cứ vào nhân thân và các tình tiết giảm nhẹ; quyết định chưa nêu tình tiết giảm nhẹ nào.", `khoản 1 Điều 65 ${BLHS}`);
  } else if (d.probation_months !== null) {
    err("probation_without_suspension", "probation_months", "Chỉ ấn định thời gian thử thách khi cho hưởng án treo.", `khoản 1 Điều 65 ${BLHS}`);
  }
  return { errors, warnings, flags: [] };
}

function decisionView(c) {
  if (c.step < 10) return null;
  return {
    draft: c.draft, updated_at: c.draftAt, check: c.draft ? decisionCheck(c.draft) : null, locked: c.decided,
    assessor_opinions: c.assessor?.opinions ?? null, assessor_draft_updated_at: c.assessor?.draftAt ?? null, assessor_order_note: ORDER_NOTE,
    pronouncement_preview: c.preview, form: decisionForm()
  };
}

const DECISION_KEYS = ["guilty", "dieu", "khoan", "diem", "penalty_type", "penalty_months", "fine_vnd", "suspended", "probation_months", "applies_dieu_54",
  "mitigating", "aggravating", "civil_amount_vnd", "reasoning_summary", "exhibits", "defendant_pays_criminal_fee", "defendant_pays_civil_fee"];
const DECISION_REQUIRED = ["guilty", "dieu", "khoan", "diem", "penalty_type", "mitigating", "aggravating", "reasoning_summary"];
const schemaOk = (body) => {
  const d = body?.decision;
  return body && Object.keys(body).every((k) => ["expected_version", "decision"].includes(k)) && Number.isInteger(body.expected_version) && d
    && Object.keys(d).every((k) => DECISION_KEYS.includes(k)) && DECISION_REQUIRED.every((k) => k in d)
    && ["tu", "cai_tao_khong_giam_giu", "phat_tien", "khong"].includes(d.penalty_type)
    && (d.exhibits ?? []).every((x) => decisionForm().dispositions.includes(x.disposition) && Object.keys(x).sort().join() === "disposition,evidence_id");
};

// PUT /decision (contract 3.11) over `c`, keeping `world` in sync. `bodies` collects what was sent.
export function chairDecisionPut(world, c, bodies) {
  return (route, body) => {
    bodies.push(body);
    const conflict = (code) => fulfillError(route, 409, code, { state: chairState(c) });
    if (world.role !== "chu_toa") return conflict("trial_not_presiding");
    if (!schemaOk(body)) return fulfillError(route, 422, "validation_error");
    if (c.completed) return conflict("trial_not_active");
    if (body.expected_version !== c.version) return conflict("trial_version_mismatch");
    if (c.decided) return conflict("trial_decision_locked");
    if (c.step !== 10 || !c.done.includes("vao_nghi_an")) return conflict("trial_action_not_allowed");
    const d = body.decision;
    c.draft = { penalty_months: null, fine_vnd: null, suspended: false, probation_months: null, applies_dieu_54: false, civil_amount_vnd: null, exhibits: [],
      defendant_pays_criminal_fee: false, defendant_pays_civil_fee: false, ...d };
    c.draftAt = new Date(Date.UTC(2026, 9, 31, 1, c.version % 60)).toISOString();
    c.version += 1;
    world.state = chairState(c);
    return fulfillJson(route, 200, { state: world.state });
  };
}

const PRONOUNCEMENT = [
  `${PRONOUNCE_MARK}. Nhân danh nước Cộng hòa xã hội chủ nghĩa Việt Nam, Tòa án nhân dân khu vực 1, tỉnh X tuyên xử (văn bản mẫu):`,
  "Về tội danh: Tuyên bố bị cáo Trần Đức Hùng phạm tội trộm cắp tài sản (văn bản mẫu).",
  "Về án phí: Bị cáo chịu án phí hình sự sơ thẩm theo quy định của pháp luật (văn bản mẫu)."
].join("\n\n");

const chairLine = (c, text, key, o = {}) => utt(++c.seq, c.step, "CHU_TOA", text, { is_user: true, speaker_role: "Chủ tọa", procedure_item: key, ...o });
const aiLine = (c, id, text, o = {}) => utt(++c.seq, c.step, id, text, { procedure_item: null, ...o });
const answer = (id) => `${CHAIR_MARK}: ${participants[id]?.role ?? id} trả lời.`;

const FIELDS = {
  advance: ["target_step"], continue: [], item: ["item", "text"], invite: ["item", "text"], ask: ["addressee", "text"],
  remark: ["text", "addressee"], return_to_questioning: ["text"], decide: [], prepare_pronouncement: [], pronounce: []
};

// Applies one /turn body to `c`. Returns { lines } (accepted) or { status, code, extra } (refused).
export function applyChair(c, body) {
  const { expected_step: step, expected_version: version, action, ...rest } = body;
  const allowedFields = FIELDS[action];
  if (allowedFields === undefined) return { status: 409, code: "trial_action_not_allowed" };
  if (Object.keys(rest).some((key) => !allowedFields.includes(key)) || (rest.text !== undefined && rest.text.length > 6000)) return { status: 422, code: "validation_error" };
  if (step !== c.step) return { status: 409, code: "trial_step_mismatch" };
  if (version !== c.version) return { status: 409, code: "trial_version_mismatch" };
  const lines = [];
  const bump = () => { c.version += 1; };
  const tooLong = (limit) => (rest.text ?? "").trim().length > limit;

  if (c.completed) return { status: 409, code: "trial_not_active" };
  if (action === "advance") {
    if (c.step === 11) return { status: 409, code: "trial_action_not_allowed" };
    if (rest.target_step !== advanceTarget(c)) return { status: 409, code: "trial_skip_not_allowed" };
    if (missing(c).length) return { status: 409, code: "trial_procedure_incomplete", extra: { missing_items: missing(c) } };
    Object.assign(c, { step: advanceTarget(c), done: [], questions: 0, remarks: 0, rounds: 0, inReturn: false });
    bump();
    return { lines };
  }
  if (action === "item" || action === "invite") {
    const item = items(c).find((i) => i.key === rest.item && i.kind === action);
    if (!item) return { status: 409, code: "trial_item_not_available", extra: { item: rest.item } };
    if (c.done.includes(item.key)) return { status: 409, code: "trial_item_done", extra: { item: rest.item } };
    if (!available(c, item)) return { status: 409, code: "trial_item_not_available", extra: { item: rest.item } };
    if (tooLong(3000)) return { status: 409, code: "trial_text_too_long" };
    if (item.key === "y_kien_hoi_tham") {
      // Contract 5.4: comments on the saved draft, kept in state only - never an utterance.
      if (c.draft === null) return { status: 409, code: "trial_decision_missing" };
      const errors = decisionCheck(c.draft).errors;
      if (errors.length) return { status: 409, code: "trial_decision_invalid", extra: { errors: errors.map((e) => e.code) } };
      c.assessor = { draftAt: c.draftAt, opinions: [
        { speaker_id: "HOI_THAM_1", speaker_name: participants.HOI_THAM_1.name, agrees: true, text: `${ASSESSOR_MARK} 1: đồng ý với mức hình phạt của bản nháp.` },
        { speaker_id: "HOI_THAM_2", speaker_name: HOI_THAM_2, agrees: false, text: `${ASSESSOR_MARK} 2: đề nghị cân nhắc thêm tình tiết giảm nhẹ.` }] };
      c.done.push(item.key);
      bump();
      return { lines, status: "Hội thẩm đang góp ý trên bản nháp..." };
    }
    lines.push(chairLine(c, rest.text?.trim() ? rest.text : template(item), item.key));
    for (const id of action === "invite" ? INVITED[item.key] ?? [] : CODE_ANSWERS[item.key] ?? []) lines.push(aiLine(c, id, answer(id)));
    c.done.push(item.key);
    if (item.key === "moi_doi_dap" || item.key === "vong_2") c.rounds += 1;
    bump();
    return { lines };
  }
  if (action === "ask") {
    if (!askTo(c).length) return { status: 409, code: questioning(c) ? "trial_turn_limit" : "trial_action_not_allowed" };
    if (!askTo(c).includes(rest.addressee)) return { status: 409, code: "trial_missing_addressee" };
    if (!rest.text?.trim()) return { status: 409, code: "trial_empty_text" };
    if (tooLong(1500)) return { status: 409, code: "trial_text_too_long" };
    const key = c.inReturn ? "hoi_lai" : rest.addressee === "BI_CAO" ? "hoi_bi_cao" : "hoi_nguoi_khac";
    lines.push(chairLine(c, rest.text, key, { addressee: rest.addressee }), aiLine(c, rest.addressee, answer(rest.addressee)));
    if (!c.done.includes(key)) c.done.push(key);
    c.questions += 1;
    bump();
    return { lines };
  }
  if (action === "remark") {
    if (!remarkOk(c)) return { status: 409, code: c.step >= 2 && c.step <= 9 ? "trial_turn_limit" : "trial_action_not_allowed" };
    if (rest.addressee !== undefined && !remarkTo(c).includes(rest.addressee)) return { status: 409, code: "trial_missing_addressee" };
    if (!rest.text?.trim()) return { status: 409, code: "trial_empty_text" };
    if (tooLong(1500)) return { status: 409, code: "trial_text_too_long" };
    lines.push(chairLine(c, rest.text, "remark", { addressee: rest.addressee ?? null }));
    if (rest.addressee) lines.push(aiLine(c, rest.addressee, answer(rest.addressee)));
    c.remarks += 1;
    bump();
    return { lines };
  }
  if (action === "return_to_questioning") {
    if (c.step !== 8) return { status: 409, code: "trial_return_not_allowed" };
    if (c.returned) return { status: 409, code: "trial_return_used" };
    const item = items(c).find((i) => i.kind === "return");
    if (!item || !available(c, item)) return { status: 409, code: "trial_return_not_allowed" };
    lines.push(chairLine(c, rest.text?.trim() ? rest.text : template(item), "tro_lai_xet_hoi"));
    Object.assign(c, { step: 5, done: [], questions: 0, remarks: 0, rounds: 0, returned: true, inReturn: true });
    bump();
    return { lines };
  }
  if (action === "decide") {
    if (c.step !== 10 || !available(c, items(c).find((i) => i.kind === "decide"))) return { status: 409, code: c.decided ? "trial_item_done" : "trial_item_not_available", extra: { item: "chot_quyet_dinh" } };
    if (c.draft === null) return { status: 409, code: "trial_decision_missing" };
    const errors = decisionCheck(c.draft).errors;
    if (errors.length) return { status: 409, code: "trial_decision_invalid", extra: { errors: errors.map((e) => e.code) } };
    c.decided = true;
    c.done.push("chot_quyet_dinh");
    bump();
    return { lines };
  }
  if (action === "prepare_pronouncement") {
    if (c.step !== 11 || !c.decided || c.preview) return { status: 409, code: "trial_action_not_allowed" };
    c.preview = PRONOUNCEMENT;
    bump();
    return { lines, status: "Đang soạn lời tuyên án..." };
  }
  if (action === "pronounce") {
    if (c.step !== 11 || !c.preview) return { status: 409, code: "trial_pronouncement_missing" };
    lines.push(chairLine(c, c.preview, "tuyen_an"));
    c.done.push("tuyen_an");
    c.completed = true;
    bump();
    return { lines, after: "Đang lập biên bản..." };
  }
  return { status: 409, code: "trial_action_not_allowed" };
}

// A /turn handler over `c` that keeps `world` (GET /{id}) in sync. `bodies` collects what was sent.
// `c.slowMs` holds the answer back (an AI part still running) so a check can see the wait and cancel it.
export function chairTurn(world, c, bodies) {
  return async (route, body) => {
    bodies.push(body);
    const outcome = applyChair(c, body);
    if (typeof outcome.status === "number") {
      return fulfillError(route, outcome.status, outcome.code, outcome.status === 409 ? { fields: outcome.extra, state: chairState(c) } : {});
    }
    world.state = chairState(c);
    world.utterances.push(...outcome.lines);
    if (c.slowMs > 0) await new Promise((resolve) => setTimeout(resolve, c.slowMs));
    const events = (outcome.status ? sseEvent("status", { message: outcome.status }) : "") + outcome.lines.map((u) => sseEvent("utterance", u)).join("")
      + (outcome.after ? sseEvent("status", { message: outcome.after }) : "") + sseEvent("state", world.state) + sseEvent("done", {});
    try {
      await fulfillSse(route, events);
    } catch {
      // the page stopped waiting (cancel) - the server-side work is done all the same
    }
  };
}

