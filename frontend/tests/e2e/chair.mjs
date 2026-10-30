// Fake presiding-judge backend (contract 5.4) for the mocked browser suite: the same checklist,
// order rules, counters, Điều 323 return and 409 codes as backend/app/services/trial_presiding.py,
// for steps 1-10 and one case shape (victim present, one witness). Every line is invented.
import { participants, utt } from "./fixtures.mjs";
import { baseState, fulfillError, fulfillSse, sseEvent } from "./lib.mjs";

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
    I("y_kien_hoi_tham", "Nghe ý kiến Hội thẩm về bản nháp quyết định", "invite", false, ["326"], { ai: 1 }),
    I("chot_quyet_dinh", "Chốt quyết định", "decide", true, ["326"])
  ]
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

const template = (item) => item.template ?? (item.kind === "decide" ? null : `${CHAIR_MARK}: ${item.label.toLowerCase()}.`);

// The server-side session. `seq` continues after the fixture transcript.
export function newChair(o = {}) {
  return { step: 1, version: 20, done: [], questions: 0, remarks: 0, rounds: 0, returned: false, inReturn: false, seq: 200, ...o };
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
  if (item.kind === "decide" || item.key === "y_kien_hoi_tham") return done.includes("vao_nghi_an");
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
  if (c.step === 1) return ["advance:2"];
  const avail = items(c).filter((i) => available(c, i));
  const out = [];
  const keys = (kind) => avail.filter((i) => i.kind === kind).map((i) => i.key);
  if (keys("item").length) out.push(`item:${keys("item").join("|")}`);
  if (avail.some((i) => i.kind === "ask") && askTo(c).length) out.push(`ask:${askTo(c).join("|")}`);
  if (keys("invite").length) out.push(`invite:${keys("invite").join("|")}`);
  if (remarkOk(c)) out.push("remark");
  if (avail.some((i) => i.kind === "return")) out.push("return_to_questioning");
  if (avail.some((i) => i.kind === "decide")) out.push("decide");
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
    presiding: presidingView(c), decision: null, ...o });
}

const chairLine = (c, text, key, o = {}) => utt(++c.seq, c.step, "CHU_TOA", text, { is_user: true, speaker_role: "Chủ tọa", procedure_item: key, ...o });
const aiLine = (c, id, text, o = {}) => utt(++c.seq, c.step, id, text, { procedure_item: null, ...o });
const answer = (id) => `${CHAIR_MARK}: ${participants[id]?.role ?? id} trả lời.`;

const FIELDS = {
  advance: ["target_step"], continue: [], item: ["item", "text"], invite: ["item", "text"], ask: ["addressee", "text"],
  remark: ["text", "addressee"], return_to_questioning: ["text"]
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

  if (action === "advance") {
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
  return { status: 409, code: "trial_action_not_allowed" };
}

// A /turn handler over `c` that keeps `world` (GET /{id}) in sync. `bodies` collects what was sent.
export function chairTurn(world, c, bodies) {
  return (route, body) => {
    bodies.push(body);
    const outcome = applyChair(c, body);
    if (outcome.status) {
      return fulfillError(route, outcome.status, outcome.code, outcome.status === 409 ? { fields: outcome.extra, state: chairState(c) } : {});
    }
    world.state = chairState(c);
    world.utterances.push(...outcome.lines);
    return fulfillSse(route, outcome.lines.map((u) => sseEvent("utterance", u)).join("") + sseEvent("state", world.state) + sseEvent("done", {}));
  };
}

