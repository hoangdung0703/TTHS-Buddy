// Unit tests for src/lib/trialRules.ts. No test framework: Node's built-in runner, which loads the
// .ts file directly (type stripping, Node >= 23.6). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  askAddresseesForItem,
  chairItemActionable,
  chairItemLabel,
  chairOneClickTemplate,
  chairTargetOptions,
  chairTextLimits,
  hasPresidingAction,
  isChairRole,
  parseChairActions,
  resolveChairTarget,
  validateChairText,
  applyClerkDraft,
  chairInvitation,
  endSlotLabel,
  isDefendantRole,
  legalBasisArticle,
  canFinalizeClerkDraft,
  caseCreationBlockedReason,
  clerkNoticeHint,
  clerkSectionLength,
  clerkSubsection,
  isClerkRole,
  usesObserverControls,
  composerMode,
  GLOBAL_DAILY_LIMIT_MESSAGE,
  isCaseLimitCode,
  isObserverRole,
  isResyncConflict,
  mergeUtterances,
  messageForTrialError,
  parseAllowedActions,
  parseTrialErrorBody,
  stepHint,
  TRIAL_ROLE_LABELS,
  textLimitsForState,
  textLimitsForStep,
  USAGE_LOG_UNAVAILABLE_MESSAGE,
  USAGE_UNAVAILABLE_NOTICE,
  validateTrialText
} from "../src/lib/trialRules.ts";

const baseState = {
  session_id: "s",
  current_step: 5,
  step_title: "Kiểm sát viên và luật sư xét hỏi",
  status: "active",
  awaiting: "user",
  allowed_actions: [],
  version: 3
};

test("feature flag off: 404 {detail: Not Found} is featureDisabled", () => {
  const parsed = parseTrialErrorBody(404, JSON.stringify({ detail: "Not Found" }));
  assert.equal(parsed.featureDisabled, true);
});

test("404 Trial not found (app envelope) is NOT the feature flag", () => {
  const parsed = parseTrialErrorBody(404, JSON.stringify({ error: { code: "http_error", message: "Trial not found" } }));
  assert.equal(parsed.featureDisabled, false);
  assert.equal(parsed.code, "http_error");
});

test("409 carries code and state; version mismatch re-syncs", () => {
  const state = { ...baseState, version: 9 };
  const parsed = parseTrialErrorBody(409, JSON.stringify({ error: { code: "trial_version_mismatch", message: "x" }, state }));
  assert.equal(parsed.code, "trial_version_mismatch");
  assert.deepEqual(parsed.state, state);
  assert.equal(isResyncConflict(parsed.code), true);
});

test("409 trial_guard_exhausted is not a silent re-sync and has its own message", () => {
  assert.equal(isResyncConflict("trial_guard_exhausted"), false);
  assert.match(messageForTrialError({ status: 409, code: "trial_guard_exhausted" }), /không thể tiếp tục/);
});

test("non-JSON body does not throw", () => {
  const parsed = parseTrialErrorBody(500, "<html>");
  assert.equal(parsed.code, null);
  assert.equal(parsed.featureDisabled, false);
});

test("429 limit codes have Vietnamese messages", () => {
  assert.match(messageForTrialError({ status: 429, code: "trial_daily_case_limit" }), /ngày mai/);
  assert.match(messageForTrialError({ status: 429, code: "trial_active_session_limit" }), /dở dang/);
});

test("parseAllowedActions: speak with addressees, end_slot, advance, continue", () => {
  const parsed = parseAllowedActions(["speak:BI_CAO|BI_HAI|NLC_1", "end_slot"]);
  assert.deepEqual(parsed.addressees, ["BI_CAO", "BI_HAI", "NLC_1"]);
  assert.equal(parsed.canSpeak, true);
  assert.equal(parsed.canEndSlot, true);
  assert.equal(parseAllowedActions(["advance:6"]).advanceTo, 6);
  assert.equal(parseAllowedActions(["continue"]).canContinue, true);
});

test("composerMode follows the server state only", () => {
  assert.equal(composerMode({ ...baseState, allowed_actions: ["speak"] }), "speak");
  assert.equal(composerMode({ ...baseState, allowed_actions: ["advance:6"] }), "advance");
  assert.equal(composerMode({ ...baseState, awaiting: "ai", allowed_actions: ["continue"] }), "paused");
  // Guard fuse: awaiting ai with no actions -> only abandon/delete.
  assert.equal(composerMode({ ...baseState, awaiting: "ai", allowed_actions: [] }), "exhausted");
  assert.equal(composerMode({ ...baseState, status: "completed", awaiting: "none" }), "finished");
  assert.equal(composerMode({ ...baseState, status: "abandoned", awaiting: "none" }), "finished");
});

