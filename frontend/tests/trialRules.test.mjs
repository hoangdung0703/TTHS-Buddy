// Unit tests for src/lib/trialRules.ts. No test framework: Node's built-in runner, which loads the
// .ts file directly (type stripping, Node >= 23.6). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  composerMode,
  isResyncConflict,
  mergeUtterances,
  messageForTrialError,
  parseAllowedActions,
  parseTrialErrorBody,
  textLimitsForStep,
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

test("length limits per step match the backend", () => {
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
