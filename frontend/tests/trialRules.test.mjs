// Unit tests for src/lib/trialRules.ts. No test framework: Node's built-in runner, which loads the
// .ts file directly (type stripping, Node >= 23.6). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  applyClerkDraft,
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
    const source = await readFile(file, "utf8");
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