test("text_limits from the server state win over the step table", () => {
  // Server says 50..900 at step 6: the client must follow it, not its own 300..6000.
  const limits = textLimitsForState({ current_step: 6, text_limits: { min: 50, max: 900 } });
  assert.deepEqual([limits.min, limits.max, limits.label], [50, 900, "Bản luận tội"]);
  assert.match(validateTrialText("a".repeat(901), limits), /900/);
  assert.match(validateTrialText("a".repeat(49), limits), /ít nhất 50/);
  assert.equal(validateTrialText("a".repeat(50), limits), null);
});

test("missing or malformed text_limits falls back to the step table", () => {
  for (const text_limits of [undefined, null, {}, { min: 0, max: 10 }, { min: 10, max: 5 }, { min: "1", max: 1500 }]) {
    const limits = textLimitsForState({ current_step: 6, text_limits });
    assert.deepEqual([limits.min, limits.max], [300, 6000], JSON.stringify(text_limits));
  }
  assert.deepEqual(Object.values(textLimitsForState({ current_step: 5 })).slice(0, 2), [1, 1500]);
});

test("fallback length limits per step match the backend table", () => {
  assert.deepEqual([textLimitsForStep(2).min, textLimitsForStep(2).max], [1, 1500]);
  assert.deepEqual([textLimitsForStep(3).min, textLimitsForStep(3).max], [100, 6000]);
  assert.deepEqual([textLimitsForStep(5).min, textLimitsForStep(5).max], [1, 1500]);
  assert.deepEqual([textLimitsForStep(6).min, textLimitsForStep(6).max], [300, 6000]);
  assert.deepEqual([textLimitsForStep(7).min, textLimitsForStep(7).max], [300, 6000]);
  assert.deepEqual([textLimitsForStep(8).min, textLimitsForStep(8).max], [1, 6000]);
});

test("validateTrialText blocks short luận tội and long questions", () => {
  assert.match(validateTrialText("a".repeat(299), textLimitsForStep(6)), /ít nhất 300/);
  // Padding whitespace does not count toward the minimum (the server strips first).
  assert.match(validateTrialText(`  ${"a".repeat(299)}   `, textLimitsForStep(6)), /ít nhất 300/);
  assert.equal(validateTrialText("a".repeat(300), textLimitsForStep(6)), null);
  assert.match(validateTrialText("a".repeat(1501), textLimitsForStep(5)), /1\.500/);
  assert.equal(validateTrialText("a".repeat(1500), textLimitsForStep(5)), null);
  assert.match(validateTrialText("a".repeat(6001), textLimitsForStep(8)), /6\.000/);
  assert.match(validateTrialText("   ", textLimitsForStep(2)), /chưa nhập/);
});

test("mergeUtterances drops duplicate seq and keeps order", () => {
  const u = (seq) => ({ seq, step: 1, speaker_id: "THU_KY", speaker_role: "Thư ký", speaker_name: "", is_user: false, kind: "speech", text: "", addressee: null });
  const merged = mergeUtterances([u(1), u(3)], [u(3), u(2)]);
  assert.deepEqual(merged.map((x) => x.seq), [1, 2, 3]);
});

test("no verdict field is ever read: the source has no verdict handling", async () => {
  const { readFile, readdir } = await import("node:fs/promises");
  const { join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const root = fileURLToPath(new URL("../src", import.meta.url));
  const files = [];
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) await walk(path);
      else if (/\.(ts|tsx)$/.test(entry.name)) files.push(path);
    }
  }
  await walk(root);
  for (const file of files.filter((f) => /trial/i.test(f))) {
    // The one allowed card is the defendant's own role_brief (contract 3.3, Mục 9.14): its type and
    // reads through `brief.` are set aside; any other stance/demeanor is still a leak.
    const source = (await readFile(file, "utf8"))
      .replace(/export interface TrialRoleBrief \{[^}]*\}/, "")
      .replace(/\bbrief\.(stance|demeanor)\b/g, "");
    const hit = source.match(/verdict_json|kết quả nghị án|defendant_plea|character_card|\bstance\b|\bdemeanor\b/i);
    assert.equal(hit, null, `${file} mentions ${hit?.[0]}`);
  }
});

