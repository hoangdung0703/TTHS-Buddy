// Unit tests for src/lib/trialText.ts (Node's built-in runner, `npm test`).
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { isLongTrialText, parseTrialText } from "../src/lib/trialText.ts";

test("paragraphs split on one blank line; single newlines are line breaks", () => {
  const blocks = parseTrialText("Dòng một\nDòng hai\n\nĐoạn hai");
  assert.deepEqual(blocks, [
    { type: "paragraph", lead: null, lines: ["Dòng một", "Dòng hai"] },
    { type: "paragraph", lead: null, lines: ["Đoạn hai"] }
  ]);
});

test("consecutive '- ' lines become one list; a sentence before them stays a paragraph", () => {
  const blocks = parseTrialText("Chứng cứ gồm:\n- E1 vật chứng\n- E2 định giá\n\nKết luận.");
  assert.deepEqual(blocks, [
    { type: "paragraph", lead: null, lines: ["Chứng cứ gồm:"] },
    { type: "list", items: ["E1 vật chứng", "E2 định giá"] },
    { type: "paragraph", lead: null, lines: ["Kết luận."] }
  ]);
});

test("roman-numeral lines are headings, also when followed by a line in the same block", () => {
  const blocks = parseTrialText("VIỆN KIỂM SÁT\nSố: 12/CT\n\nI. Nội dung vụ án\nVào ngày...\n\nIV. Kết luận và truy tố\nTruy tố bị cáo.");
  assert.deepEqual(blocks.map((b) => b.type), ["paragraph", "heading", "paragraph", "heading", "paragraph"]);
  assert.equal(blocks[1].text, "I. Nội dung vụ án");
  assert.deepEqual(blocks[0].lines, ["VIỆN KIỂM SÁT", "Số: 12/CT"]);
  // "Về" alone or "In" are not headings.
  assert.equal(parseTrialText("Iran không phải tiêu đề")[0].type, "paragraph");
});

test("lead phrase 'Về ...:' is split off at the start of a paragraph only", () => {
  const [first] = parseTrialText("Về hành vi phạm tội: Bị cáo đã lấy tài sản.");
  assert.equal(first.lead, "Về hành vi phạm tội:");
  assert.deepEqual(first.lines, ["Bị cáo đã lấy tài sản."]);
  const [alone, list] = parseTrialText("Về chứng cứ:\n- E1");
  assert.equal(alone.lead, "Về chứng cứ:");
  assert.deepEqual(alone.lines, []);
  assert.equal(list.type, "list");
  // Too long a phrase, or "Về" mid-paragraph, is not a lead.
  assert.equal(parseTrialText(`Về ${"rất ".repeat(20)}dài: nội dung`)[0].lead, null);
  assert.equal(parseTrialText("Bị cáo nói. Về sau: không")[0].lead, null);
});

test("legacy text without newlines is one paragraph, unchanged", () => {
  const legacy = "Cáo trạng số 1. Vào ngày 19/04/2026 bị cáo lấy tài sản. Đề nghị truy tố theo khoản 1 Điều 173.";
  assert.deepEqual(parseTrialText(legacy), [{ type: "paragraph", lead: null, lines: [legacy] }]);
  assert.equal(isLongTrialText(legacy), false);
});

test("HTML-like input stays literal text; markdown is not interpreted", () => {
  const raw = '<b>không đậm</b> & <script>alert(1)</script> **sao** # thăng "ngoặc"';
  const [block] = parseTrialText(raw);
  assert.deepEqual(block.lines, [raw]);
});

test("CRLF and stray whitespace-only lines are tolerated", () => {
  const blocks = parseTrialText("Một\r\n\r\nHai\n   \nBa");
  assert.deepEqual(blocks.map((b) => b.lines[0]), ["Một", "Hai", "Ba"]);
});

test("isLongTrialText: several blocks or > 600 chars", () => {
  assert.equal(isLongTrialText("Ngắn."), false);
  assert.equal(isLongTrialText("Một.\n\nHai."), true);
  assert.equal(isLongTrialText("a".repeat(601)), true);
  assert.equal(isLongTrialText("- một mục"), true);
});

test("no trial component injects HTML", async () => {
  const dir = fileURLToPath(new URL("../src/components/trial", import.meta.url));
  for (const name of await readdir(dir)) {
    const source = await readFile(join(dir, name), "utf8");
    assert.equal(source.includes("dangerouslySetInnerHTML"), false, name);
    assert.equal(/from "react-markdown"/.test(source), false, name);
  }
});