// --- Observer role (contract 5.1) and the case-creation limits (contract Mục 2) ------------------

test("observer: only advance/continue drive the composer; text_limits null never opens an input", () => {
  const observer = { ...baseState, text_limits: null, procedure_note: { step: 5, title: "t", text: "x", legal_basis: ["307"], reviewed: false } };
  assert.equal(composerMode({ ...observer, allowed_actions: ["advance:6"] }), "advance");
  assert.equal(composerMode({ ...observer, awaiting: "ai", allowed_actions: ["continue"] }), "paused");
  assert.equal(composerMode({ ...observer, awaiting: "ai", allowed_actions: [] }), "exhausted");
  assert.equal(composerMode({ ...observer, current_step: 11, status: "completed", awaiting: "none" }), "finished");
  assert.equal(isObserverRole("nguoi_xem"), true);
  assert.equal(isObserverRole("ksv"), false);
  assert.equal(TRIAL_ROLE_LABELS.nguoi_xem, "Người xem");
});

test("observer step hints never address the student as a speaker", () => {
  for (let step = 1; step <= 11; step++) {
    const hint = stepHint(step, "nguoi_xem", false);
    assert.doesNotMatch(hint, /\bbạn\b|ít nhất|Bấm/i, `step ${step}: ${hint}`);
  }
  assert.match(stepHint(8, "nguoi_xem", false), /Kiểm sát viên đối đáp, luật sư đáp lại/);
});

test("global daily cap: server message shown verbatim, distinct from the per-user limit", () => {
  const body = JSON.stringify({ error: { code: "trial_global_daily_limit", message: "Câu thân thiện của máy chủ." } });
  const parsed = parseTrialErrorBody(429, body);
  assert.equal(parsed.serverMessage, "Câu thân thiện của máy chủ.");
  assert.equal(messageForTrialError(parsed), "Câu thân thiện của máy chủ.");
  assert.equal(messageForTrialError({ status: 429, code: "trial_global_daily_limit" }), GLOBAL_DAILY_LIMIT_MESSAGE);
  const perUser = messageForTrialError(parseTrialErrorBody(429, JSON.stringify({ error: { code: "trial_daily_case_limit", message: "m" } })));
  assert.notEqual(perUser, GLOBAL_DAILY_LIMIT_MESSAGE);
  assert.match(perUser, /bạn đã tạo đủ/);
});

test("503 trial_usage_log_unavailable: fail-closed message, not the generic data_unavailable", () => {
  const parsed = parseTrialErrorBody(503, JSON.stringify({ error: { code: "trial_usage_log_unavailable", message: "Thử lại sau nhé." } }));
  assert.equal(messageForTrialError(parsed), "Thử lại sau nhé.");
  assert.equal(messageForTrialError({ status: 503, code: "trial_usage_log_unavailable", serverMessage: null }), USAGE_LOG_UNAVAILABLE_MESSAGE);
  assert.notEqual(messageForTrialError({ status: 503, code: "data_unavailable" }), USAGE_LOG_UNAVAILABLE_MESSAGE);
  // Only these documented codes are echoed; any other server message stays hidden.
  assert.doesNotMatch(messageForTrialError(parseTrialErrorBody(500, JSON.stringify({ error: { code: "internal_server_error", message: "trace" } }))), /trace/);
});

test("limit refusals are notices, other failures are errors", () => {
  for (const code of ["trial_daily_case_limit", "trial_active_session_limit", "trial_global_daily_limit", "trial_usage_log_unavailable"]) {
    assert.equal(isCaseLimitCode(code), true, code);
  }
  for (const code of [null, "rate_limit_exceeded", "data_unavailable", "http_error"]) {
    assert.equal(isCaseLimitCode(code), false, String(code));
  }
});

test("usage log unreadable: 'tạm thời chưa tạo được', never 'đã tạo đủ'", () => {
  const limits = { max_cases_per_day: 5, max_active_sessions: 3, max_witnesses: 2, abandon_after_days: 14 };
  const reason = (remaining) => caseCreationBlockedReason({ limits, remaining });
  assert.equal(USAGE_UNAVAILABLE_NOTICE, "Tạm thời chưa tạo được vụ án mới, bạn vui lòng thử lại sau.");
  assert.equal(reason({ cases_today: 0, active_sessions: 2, usage_available: false }), USAGE_UNAVAILABLE_NOTICE);
  assert.equal(reason({ cases_today: 0, active_sessions: 0, usage_available: false }), USAGE_UNAVAILABLE_NOTICE);
  assert.match(reason({ cases_today: 0, active_sessions: 2, usage_available: true }), /đã tạo đủ 5 vụ án/);
  // An older backend without the field: available.
  assert.match(reason({ cases_today: 0, active_sessions: 2 }), /đã tạo đủ 5 vụ án/);
  assert.equal(reason({ cases_today: 3, active_sessions: 2 }), null);
  assert.match(reason({ cases_today: 3, active_sessions: 0, usage_available: true }), /3 phiên dở dang/);
});

// --- Clerk role (contract 5.2, 3.8-3.10) ---

test("clerk: role label, and the observer controls everywhere but the step-1 report", () => {
  assert.equal(isClerkRole("thu_ky"), true);
  assert.equal(isClerkRole("nguoi_xem"), false);
  assert.equal(TRIAL_ROLE_LABELS.thu_ky, "Thư ký phiên tòa");
  assert.equal(usesObserverControls("thu_ky", "speak"), false);
  for (const mode of ["advance", "paused", "waiting"]) {
    assert.equal(usesObserverControls("thu_ky", mode), true);
  }
  assert.equal(usesObserverControls("nguoi_xem", "advance"), true);
  assert.equal(usesObserverControls("ksv", "advance"), false);
});

test("clerk step 1: speak with the server's 100-3000 limits, labelled as a report", () => {
  const state = { ...baseState, current_step: 1, allowed_actions: ["speak"], text_limits: { min: 100, max: 3000 } };
  assert.equal(composerMode(state), "speak");
  const limits = textLimitsForState(state);
  assert.deepEqual([limits.min, limits.max, limits.label], [100, 3000, "Báo cáo"]);
  assert.match(validateTrialText("a".repeat(99), limits), /ít nhất 100/);
  assert.equal(validateTrialText("a".repeat(100), limits), null);
  assert.match(validateTrialText("a".repeat(3001), limits), /dài quá 3\.000/);
  assert.match(stepHint(1, "thu_ky", true), /Lời mẫu đã điền sẵn/);
  assert.equal(stepHint(5, "thu_ky", false), stepHint(5, "nguoi_xem", false));
});

test("clerk 409 codes have their own Vietnamese messages", () => {
  for (const code of ["trial_not_clerk", "trial_record_finalized", "trial_record_section_empty"]) {
    const message = messageForTrialError({ status: 409, code });
    assert.notEqual(message, messageForTrialError({ status: 409, code: "something_else" }));
  }
  assert.match(messageForTrialError({ status: 409, code: "trial_record_section_empty" }), /còn trống/);
});

test("clerk section length: suggested range is soft, hard cap blocks", () => {
  const limits = { min: 200, max: 4000, hard_max: 6000 };
  assert.equal(clerkSectionLength("   ", limits), "empty");
  assert.equal(clerkSectionLength("a".repeat(199), limits), "short");
  assert.equal(clerkSectionLength("a".repeat(200), limits), "ok");
  assert.equal(clerkSectionLength("a".repeat(4001), limits), "long");
  assert.equal(clerkSectionLength("a".repeat(6000), limits), "long");
  assert.equal(clerkSectionLength("a".repeat(6001), limits), "over");
});

test("clerk finalize: both sections written and within the hard cap; notices do not matter", () => {
  const limits = { hard_max: 6000 };
  assert.equal(canFinalizeClerkDraft({ iv2: "x", iv3: "y" }, limits), true);
  assert.equal(canFinalizeClerkDraft({ iv2: "x", iv3: "  " }, limits), false);
  assert.equal(canFinalizeClerkDraft({ iv2: "", iv3: "y" }, limits), false);
  assert.equal(canFinalizeClerkDraft({ iv2: "x", iv3: "y".repeat(6001) }, limits), false);
});

test("clerk notices: every documented code has a hint, unknown codes none", () => {
  for (const code of ["empty", "too_short", "too_long", "unknown_amount", "unknown_percent", "citation_missing_law", "citation_not_in_section", "unknown_name"]) {
    assert.equal(typeof clerkNoticeHint(code), "string", code);
  }
  assert.match(clerkNoticeHint("unknown_name"), /tên đầy đủ/);
  assert.equal(clerkNoticeHint("new_code"), null);
});

test("clerk draft preview: saved text goes into the 'user' subsections only, input untouched", () => {
  const sub = (heading, content, summary = null) => ({ heading, content, summary, entries: [] });
  const record = {
    sections: [
      { heading: "III. Phần thủ tục", entries: [] },
      { heading: "IV. Phần tranh tụng", subsections: [sub("1. Cáo trạng", "verbatim"), sub("2. Hỏi và trả lời", "user"), sub("3. Tranh luận", "user"), sub("4. Lời nói sau cùng", "verbatim")] }
    ]
  };
  const preview = applyClerkDraft(record, { iv2: "Mục hai.", iv3: "" });
  const [, iv2, iv3, iv4] = preview.sections[1].subsections;
  assert.equal(iv2.summary, "Mục hai.");
  assert.equal(iv3.summary, null);
  assert.equal(iv4.summary, null);
  assert.equal(record.sections[1].subsections[1].summary, null);
  assert.equal(clerkSubsection(record, "iv3").heading, "3. Tranh luận");
});

// --- Defendant role (contract 5.3) ---

test("defendant: label, decline parsed only from allowed_actions", () => {
  assert.equal(isDefendantRole("bi_cao"), true);
  assert.equal(TRIAL_ROLE_LABELS.bi_cao, "Bị cáo");
  assert.equal(parseAllowedActions(["speak", "decline"]).canDecline, true);
  assert.equal(parseAllowedActions(["speak"]).canDecline, false);
  assert.equal(parseAllowedActions(["speak", "end_slot"]).canDecline, false);
  assert.equal(composerMode({ ...baseState, current_step: 4, allowed_actions: ["speak", "decline"] }), "speak");
});

test("defendant limits: server values win; labels per step; fallback 1500 / 3000", () => {
  const answer = textLimitsForState({ current_step: 4, text_limits: { min: 1, max: 1500 } }, "bi_cao");
  assert.deepEqual([answer.min, answer.max, answer.label], [1, 1500, "Câu trả lời"]);
  assert.equal(textLimitsForState({ current_step: 9, text_limits: { min: 1, max: 3000 } }, "bi_cao").label, "Lời nói sau cùng");
  assert.equal(textLimitsForState({ current_step: 8, text_limits: null }, "bi_cao").max, 3000);
  assert.equal(textLimitsForState({ current_step: 2, text_limits: null }, "bi_cao").max, 1500);
  // Other roles unchanged.
  assert.equal(textLimitsForState({ current_step: 8, text_limits: null }, "ksv").label, "Ý kiến đối đáp");
});

test("defendant end_slot labels: 'Không bổ sung' (7), 'Không có ý kiến' (8); other roles unchanged", () => {
  assert.equal(endSlotLabel(7, "bi_cao"), "Không bổ sung");
  assert.equal(endSlotLabel(8, "bi_cao"), "Không có ý kiến");
  assert.equal(endSlotLabel(8, "luat_su"), "Kết thúc đối đáp");
  assert.equal(endSlotLabel(2), "Không có ý kiến");
  assert.match(stepHint(9, "bi_cao", true), /lời sau cùng/);
  assert.match(stepHint(4, "bi_cao", true), /từ chối trả lời/);
});

test("chairInvitation: latest Chủ tọa line of the step, none once the student has spoken", () => {
  const u = (seq, step, speaker_id, o = {}) => ({ seq, step, speaker_id, speaker_role: "", speaker_name: "", is_user: false, kind: "speech", text: `t${seq}`, addressee: null, ...o });
  const lines = [u(1, 7, "LUAT_SU"), u(2, 7, "CHU_TOA", { kind: "procedural" })];
  assert.equal(chairInvitation(lines, 7).seq, 2);
  assert.equal(chairInvitation([...lines, u(3, 7, "BI_CAO", { is_user: true })], 7), null);
  assert.equal(chairInvitation(lines, 8), null);
  assert.equal(chairInvitation([u(4, 8, "CHU_TOA"), u(5, 8, "CHU_TOA", { kind: "notice" })], 8).seq, 4);
});

test("legalBasisArticle: article and code from the server's citation", () => {
  const bltths = legalBasisArticle("điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự");
  assert.equal(bltths.dieu, "61");
  assert.match(bltths.lawVersion, /BLTTHS/);
  assert.match(legalBasisArticle("điểm s khoản 1 Điều 51 Bộ luật Hình sự").lawVersion, /BLHS/);
  assert.equal(legalBasisArticle("Nghị quyết 05/2017"), null);
});

// --- Presiding judge (contract 5.4) ---

const chairItem = (key, kind, o = {}) => ({ key, label: `Nhãn ${key}`, kind, required: true, done: false, available: true, template: `Lời mẫu ${key}.`, basis: ["301"], ai_calls: 0, note: null, ...o });
const presiding = (items, o = {}) => ({
  step: 4, items, missing_required: items.filter((i) => i.required && !i.done).map((i) => i.key),
  counters: { questions_left: 10, remarks_left: 5, debate_rounds: 0 }, ask_addressees: ["BI_CAO", "BI_HAI"], remark_addressees: ["KSV"],
  limits: { item: { min: 1, max: 3000 }, ask: { min: 1, max: 1500 }, remark: { min: 1, max: 1500 } },
  return_available: false, returned: false, in_return: false, templates_reviewed: false, ...o
});

test("chair: role, label, presiding actions give the 'preside' composer mode", () => {
  assert.equal(isChairRole("chu_toa"), true);
  assert.equal(isChairRole("ksv"), false);
  assert.equal(TRIAL_ROLE_LABELS.chu_toa, "Chủ tọa phiên tòa");
  assert.equal(hasPresidingAction(["item:khai_mac", "remark"]), true);
  assert.equal(hasPresidingAction(["speak", "end_slot", "advance:3"]), false);
  assert.equal(composerMode({ ...baseState, allowed_actions: ["item:khai_mac"] }), "preside");
  assert.equal(composerMode({ ...baseState, allowed_actions: ["remark", "advance:5"] }), "preside");
  // Step 1 of a chair session is the plain advance; other roles are unchanged.
  assert.equal(composerMode({ ...baseState, current_step: 1, allowed_actions: ["advance:2"] }), "advance");
  assert.equal(composerMode({ ...baseState, allowed_actions: ["speak", "end_slot"] }), "speak");
});

test("chair: parseChairActions reads item/ask/invite lists, remark, return and advance", () => {
  const parsed = parseChairActions(["item:a|b", "ask:BI_CAO|NLC_1", "invite:moi_hoi_tham_hoi", "remark", "return_to_questioning", "advance:5"]);
  assert.deepEqual(parsed, { items: ["a", "b"], invites: ["moi_hoi_tham_hoi"], askTo: ["BI_CAO", "NLC_1"], canRemark: true, canReturn: true, advanceTo: 5 });
  assert.deepEqual(parseChairActions([]), { items: [], invites: [], askTo: [], canRemark: false, canReturn: false, advanceTo: null });
});

test("chair: ask items go to the right people; one-click template only when it says everything", () => {
  assert.deepEqual(askAddresseesForItem("hoi_bi_cao", ["BI_CAO", "BI_HAI"]), ["BI_CAO"]);
  assert.deepEqual(askAddresseesForItem("hoi_nguoi_khac", ["BI_CAO", "BI_HAI", "NLC_1"]), ["BI_HAI", "NLC_1"]);
  assert.deepEqual(askAddresseesForItem("hoi_lai", ["BI_CAO", "BI_HAI"]), ["BI_CAO", "BI_HAI"]);
  const actions = parseChairActions(["item:khai_mac", "ask:BI_CAO|BI_HAI", "invite:moi_hoi_tham_hoi"]);
  assert.equal(chairOneClickTemplate(chairItem("khai_mac", "item"), actions), true);
  assert.equal(chairOneClickTemplate(chairItem("moi_hoi_tham_hoi", "invite"), actions), true);
  assert.equal(chairOneClickTemplate(chairItem("hoi_bi_cao", "ask"), actions), true);
  assert.equal(chairOneClickTemplate(chairItem("hoi_nguoi_khac", "ask"), parseChairActions(["ask:BI_CAO|BI_HAI|NLC_1"])), false);
  // Not listed, not available, or no template: no one-click.
  assert.equal(chairOneClickTemplate(chairItem("kiem_tra_co_mat", "item"), actions), false);
  assert.equal(chairOneClickTemplate(chairItem("khai_mac", "item", { available: false }), actions), false);
  assert.equal(chairOneClickTemplate(chairItem("khai_mac", "item", { template: null }), actions), false);
  assert.equal(chairItemActionable(chairItem("tro_lai_xet_hoi", "return"), parseChairActions(["return_to_questioning"])), true);
  assert.equal(chairItemActionable(chairItem("tro_lai_xet_hoi", "return"), parseChairActions(["remark"])), false);
});

test("chair: composer targets only from allowed_actions; default prefers a question, then a required item", () => {
  const p = presiding([chairItem("cong_bo_loi_khai_bi_hai", "item"), chairItem("moi_hoi_tham_hoi", "invite", { required: false }), chairItem("hoi_bi_cao", "ask")]);
  const options = chairTargetOptions(p, parseChairActions(["item:cong_bo_loi_khai_bi_hai", "invite:moi_hoi_tham_hoi", "ask:BI_CAO", "remark"]));
  assert.deepEqual(options.map((o) => o.value), ["item:cong_bo_loi_khai_bi_hai", "invite:moi_hoi_tham_hoi", "ask", "remark"]);
  assert.equal(resolveChairTarget("", p, options), "ask");
  assert.equal(resolveChairTarget("remark", p, options), "remark");
  const noAsk = options.filter((o) => o.value !== "ask");
  assert.equal(resolveChairTarget("ask", p, noAsk), "item:cong_bo_loi_khai_bi_hai");
  assert.equal(resolveChairTarget("", presiding([]), []), null);
});

test("chair: text limits from presiding.limits; an empty box sends the template where there is one", () => {
  const p = presiding([chairItem("khai_mac", "item"), chairItem("x", "item", { template: null })]);
  const item = chairTextLimits("item:khai_mac", p);
  assert.equal(item.max, 3000);
  assert.equal(item.optional, true);
  assert.equal(validateChairText("", item), null);
  assert.match(validateChairText("a".repeat(3001), item), /3\.000/);
  assert.equal(chairTextLimits("item:x", p).optional, false);
  assert.equal(validateChairText(" ", chairTextLimits("item:x", p)), "Bạn chưa nhập nội dung.");
  const ask = chairTextLimits("ask", p);
  assert.equal(ask.max, 1500);
  assert.equal(validateChairText("", ask), "Bạn chưa nhập nội dung.");
  assert.match(validateChairText("a".repeat(1501), chairTextLimits("remark", p)), /1\.500/);
  assert.equal(chairTextLimits("return", p).optional, true);
});

test("chair: procedure_item labels, current step first, catalogue as fallback", () => {
  const p = presiding([chairItem("hoi_bi_cao", "ask")]);
  assert.equal(chairItemLabel("hoi_bi_cao", p), "Nhãn hoi_bi_cao");
  assert.equal(chairItemLabel("khai_mac", p), "Khai mạc, đọc quyết định đưa vụ án ra xét xử");
  assert.equal(chairItemLabel("remark", null), "Phát biểu khác");
  assert.equal(chairItemLabel("unknown_key", null), null);
  assert.equal(chairItemLabel(null, p), null);
});

test("chair 409s: missing_items parsed; new codes have Vietnamese messages; re-sync set", () => {
  const body = JSON.stringify({ error: { code: "trial_procedure_incomplete", message: "m" }, missing_items: ["khai_mac", 3, "hoi_thay_doi"], state: baseState });
  const parsed = parseTrialErrorBody(409, body);
  assert.deepEqual(parsed.missingItems, ["khai_mac", "hoi_thay_doi"]);
  assert.deepEqual(parseTrialErrorBody(409, JSON.stringify({ error: { code: "trial_busy", message: "m" } })).missingItems, []);
  const codes = ["trial_procedure_incomplete", "trial_item_not_available", "trial_item_done", "trial_return_not_allowed", "trial_return_used",
    "trial_decision_missing", "trial_decision_invalid", "trial_decision_locked", "trial_pronouncement_missing", "trial_not_presiding"];
  const generic = messageForTrialError({ status: 409, code: "trial_unknown_code" });
  for (const code of codes) {
    const message = messageForTrialError({ status: 409, code });
    assert.notEqual(message, generic, code);
  }
  assert.equal(isResyncConflict("trial_item_done"), true);
  assert.equal(isResyncConflict("trial_return_used"), true);
  assert.equal(isResyncConflict("trial_procedure_incomplete"), false);
});
