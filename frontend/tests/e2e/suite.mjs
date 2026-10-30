// Mocked browser suite for "Phiên tòa giả định" (0 Gemini calls, no real backend or account).
// Run tests/e2e/build.sh first, then `node tests/e2e/suite.mjs`. Prints PASS/FAIL lines only and
// exits non-zero when anything fails. Set E2E_SHOTS=<dir> to also save screenshots there.
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import {
  FAKE, FULL, SHORT, OBSERVER_PREAMBLE, TRANSCRIPT_MARKER, CLERK_PREFILL, DECLINE_TEXT, IDENTITY_PREFILL, ROLE_BRIEF_NOTE, clerkPrompt, clerkRecordText, clerkReport, config,
  defendantQuestion, makeUtterances, procedureNote, recordText, utt
} from "./fixtures.mjs";
import {
  BASE, baseState, check, chromium, failureCount, fulfillError, fulfillSse, installStreamingTurn, newPage, noPageOverflow, signIn, signOut,
  openHearing, resetWorld, scrollInfo, sseEvent, world
} from "./lib.mjs";
import { CHAIR_MARK, DEBATE_NOTE, chairState, chairTurn, newChair } from "./chair.mjs";

const SHOTS = process.env.E2E_SHOTS ?? null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${name}.png`) });
}

const consoleMessages = [];
const browser = await chromium.launch();
const open = (options = {}) => newPage(browser, { consoleBucket: consoleMessages, ...options });
const trialRequests = (method) => world.requests.filter((r) => r.method === method && r.path === "/api/trials").length;
const redirectsHome = (page) => page.waitForURL("**/dashboard", { timeout: 15000 }).then(() => true, () => false);
const aiUtt = (seq, step = 5, text = `Lời mới AI số ${seq}.`) => utt(seq, step, "CHU_TOA", text);

// =============================== Feature flag (HEAD probe) ===============================
resetWorld();
world.flag = "off";
let { context, page } = await open();
await page.goto(`${BASE}/dashboard`);
await page.waitForTimeout(2500);
check("flag off: menu hidden", (await page.getByRole("link", { name: "Phiên tòa giả định" }).count()) === 0);
check("flag off: probe is HEAD /api/trials, no GET", trialRequests("HEAD") >= 1 && trialRequests("GET") === 0);
for (const path of ["/trial", "/trial/new", `/trial/${FAKE}`, `/trial/${FAKE}/record`]) {
  await page.goto(`${BASE}${path}`);
  check(`flag off: ${path} redirects to the dashboard`, await redirectsHome(page));
}
await context.close();

resetWorld();
({ context, page } = await open());
await page.goto(`${BASE}/dashboard`);
check("flag on: menu visible", await page.getByRole("link", { name: "Phiên tòa giả định" }).first().waitFor({ timeout: 15000 }).then(() => true, () => false));
const headsAfterLoad = trialRequests("HEAD");
check("flag on: exactly one HEAD probe, no GET list on the dashboard", headsAfterLoad === 1 && trialRequests("GET") === 0);
await page.getByRole("link", { name: "Vở ghi" }).first().click();
await page.waitForURL("**/notes");
await page.waitForTimeout(800);
check("flag on: no re-probe on client-side navigation", trialRequests("HEAD") === headsAfterLoad && trialRequests("GET") === 0);
const storageKeys = await page.evaluate(() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]);
check("nothing about trials in local/session storage", !storageKeys.some((key) => /trial/i.test(key)));
await context.close();

resetWorld();
world.flag = "head405";
({ context, page } = await open());
await page.goto(`${BASE}/dashboard`);
check("backend without HEAD (405): falls back to GET, menu visible",
  await page.getByRole("link", { name: "Phiên tòa giả định" }).first().waitFor({ timeout: 15000 }).then(() => trialRequests("GET") === 1, () => false));
await context.close();

// =============================== Probe kept per user (TRIAL_ALLOWED_EMAILS) ===============================
const USER_A = "a@e2e.test";
const USER_B = "b@e2e.test";
const headProbes = () => world.requests.filter((r) => r.method === "HEAD" && r.path === "/api/trials");
const menuLink = (page) => page.getByRole("link", { name: "Phiên tòa giả định" });
const menuShows = (page) => menuLink(page).first().waitFor({ timeout: 10000 }).then(() => true, () => false);

resetWorld();
world.allowedEmails = [USER_A];
({ context, page } = await open({ signedInAs: null }));
// Signed out, /trial mounts the feature gate before the login redirect: the old code probed here
// without a token, got the allowlist 404 and kept "disabled" for the whole page life.
await page.goto(`${BASE}/trial`);
await page.waitForURL("**/login", { timeout: 15000 });
await page.waitForTimeout(800);
check("signed out: no HEAD probe without a token", headProbes().length === 0);
await page.evaluate(() => { window.__e2eSamePage = true; });
await signIn(page, USER_A);
check("sign-in after a signed-out visit: listed user sees the menu", await menuShows(page));
check("listed user: exactly one HEAD probe, made with that user's token", headProbes().length === 1 && headProbes()[0].email === USER_A);
await signOut(page);
check("sign-out: menu gone, no probe while signed out", (await menuLink(page).count()) === 0 && headProbes().length === 1);
await signIn(page, USER_B);
await page.waitForTimeout(1500);
check("switch A -> B without reload: B (not listed) has no menu", (await menuLink(page).count()) === 0 && headProbes().filter((h) => h.email === USER_B).length === 1);
await signOut(page);
await signIn(page, USER_A);
check("switch B -> A without reload: the menu comes back", await menuShows(page));
check("no page reload during sign-in/out/switch, one probe per sign-in", (await page.evaluate(() => window.__e2eSamePage === true)) && headProbes().length === 3);
await signOut(page);
await signIn(page, USER_B);
await page.waitForTimeout(1000);
await page.goto(`${BASE}/trial`);
check("not-listed user: /trial redirects to the dashboard", await redirectsHome(page));
await context.close();

// A network error is not remembered: the next page asks again.
resetWorld();
let failingHeads = 1;
world.head = async (route) => {
  if (failingHeads-- <= 0) return false;
  await route.abort("failed");
  return true;
};
({ context, page } = await open());
await page.goto(`${BASE}/dashboard`);
await page.waitForTimeout(2000);
check("probe network error: menu hidden, no redirect state kept", (await menuLink(page).count()) === 0 && headProbes().length === 1);
await page.getByRole("link", { name: "Vở ghi" }).first().click();
await page.waitForURL("**/notes");
check("after a network error the next page probes again and shows the menu", (await menuShows(page)) && headProbes().length === 2);
await context.close();

// "unknown" (probe still pending) hides the menu but does not redirect.
resetWorld();
world.delay = 3000;
({ context, page } = await open());
await page.goto(`${BASE}/trial`);
await page.waitForTimeout(1500);
check("probe pending: /trial is not redirected, menu hidden", new URL(page.url()).pathname === "/trial" && (await menuLink(page).count()) === 0);
check("probe answers: menu shown, still on /trial", (await menuShows(page)) && new URL(page.url()).pathname === "/trial");
await context.close();

// =============================== Usage log unreadable (usage_available = false) ===============================
const USAGE_NOTICE = "Tạm thời chưa tạo được vụ án mới, bạn vui lòng thử lại sau.";
resetWorld();
world.config = config({ remaining: { cases_today: 0, active_sessions: 2, usage_available: false } });
({ context, page } = await open());
await page.goto(`${BASE}/trial`);
await page.getByTestId("trial-create-blocked").waitFor({ timeout: 20000 });
check("list, usage unavailable: contract notice, create locked, no 'đã tạo đủ', no '0/5'",
  (await page.getByTestId("trial-create-blocked").innerText()).trim() === USAGE_NOTICE
  && (await page.getByRole("button", { name: "Tạo phiên mới" }).isDisabled())
  && !/đã tạo đủ/.test(await page.locator("body").innerText())
  && !(await page.getByTestId("trial-quota").innerText()).includes("0/5"));
await page.goto(`${BASE}/trial/new`);
await page.getByTestId("role-nguoi_xem").waitFor({ timeout: 20000 });
await page.getByTestId("role-nguoi_xem").getByRole("radio").click();
await page.getByRole("radio", { name: /Tội trộm cắp tài sản/ }).click();
check("new, usage unavailable: contract notice, 'Tạo vụ án' locked, no 'đã tạo đủ'",
  (await page.getByTestId("trial-create-blocked").innerText()).trim() === USAGE_NOTICE
  && (await page.getByRole("button", { name: "Tạo vụ án" }).isDisabled())
  && !/đã tạo đủ/.test(await page.locator("body").innerText()));
world.config = config({ remaining: { cases_today: 0, active_sessions: 2 } }); // older backend, no field
await page.goto(`${BASE}/trial/new`);
await page.getByTestId("trial-create-blocked").waitFor({ timeout: 20000 });
check("new, older backend without usage_available and 0 left: 'đã tạo đủ 5 vụ án'", (await page.getByTestId("trial-create-blocked").innerText()).includes("đã tạo đủ 5 vụ án"));
await context.close();

// =============================== /trial/new ===============================
resetWorld();
({ context, page } = await open());
await page.goto(`${BASE}/trial/new`);
await page.getByTestId("role-nguoi_xem").waitFor({ timeout: 20000 });
const radio = (key) => page.getByTestId(`role-${key}`).getByRole("radio");
check("new: Người xem enabled from config.user_roles", await radio("nguoi_xem").isEnabled());
check("new: Người xem card has the contract description and no article pill",
  (await page.getByTestId("role-nguoi_xem").innerText()).includes("Theo dõi trọn một phiên tòa do hệ thống đóng mọi vai")
  && (await page.getByTestId("role-nguoi_xem").getByRole("button", { name: /Xem toàn văn/ }).count()) === 0);
let comingSoon = true;
for (const key of ["bi_cao", "chu_toa", "thu_ky"]) {
  comingSoon = comingSoon && (await radio(key).isDisabled()) && (await page.getByTestId(`role-${key}`).innerText()).includes("Sắp có");
}
check("new: roles not in config are disabled and marked 'Sắp có'", comingSoon);
check("new: KSV and luật sư still enabled with their article pill",
  (await radio("ksv").isEnabled()) && (await page.getByTestId("role-ksv").getByRole("button", { name: /Xem toàn văn/ }).count()) === 1);
await shot(page, "new-desktop");

let createBody = null;
world.create = (route, body) => {
  createBody = body;
  return fulfillSse(route, sseEvent("status", { message: "Đang chuẩn bị hồ sơ pháp lý của vụ án..." })
    + sseEvent("session", { session_id: FAKE, title: "Vụ mẫu" }) + sseEvent("state", baseState()) + sseEvent("done", {}));
};
await radio("nguoi_xem").click();
await page.getByRole("radio", { name: /Tội trộm cắp tài sản/ }).click();
await page.getByRole("radio", { name: "2" }).click();
world.role = "nguoi_xem";
world.state = baseState({ current_step: 1, allowed_actions: ["advance:2"], procedure_note: procedureNote(1) });
await page.getByRole("button", { name: "Tạo vụ án" }).click();
check("new: observer case created, navigated to the hearing", await page.waitForURL(`**/trial/${FAKE}`, { timeout: 15000 }).then(() => true, () => false));
check("new: POST body has exactly the 5 contract fields, user_role nguoi_xem",
  createBody !== null && Object.keys(createBody).sort().join() === "crime_key,has_related_party,user_role,victim_present,witness_count"
  && createBody.user_role === "nguoi_xem" && createBody.witness_count === 2 && createBody.crime_key === "blhs_173");

// Limit refusals.
const createError = page.getByTestId("trial-create-error");
async function tryCreate(status, code, message) {
  world.create = (route) => fulfillError(route, status, code, { message });
  await page.goto(`${BASE}/trial/new`);
  await radio("nguoi_xem").click();
  await page.getByRole("radio", { name: /Tội trộm cắp tài sản/ }).click();
  await page.getByRole("button", { name: "Tạo vụ án" }).click();
  await createError.waitFor({ timeout: 10000 });
  return { text: await createError.innerText(), code: await createError.getAttribute("data-code"), cls: (await createError.getAttribute("class")) ?? "" };
}
const GLOBAL_TEXT = "Hôm nay hệ thống đã tạo đủ số vụ án mô phỏng cho phép (câu mẫu từ máy chủ).";
const globalLimit = await tryCreate(429, "trial_global_daily_limit", GLOBAL_TEXT);
check("new: 429 trial_global_daily_limit shows the server message verbatim, as a notice (not red)",
  globalLimit.text.includes(GLOBAL_TEXT) && globalLimit.code === "trial_global_daily_limit" && !globalLimit.cls.includes("bg-red-50"));
await shot(page, "new-global-limit");
const userLimit = await tryCreate(429, "trial_daily_case_limit", "Mỗi ngày chỉ tạo được tối đa 5 vụ án.");
check("new: 429 trial_daily_case_limit has its own (per-user) wording", userLimit.text.includes("bạn đã tạo đủ") && userLimit.text !== globalLimit.text);
const LOG_TEXT = "Tạm thời chưa tạo được vụ án mới vì hệ thống không kiểm tra được hạn mức (câu mẫu).";
const logDown = await tryCreate(503, "trial_usage_log_unavailable", LOG_TEXT);
check("new: 503 trial_usage_log_unavailable shows the server message, retry stays available",
  logDown.text.includes(LOG_TEXT) && logDown.code === "trial_usage_log_unavailable" && (await page.getByRole("button", { name: "Thử tạo lại" }).isEnabled()));
const generic = await tryCreate(503, "data_unavailable", "internal detail");
check("new: other 503 keeps the generic red error, server text not echoed", !generic.text.includes("internal detail") && generic.cls.includes("bg-red-50"));
await context.close();

world.config = config({ user_roles: ["ksv", "luat_su"] });
({ context, page } = await open());
await page.goto(`${BASE}/trial/new`);
await page.getByTestId("role-nguoi_xem").waitFor({ timeout: 20000 });
check("new: without nguoi_xem in config the card is disabled ('Sắp có')",
  (await radio("nguoi_xem").isDisabled()) && (await page.getByTestId("role-nguoi_xem").innerText()).includes("Sắp có"));
await context.close();

// =============================== Hearing, KSV (existing behaviour) ===============================
resetWorld();
({ context, page } = await open());
await openHearing(page, baseState());
await page.getByTestId("trial-input").fill("a".repeat(299));
check("limits fallback: 299 chars at step 6 blocked", await page.getByTestId("trial-send").isDisabled());
await page.getByTestId("trial-input").fill("a".repeat(300));
check("limits fallback: 300 chars allowed", await page.getByTestId("trial-send").isEnabled());
await openHearing(page, baseState({ text_limits: { min: 50, max: 900 } }));
await page.getByTestId("trial-input").fill("a".repeat(60));
check("server text_limits: 60/900 allowed", (await page.getByTestId("trial-send").isEnabled()) && (await page.getByTestId("trial-counter").innerText()).includes("60/900"));
await page.getByTestId("trial-input").fill("a".repeat(901));
check("server text_limits: 901 blocked", await page.getByTestId("trial-send").isDisabled());
check("KSV: no procedure note", (await page.getByTestId("trial-procedure-note").count()) === 0);

// 409 version mismatch.
await openHearing(page, baseState());
await page.getByTestId("trial-input").fill("a".repeat(300));
let turnBody = null;
world.turn = (route, body) => {
  turnBody = body;
  world.state = baseState({ version: 11 });
  return fulfillError(route, 409, "trial_version_mismatch", { state: world.state });
};
let detailGets = world.requests.filter((r) => r.method === "GET" && r.path.endsWith(FAKE)).length;
await page.getByTestId("trial-send").click();
await page.getByTestId("trial-soft-notice").waitFor({ timeout: 10000 });
check("409: exact body, state re-read, soft notice, draft kept",
  turnBody.expected_version === 10 && Object.keys(turnBody).sort().join() === "action,expected_step,expected_version,text"
  && world.requests.filter((r) => r.method === "GET" && r.path.endsWith(FAKE)).length > detailGets
  && (await page.getByTestId("trial-input").inputValue()).length === 300);

// Step 5: addressee and 1500.
await openHearing(page, baseState({ current_step: 5, allowed_actions: ["speak:BI_CAO|BI_HAI", "end_slot"], text_limits: { min: 1, max: 1500 } }));
await page.getByTestId("trial-input").fill("b".repeat(1501));
check("step 5: addressee select, 1501 chars blocked", (await page.getByLabel("Hỏi:").count()) === 1 && (await page.getByTestId("trial-send").isDisabled()));

// Names: panel anonymised, transcript full.
const aside = page.locator('aside[aria-label="Hồ sơ vụ án"]');
const panelText = await aside.innerText();
check("panel: abbreviated names from case_file", panelText.includes(SHORT.BI_CAO) && panelText.includes(SHORT.BI_HAI));
check("panel: no full lay names", !panelText.includes(FULL.BI_CAO) && !panelText.includes(FULL.BI_HAI));
await aside.getByRole("tab", { name: "Lời khai" }).click();
const statements = await aside.innerText();
check("panel statements: names via display_names", statements.includes(`Bị cáo ${SHORT.BI_CAO}`) && statements.includes(`Người làm chứng ${SHORT.NLC_1}`) && !statements.includes(FULL.NLC_1));
check("transcript: full names", (await page.locator('ol[aria-label="Diễn biến phiên tòa"]').innerText()).includes(FULL.BI_CAO));

// Structured text.
const longBubble = page.locator('[data-testid="trial-ai-utterance"]').last();
check("long utterance: reading layout, 3-item list, bold lead",
  (await longBubble.locator("[data-long]").count()) === 1 && (await longBubble.locator('ul[data-trial-text="list"] li').count()) === 3
  && (await longBubble.locator('[data-trial-text="lead"]').first().innerText()).trim() === "Về hành vi phạm tội:");
const htmlBubble = page.locator('[data-seq="25"]');
check("HTML characters shown literally", (await htmlBubble.innerText()).includes("<b>không đậm</b>") && (await htmlBubble.locator("b, script").count()) === 0);
await aside.getByRole("tab", { name: "Cáo trạng" }).click();
check("indictment in panel: 4 headings + evidence list",
  (await aside.locator('[data-trial-text="heading"]').count()) === 4 && (await aside.locator('[data-trial-text="list"] li').count()) === 2);

// Expanded panel.
await page.getByRole("button", { name: "Mở rộng hồ sơ vụ án" }).click();
const sheet = page.getByTestId("trial-casefile-expanded");
const sheetBox = await sheet.boundingBox();
check(`expanded panel ~720px (${Math.round(sheetBox.width)})`, sheetBox.width >= 700 && sheetBox.width <= 730);
check("expanded panel keeps the tab", (await sheet.getByRole("tab", { name: "Cáo trạng" }).getAttribute("aria-selected")) === "true");
await page.keyboard.press("Escape");
check("expanded panel: Esc closes, focus returns", (await sheet.count()) === 0 && (await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))) === "Mở rộng hồ sơ vụ án");

// Scrolling and "Có lời mới".
world.utterances = makeUtterances(40);
await openHearing(page, baseState({ current_step: 5, awaiting: "ai", allowed_actions: ["continue"] }));
let info = await scrollInfo(page);
check("load: at bottom, latest visible", info.distance <= 2 && info.latestVisible);
let nextSeq = 100;
world.turn = (route) => {
  const added = [aiUtt(nextSeq++), aiUtt(nextSeq++)];
  world.utterances.push(...added);
  world.state = baseState({ current_step: 5, awaiting: "ai", allowed_actions: ["continue"], version: world.state.version + 1 });
  return fulfillSse(route, added.map((u) => sseEvent("utterance", u)).join("") + sseEvent("state", world.state) + sseEvent("done", {}));
};
await page.getByRole("button", { name: "Tiếp tục" }).click();
await page.waitForTimeout(1200);
info = await scrollInfo(page);
check("at bottom: new lines followed", info.distance <= 2 && info.latestVisible && (await page.getByTestId("trial-new-below").count()) === 0);
await page.evaluate(() => document.querySelector("[data-seq]").scrollIntoView({ block: "start" }));
await page.waitForTimeout(300);
const topBefore = (await scrollInfo(page)).top;
await page.getByRole("button", { name: "Tiếp tục" }).click();
await page.waitForTimeout(1200);
info = await scrollInfo(page);
check("scrolled up: not pulled down, 'Có lời mới' shown", Math.abs(info.top - topBefore) < 5 && (await page.getByTestId("trial-new-below").isVisible()));
await page.getByTestId("trial-new-below").click();
await page.waitForTimeout(400);
info = await scrollInfo(page);
check("'Có lời mới': back at bottom, button gone", info.distance <= 2 && info.latestVisible && (await page.getByTestId("trial-new-below").count()) === 0);

// Guard fuse, no automatic continue, stream error.
world.utterances = makeUtterances();
await openHearing(page, baseState({ awaiting: "ai", allowed_actions: ["continue"] }));
world.turn = (route) => {
  world.state = baseState({ awaiting: "ai", allowed_actions: [] });
  return fulfillError(route, 409, "trial_guard_exhausted", { state: world.state });
};
await page.getByRole("button", { name: "Tiếp tục" }).click();
await page.getByTestId("trial-guard-exhausted").waitFor({ timeout: 10000 });
check("guard fuse: only Bỏ/Xóa phiên", (await page.getByRole("button", { name: "Tiếp tục" }).count()) === 0 && (await page.getByRole("button", { name: "Bỏ phiên" }).count()) >= 1);
let posts = 0;
world.turn = (route) => {
  posts++;
  return route.fulfill({ status: 500, body: "{}" });
};
await openHearing(page, baseState({ awaiting: "ai", allowed_actions: ["continue"] }));
await page.waitForTimeout(1500);
check("no automatic continue on load", posts === 0);
world.turn = (route) => fulfillSse(route, sseEvent("status", { message: "x" }) + sseEvent("error", { message: "Xin lỗi, đã có lỗi" }));
await page.getByRole("button", { name: "Tiếp tục" }).click();
check("stream error: red box", await page.getByTestId("trial-error").waitFor({ timeout: 10000 }).then(() => true, () => false));

// Finished.
await openHearing(page, baseState({ current_step: 11, status: "completed", awaiting: "none", allowed_actions: [] }));
info = await scrollInfo(page);
const barBox = await page.getByTestId("trial-finished").boundingBox();
check(`finished: one-line bar (${Math.round(barBox.height)}px, dock ${info.dockH}px), latest not covered`, barBox.height <= 60 && info.dockH <= 90 && info.latestVisible);
check("finished: Xem biên bản, nowhere to show a verdict",
  (await page.getByRole("link", { name: "Xem biên bản" }).count()) >= 1 && !/kết quả nghị án|quyết định nghị án/i.test(await page.locator("body").innerText()));
await context.close();

// =============================== Hearing, Người xem ===============================
resetWorld();
world.role = "nguoi_xem";
({ context, page } = await open());
await installStreamingTurn(context);
await openHearing(page, baseState({ current_step: 5, step_title: "Kiểm sát viên và luật sư xét hỏi", allowed_actions: ["advance:6"], version: 30, procedure_note: procedureNote(5, false) }));
const note = page.getByTestId("trial-procedure-note");
const noteHeader = note.getByRole("button", { name: /Chú giải thủ tục/ });
check("observer: no input, no send, no end-slot", (await page.getByTestId("trial-input").count()) === 0 && (await page.getByTestId("trial-send").count()) === 0
  && (await page.getByTestId("trial-end-slot").count()) === 0 && (await page.locator("textarea").count()) === 0);
check("observer: header says 'Vai của bạn: Người xem'", (await page.getByText("Vai của bạn: Người xem").count()) === 1);
check("observer: note of the current step open by default, text and BLTTHS pills",
  (await noteHeader.getAttribute("aria-expanded")) === "true" && (await note.innerText()).includes("Chú giải mẫu cho bước 5")
  && (await note.getByRole("button", { name: /Xem toàn văn Điều 307/ }).count()) === 1);
const draftLabel = (scope) => scope.getByText("Bản nháp, đang chờ nhóm luật duyệt").filter({ visible: true });
check("observer: reviewed=false shows 'Bản nháp, đang chờ nhóm luật duyệt'", (await draftLabel(note).count()) === 1);
check("observer: 'Sang bước tiếp theo' with the next step title",
  (await page.getByTestId("trial-advance").isEnabled()) && (await page.getByTestId("trial-composer-dock").innerText()).includes("Tiếp theo: Kiểm sát viên luận tội"));
check("observer: no 'Tiếp tục xem' in advance mode", (await page.getByRole("button", { name: "Tiếp tục xem" }).count()) === 0);
await shot(page, "observer-desktop");
await noteHeader.click();
check("observer: note collapses", (await noteHeader.getAttribute("aria-expanded")) === "false" && (await page.getByTestId("trial-procedure-note-body").count()) === 0);

// A long AI turn: progress with the server status and elapsed time, button locked.
const nextState = baseState({ current_step: 6, step_title: "Kiểm sát viên luận tội", allowed_actions: ["advance:7"], version: 31, procedure_note: procedureNote(6, false) });
await page.evaluate(({ utterance, state }) => {
  window.__e2eTurn = [
    { delay: 200, event: "status", data: { message: "Kiểm sát viên luận tội..." } },
    { delay: 2600, event: "utterance", data: utterance },
    { delay: 100, event: "state", data: state },
    { event: "done", data: {} }
  ];
}, { utterance: utt(200, 6, "KSV", "Bản luận tội mẫu."), state: nextState });
world.state = nextState;
await page.getByTestId("trial-advance").click();
await page.waitForTimeout(1500);
const progress = page.getByTestId("trial-observer-progress");
check("observer turn running: progress shows the status line and elapsed seconds",
  (await progress.isVisible()) && (await progress.innerText()).includes("Kiểm sát viên luận tội...") && /\b[1-9]\d*s\b/.test(await progress.innerText()));
check("observer turn running: button locked, no advance button",
  (await page.getByTestId("trial-observer-busy-button").isDisabled()) && (await page.getByTestId("trial-advance").count()) === 0);
await shot(page, "observer-progress-desktop");
await page.getByTestId("trial-advance").waitFor({ timeout: 10000 });
const sentAdvance = (await page.evaluate(() => window.__e2eTurnBodies))[0];
check("observer advance: exact body {expected_step, expected_version, action, target_step}",
  JSON.stringify(sentAdvance) === JSON.stringify({ expected_step: 5, expected_version: 30, action: "advance", target_step: 6 }));
check("observer: new step's note opens by default (step 5 had been collapsed)",
  (await noteHeader.getAttribute("aria-expanded")) === "true" && (await note.innerText()).includes("Chú giải mẫu cho bước 6"));
info = await scrollInfo(page);
check("observer: the taller dock (note reopened) does not cover the newest utterance",
  info.distance <= 2 && info.latestVisible && (await page.getByTestId("trial-new-below").count()) === 0);
await page.evaluate(() => { window.__e2eTurn = undefined; });

// Reviewed note: no draft label.
await openHearing(page, baseState({ current_step: 7, allowed_actions: ["advance:8"], procedure_note: procedureNote(7, true) }));
check("observer: reviewed=true has no draft label", (await note.getByText("Bản nháp, đang chờ nhóm luật duyệt").count()) === 0);

// Paused: "Tiếp tục xem" sends continue only.
await openHearing(page, baseState({ current_step: 8, awaiting: "ai", allowed_actions: ["continue"], version: 40, procedure_note: procedureNote(8) }));
let continueBody = null;
world.turn = (route, body) => {
  continueBody = body;
  world.state = baseState({ current_step: 8, allowed_actions: ["advance:9"], version: 41, procedure_note: procedureNote(8) });
  return fulfillSse(route, sseEvent("utterance", utt(300, 8, "LUAT_SU", "Lời đối đáp mẫu.")) + sseEvent("state", world.state) + sseEvent("done", {}));
};
check("observer paused: 'Tiếp tục xem' and the note", (await page.getByRole("button", { name: "Tiếp tục xem" }).isEnabled()) && (await note.count()) === 1);
await page.getByRole("button", { name: "Tiếp tục xem" }).click();
await page.getByTestId("trial-advance").waitFor({ timeout: 10000 });
check("observer continue: exact body", JSON.stringify(continueBody) === JSON.stringify({ expected_step: 8, expected_version: 40, action: "continue" }));

// 409 on advance re-syncs.
world.turn = (route) => {
  world.state = baseState({ current_step: 9, allowed_actions: ["advance:10"], version: 45, procedure_note: procedureNote(9) });
  return fulfillError(route, 409, "trial_version_mismatch", { state: world.state });
};
await page.getByTestId("trial-advance").click();
await page.getByTestId("trial-soft-notice").waitFor({ timeout: 10000 });
check("observer 409: soft notice, state adopted (note of step 9)", (await note.innerText()).includes("Chú giải mẫu cho bước 9"));

// Guard fuse and the end of the hearing.
await openHearing(page, baseState({ current_step: 9, awaiting: "ai", allowed_actions: [], procedure_note: procedureNote(9) }));
check("observer guard fuse: Bỏ/Xóa only", (await page.getByTestId("trial-guard-exhausted").isVisible()) && (await page.getByRole("button", { name: /Tiếp tục/ }).count()) === 0);
await openHearing(page, baseState({ current_step: 11, status: "completed", awaiting: "none", allowed_actions: [], procedure_note: procedureNote(11) }));
check("observer completed: finished bar with Xem biên bản", (await page.getByTestId("trial-finished").isVisible()) && (await page.getByRole("link", { name: "Xem biên bản" }).count()) >= 1);
await context.close();

// Observer on a phone: the dock with an open note must leave the transcript readable.
for (const width of [320, 390]) {
  ({ context, page } = await open({ viewport: { width, height: 800 }, isMobile: true, hasTouch: true }));
  await openHearing(page, baseState({ current_step: 5, allowed_actions: ["advance:6"], procedure_note: procedureNote(5, false) }), "nguoi_xem");
  info = await scrollInfo(page);
  check(`observer ${width}px: dock with open note ≤ 55% of the screen (${info.dockH}px), no page overflow`, info.dockH <= 440 && (await noPageOverflow(page)));
  check(`observer ${width}px: draft label visible in the open note`, (await draftLabel(page.getByTestId("trial-procedure-note")).count()) === 1);
  if (width === 390) await shot(page, "observer-mobile");
  await context.close();
}

// =============================== 5 tabs at 320 / 390 / 1440 ===============================
resetWorld();
for (const width of [320, 390, 1440]) {
  ({ context, page } = await open({ viewport: { width, height: 800 }, ...(width < 500 ? { isMobile: true, hasTouch: true } : {}) }));
  await openHearing(page, baseState());
  if (width < 1024) await page.getByRole("button", { name: "Hồ sơ vụ án" }).click();
  const scope = width < 1024 ? page.getByRole("dialog", { name: "Hồ sơ vụ án" }) : page.locator('aside[aria-label="Hồ sơ vụ án"]');
  const tablist = scope.getByRole("tablist");
  const listBox = await tablist.boundingBox();
  const tabs = await tablist.getByRole("tab").all();
  let allIn = tabs.length === 5;
  for (const tab of tabs) {
    const box = await tab.boundingBox();
    allIn = allIn && (await tab.isVisible()) && box.x >= listBox.x - 1 && box.x + box.width <= listBox.x + listBox.width + 1;
  }
  check(`${width}px: all 5 tabs visible, no horizontal scroll`, allIn && (await tablist.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)));
  if (width < 1024) {
    await page.keyboard.press("Escape");
    check(`${width}px: drawer closes on Esc, no page overflow`, (await page.getByRole("dialog").count()) === 0 && (await noPageOverflow(page)));
  } else {
    const asideBox = await page.locator('aside[aria-label="Hồ sơ vụ án"]').boundingBox();
    check(`1440px: side panel ${Math.round(asideBox.width)}px (380-420)`, asideBox.width >= 380 && asideBox.width <= 420);
  }
  await context.close();
}

// =============================== Final turn: record summary wait released after 15s ===============================
resetWorld();
({ context, page } = await open());
await installStreamingTurn(context);
await openHearing(page, baseState({ current_step: 10, allowed_actions: ["advance:11"] }));
await page.evaluate((utterance) => {
  window.__e2eTurn = [
    { event: "status", data: { message: "Tuyên án..." } },
    { event: "utterance", data: utterance },
    { event: "status", data: { message: "Đang lập biên bản..." } },
    { delay: 40000, event: "done", data: {} }
  ];
}, aiUtt(500, 11, "Lời tuyên án mẫu."));
// From now on GET already returns the session as completed.
world.state = baseState({ current_step: 11, status: "completed", awaiting: "none", allowed_actions: [], version: 99 });
const t0 = Date.now();
await page.getByTestId("trial-advance").click();
await page.waitForTimeout(3000);
check("record wait: 'Đang lập biên bản' shown", (await page.getByTestId("trial-composer-locked").innerText()).includes("Đang lập biên bản"));
await page.getByTestId("trial-finished").waitFor({ timeout: 20000 });
const waited = (Date.now() - t0) / 1000;
check(`record wait: released after ${waited.toFixed(1)}s (≤ 16.5s)`, waited <= 16.5 && (await page.getByRole("link", { name: "Xem biên bản" }).count()) >= 1);
await context.close();

// =============================== Record and print ===============================
for (const role of ["ksv", "nguoi_xem"]) {
  resetWorld();
  world.role = role;
  ({ context, page } = await open({ permissions: ["clipboard-read", "clipboard-write"] }));
  await page.goto(`${BASE}/trial/${FAKE}/record`);
  await page.getByTestId("trial-record").waitFor({ timeout: 20000 });
  const article = page.getByTestId("trial-record");
  const order = await article.evaluate((el) => [...el.querySelectorAll("p, h2, h3")].filter((n) => n.innerText.trim()).map((n) => n.dataset.testid ?? n.closest("[data-testid]")?.dataset.testid ?? ""));
  if (role === "nguoi_xem") {
    const preamble = page.getByTestId("record-preamble");
    check("record (observer): preamble line shown verbatim", (await preamble.innerText()).trim() === OBSERVER_PREAMBLE);
    check("record (observer): preamble right after the first disclaimer, before the form", order[0] === "record-disclaimer" && order[1] === "record-preamble");
    await shot(page, "record-observer-desktop");
  } else {
    check("record (KSV): no preamble", (await page.getByTestId("record-preamble").count()) === 0);
  }
  check(`record (${role}): disclaimer first and last`, (await page.getByTestId("record-disclaimer").count()) === 2 && order[0] === "record-disclaimer" && order[order.length - 1] === "record-disclaimer");
  check(`record (${role}): blanks, content labels, appendix`,
    (await page.getByTestId("record-blank").count()) >= 3
    && (await page.getByTestId("record-content-label").allInnerTexts()).join() === "Nguyên văn,Tóm tắt,Nguyên văn,Nguyên văn"
    && (await page.getByTestId("record-appendix").innerText()).includes("PHỤ LỤC (ngoài Mẫu số 22-HS)"));
  await page.getByRole("button", { name: "Sao chép văn bản" }).click();
  await page.waitForTimeout(300);
  check(`record (${role}): copy gives exactly the server text`, (await page.evaluate(() => navigator.clipboard.readText())) === recordText({ observer: role === "nguoi_xem" }));
  await page.emulateMedia({ media: "print" });
  check(`record (${role}): print hides banner, buttons and app chrome, keeps the preamble/disclaimers`,
    !(await page.getByTestId("trial-banner").isVisible()) && !(await page.getByRole("button", { name: "In / lưu PDF" }).isVisible())
    && !(await page.locator('button[title="Đăng xuất"]').isVisible()) && (await page.getByTestId("record-disclaimer").first().isVisible())
    && (role === "ksv" || (await page.getByTestId("record-preamble").isVisible())));
  await context.close();
}

// =============================== Thư ký (clerk, contract 5.2, 3.7-3.10) ===============================
const CLERK_MARK = "Ghi chép mẫu số";
const clerkState = (o = {}) => baseState({
  current_step: 1, step_title: "Thư ký báo cáo sự có mặt", allowed_actions: ["speak"], version: 1, text_limits: { min: 100, max: 3000 },
  clerk_prompt: clerkPrompt(1), clerk_report: clerkReport(), ...o
});
const clerkStep = (step, o = {}) => clerkState({ current_step: step, step_title: `Bước ${step}`, allowed_actions: [`advance:${step + 1}`], version: 20 + step, text_limits: null, clerk_report: null, clerk_prompt: clerkPrompt(step), ...o });
const clerkDone = (o = {}) => clerkStep(11, { status: "completed", awaiting: "none", allowed_actions: [], ...o });
const notesPuts = () => world.clerkBodies.filter((b) => b.method === "PUT" && b.path === "/notes");
const notesGets = () => world.requests.filter((r) => r.method === "GET" && r.path.endsWith("/notes")).length;
const notesStatus = (scope) => scope.getByTestId("trial-notes-status");
const waitStatus = (scope, status, timeout = 6000) =>
  scope.locator(`[data-testid="trial-notes-status"][data-status="${status}"]`).waitFor({ timeout }).then(() => true, () => false);
// Confirm dialogs ("Chốt biên bản?") answer `dialogAnswer`; beforeunload is always accepted so a
// navigation never hangs on unsaved text.
let dialogAnswer = true;
const answerDialogs = (page) => page.on("dialog", (dialog) => (dialog.type() === "confirm" && !dialogAnswer ? dialog.dismiss() : dialog.accept()));

// /trial/new: the card is selectable once thu_ky is in config.user_roles, and the case is created.
resetWorld();
world.config = config({ user_roles: ["ksv", "luat_su", "nguoi_xem", "thu_ky"] });
({ context, page } = await open());
await page.goto(`${BASE}/trial/new`);
await page.getByTestId("role-thu_ky").waitFor({ timeout: 20000 });
const clerkCard = page.getByTestId("role-thu_ky");
check("clerk new: card enabled with the contract description, pills Điều 47 and 258, no 'Sắp có'",
  (await clerkCard.getByRole("radio").isEnabled()) && (await clerkCard.innerText()).includes("Báo cáo sự có mặt, ghi chép và tự viết biên bản phiên tòa")
  && (await clerkCard.getByRole("button", { name: "Xem toàn văn Điều 47" }).count()) === 1
  && (await clerkCard.getByRole("button", { name: "Xem toàn văn Điều 258 BLTTHS" }).count()) === 1 && !(await clerkCard.innerText()).includes("Sắp có"));
check("clerk new: Bị cáo and Chủ tọa still 'Sắp có'", (await page.getByTestId("role-bi_cao").getByRole("radio").isDisabled()) && (await page.getByTestId("role-chu_toa").getByRole("radio").isDisabled()));
let clerkCreateBody = null;
world.create = (route, body) => {
  clerkCreateBody = body;
  return fulfillSse(route, sseEvent("status", { message: "Đang dựng hồ sơ vụ án giả định..." }) + sseEvent("session", { session_id: FAKE, title: "Vụ mẫu" })
    + sseEvent("state", clerkState()) + sseEvent("done", {}));
};
await clerkCard.getByRole("radio").click();
await page.getByRole("radio", { name: /Tội trộm cắp tài sản/ }).click();
await shot(page, "clerk-new-desktop");
world.role = "thu_ky";
world.state = clerkState();
await page.getByRole("button", { name: "Tạo vụ án" }).click();
check("clerk new: created, navigated to the hearing", await page.waitForURL(`**/trial/${FAKE}`, { timeout: 15000 }).then(() => true, () => false));
check("clerk new: POST body has exactly the 5 fields, user_role thu_ky",
  clerkCreateBody !== null && Object.keys(clerkCreateBody).sort().join() === "crime_key,has_related_party,user_role,victim_present,witness_count" && clerkCreateBody.user_role === "thu_ky");

// Step 1: the report, prefilled, with the attendance list and the 100-3000 counter.
await page.getByTestId("trial-input").waitFor({ timeout: 20000 });
await page.waitForTimeout(600);
const reportBox = page.getByTestId("trial-input");
check("clerk step 1: textarea prefilled with clerk_report.prefill", (await reportBox.inputValue()) === CLERK_PREFILL);
check("clerk step 1: header 'Vai của bạn: Thư ký phiên tòa', attendance list with one 'Vắng mặt'",
  (await page.getByText("Vai của bạn: Thư ký phiên tòa").count()) === 1 && (await page.getByTestId("trial-attendance").innerText()).includes(FULL.BI_HAI)
  && (await page.getByTestId("trial-attendance").getByText("Vắng mặt", { exact: true }).count()) === 1);
check("clerk step 1: counter shows the server limits (/3.000, tối thiểu 100), no end-slot",
  /\/3\.000 ký tự · tối thiểu 100/.test(await page.getByTestId("trial-counter").innerText()) && (await page.getByTestId("trial-end-slot").count()) === 0);
await shot(page, "clerk-step1-desktop");
await reportBox.fill("a".repeat(99));
const sendBlocked99 = await page.getByTestId("trial-send").isDisabled();
await reportBox.fill("a".repeat(3001));
check("clerk step 1: 99 and 3001 characters blocked", sendBlocked99 && (await page.getByTestId("trial-send").isDisabled()));
await page.getByTestId("trial-clerk-refill").click();
check("clerk step 1: 'Điền lại lời mẫu' restores the template", (await reportBox.inputValue()) === CLERK_PREFILL && (await page.getByTestId("trial-send").isEnabled()));
let reportBody = null;
world.turn = (route, body) => {
  reportBody = body;
  world.state = clerkState({ allowed_actions: ["advance:2"], version: 2, text_limits: null, clerk_report: null });
  return fulfillSse(route, sseEvent("utterance", utt(2, 1, "THU_KY", body.text, { is_user: true, kind: "speech" })) + sseEvent("state", world.state) + sseEvent("done", {}));
};
await page.getByTestId("trial-send").click();
await page.getByTestId("trial-advance").waitFor({ timeout: 10000 });
check("clerk step 1: 'Báo cáo' sends exactly {expected_step 1, expected_version 1, action speak, text}",
  JSON.stringify(reportBody) === JSON.stringify({ expected_step: 1, expected_version: 1, action: "speak", text: CLERK_PREFILL }));
check("clerk after the report: no input left, only 'Sang bước tiếp theo'", (await page.getByTestId("trial-input").count()) === 0 && (await page.getByTestId("trial-send").count()) === 0);
check("clerk: notes read once with GET /notes when the session opened", notesGets() === 1);
await context.close();

// Notes: loaded on open, prompt labelled neutrally, autosave after 2 s of quiet, one PUT, reload keeps them.
resetWorld();
world.role = "thu_ky";
world.clerk.notes = `${CLERK_MARK} 1: Chủ tọa khai mạc phiên tòa.`;
world.clerk.notesUpdatedAt = "2026-10-29T01:05:00.000000+00:00";
({ context, page } = await open());
answerDialogs(page);
await openHearing(page, clerkStep(4));
const sidePanel = page.locator('aside[aria-label="Ghi chép và hồ sơ vụ án"]');
const notesBox = sidePanel.getByTestId("trial-notes-input");
await notesBox.waitFor({ timeout: 10000 });
await page.waitForFunction(() => !document.querySelector('aside [data-testid="trial-notes-input"]')?.disabled, null, { timeout: 10000 });
check("clerk notes: GET /notes text shown, 'Đã lưu lúc' from updated_at", (await notesBox.inputValue()) === world.clerk.notes && /Đã lưu lúc \d{2}:\d{2}/.test(await notesStatus(sidePanel).innerText()));
const promptCard = sidePanel.getByTestId("trial-clerk-prompt");
check("clerk notes: 'Gợi ý ghi chép' with the step prompt, no 'đang chờ nhóm luật duyệt' label anywhere",
  (await promptCard.innerText()).includes("Gợi ý ghi chép") && (await promptCard.innerText()).includes("Câu nhắc ghi chép mẫu cho bước 4")
  && !/đang chờ nhóm luật duyệt/.test(await page.locator("body").innerText()));
check("clerk step 4: observer-style controls (advance only, no input, no procedure note)",
  (await page.getByTestId("trial-advance").isEnabled()) && (await page.getByTestId("trial-input").count()) === 0 && (await page.getByTestId("trial-procedure-note").count()) === 0);
check("clerk side panel: 'Ghi chép' tab first and selected, case file one click away",
  (await sidePanel.getByRole("tab", { name: "Ghi chép" }).getAttribute("aria-selected")) === "true" && (await sidePanel.getByRole("tab", { name: "Hồ sơ vụ án" }).count()) === 1);
await shot(page, "clerk-notes-desktop");
await notesBox.click();
await page.keyboard.press("End");
await notesBox.pressSequentially(" Thêm.", { delay: 120 });
await page.waitForTimeout(1200);
const putsWhileTyping = notesPuts().length;
const savingShown = await waitStatus(sidePanel, "pending", 500);
await page.waitForTimeout(2200);
const typed = `${CLERK_MARK} 1: Chủ tọa khai mạc phiên tòa. Thêm.`;
check(`clerk notes: no PUT while typing (${putsWhileTyping}), 'Đang lưu...' shown`, putsWhileTyping === 0 && savingShown);
check("clerk notes: exactly one PUT after 2 s of quiet, body {text} only", notesPuts().length === 1 && JSON.stringify(notesPuts()[0].body) === JSON.stringify({ text: typed }));
check("clerk notes: 'Đã lưu' after the save", await waitStatus(sidePanel, "saved"));
await sidePanel.getByRole("tab", { name: "Hồ sơ vụ án" }).click();
check("clerk side panel: case file tab shows the panel and 'Mở rộng'", (await sidePanel.getByRole("tablist", { name: "Hồ sơ vụ án" }).count()) === 1 && (await page.getByRole("button", { name: "Mở rộng hồ sơ vụ án" }).count()) === 1);
await sidePanel.getByRole("tab", { name: "Ghi chép" }).click();
await page.reload();
await notesBox.waitFor({ timeout: 15000 });
await page.waitForFunction(() => !document.querySelector('aside [data-testid="trial-notes-input"]')?.disabled, null, { timeout: 10000 });
check("clerk notes: reopening the session shows the saved notes", (await notesBox.inputValue()) === typed);

// A failed save: "Lỗi lưu" with "Thử lại", which then saves.
world.notesPut = (route) => fulfillError(route, 503, "data_unavailable");
await notesBox.fill(`${typed} Lỗi.`);
check("clerk notes: failed save shows 'Lỗi lưu' and 'Thử lại'", (await waitStatus(sidePanel, "error")) && (await notesStatus(sidePanel).innerText()).includes("Lỗi lưu")
  && (await sidePanel.getByTestId("trial-notes-retry").isVisible()));
world.notesPut = null;
await sidePanel.getByTestId("trial-notes-retry").click();
check("clerk notes: 'Thử lại' saves, status back to 'Đã lưu'", (await waitStatus(sidePanel, "saved")) && world.clerk.notes === `${typed} Lỗi.`);
let clerkAdvanceBody = null;
world.turn = (route, body) => {
  clerkAdvanceBody = JSON.stringify(body);
  world.state = clerkStep(5);
  return fulfillSse(route, sseEvent("utterance", aiUtt(400, 5)) + sseEvent("state", world.state) + sseEvent("done", {}));
};
await page.getByTestId("trial-advance").click();
await page.waitForFunction(() => document.querySelector('[data-testid="trial-clerk-prompt"]')?.innerText.includes("bước 5"), null, { timeout: 10000 }).catch(() => {});
check("clerk advance: notes never sent with /turn; the prompt follows the new step",
  clerkAdvanceBody === JSON.stringify({ expected_step: 4, expected_version: 24, action: "advance", target_step: 5 }) && (await promptCard.innerText()).includes("bước 5"));

// Completed: notes still saved. Abandoned: read only, nothing sent.
await openHearing(page, clerkDone());
await page.waitForFunction(() => !document.querySelector('aside [data-testid="trial-notes-input"]')?.disabled, null, { timeout: 10000 });
check("clerk completed: finished bar with 'Mở biên bản'", (await page.getByTestId("trial-finished").isVisible()) && (await page.getByRole("link", { name: "Mở biên bản" }).count()) >= 1);
const putsBefore = notesPuts().length;
await notesBox.fill(`${typed} Sau tuyên án.`);
check("clerk completed: notes still autosave", (await waitStatus(sidePanel, "saved")) && notesPuts().length === putsBefore + 1);
await openHearing(page, clerkStep(6, { status: "abandoned", awaiting: "none", allowed_actions: [] }));
await page.waitForFunction(() => !document.querySelector('aside [data-testid="trial-notes-input"]')?.disabled, null, { timeout: 10000 });
const putsAbandoned = notesPuts().length;
check("clerk abandoned: notes shown read only, 'Chỉ xem'", !(await notesBox.isEditable()) && (await notesBox.inputValue()).includes("Sau tuyên án")
  && (await notesStatus(sidePanel).innerText()).includes("Chỉ xem"));
await page.waitForTimeout(2500);
check("clerk abandoned: no PUT", notesPuts().length === putsAbandoned);
for (const [width, height] of [[1280, 600], [1920, 1080]]) {
  await page.setViewportSize({ width, height });
  await openHearing(page, clerkStep(5));
  const box = await sidePanel.boundingBox();
  check(`clerk hearing ${width}x${height}: no page overflow, side panel inside the viewport`, (await noPageOverflow(page)) && box !== null && box.y + box.height <= height + 1);
  await shot(page, `clerk-hearing-${width}x${height}`);
}
await context.close();

// Phone: notes in a drawer, still one source of saving (the hidden side panel is a view of the same hook).
resetWorld();
world.role = "thu_ky";
world.clerk.notes = `${CLERK_MARK} 2: ghi trên điện thoại.`;
({ context, page } = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }));
answerDialogs(page);
await openHearing(page, clerkState());
info = await scrollInfo(page);
check(`clerk 390px step 1: no page overflow, dock ${info.dockH}px ≤ 70% of the screen`, (await noPageOverflow(page)) && info.dockH <= 590);
await shot(page, "clerk-step1-mobile");
await openHearing(page, clerkStep(5));
await page.getByTestId("trial-notes-open").click();
const notesDrawer = page.getByRole("dialog", { name: "Ghi chép" });
const drawerBox = notesDrawer.getByTestId("trial-notes-input");
await page.waitForFunction(() => !document.querySelector('[role="dialog"] [data-testid="trial-notes-input"]')?.disabled, null, { timeout: 10000 });
check("clerk 390px: 'Ghi chép' drawer with the prompt and the saved notes",
  (await drawerBox.inputValue()) === world.clerk.notes && (await notesDrawer.getByTestId("trial-clerk-prompt").isVisible()));
await drawerBox.fill(`${CLERK_MARK} 2: ghi trên điện thoại, thêm.`);
await page.waitForTimeout(2800);
check("clerk 390px: one PUT for one edit (single saving source), hidden side panel in sync",
  notesPuts().length === 1 && (await page.locator('aside [data-testid="trial-notes-input"]').inputValue()) === `${CLERK_MARK} 2: ghi trên điện thoại, thêm.`);
check("clerk 390px: no page overflow with the drawer open", await noPageOverflow(page));
await shot(page, "clerk-notes-mobile");
await page.keyboard.press("Escape");
await context.close();

// Other roles never touch the clerk routes and keep their panel.
resetWorld();
({ context, page } = await open());
await openHearing(page, baseState(), "ksv");
await openHearing(page, baseState({ current_step: 5, allowed_actions: ["advance:6"], procedure_note: procedureNote(5) }), "nguoi_xem");
await page.waitForTimeout(800);
check("KSV/Người xem: no /notes request, no notes panel, case file aside unchanged",
  !world.requests.some((r) => r.path.endsWith("/notes")) && (await page.getByTestId("trial-notes").count()) === 0
  && (await page.locator('aside[aria-label="Hồ sơ vụ án"]').count()) === 1);
await context.close();

// Record, "Soạn": two sections, "Lưu ý" after saving, counters, finalise saves first.
resetWorld();
world.role = "thu_ky";
world.state = clerkDone();
world.clerk.notes = `${CLERK_MARK} 3: Chủ tọa hỏi bị cáo ${FULL.BI_CAO}; bị cáo khai đã lấy máy tính vì cần tiền.`;
({ context, page } = await open({ permissions: ["clipboard-read", "clipboard-write"] }));
answerDialogs(page);
await page.goto(`${BASE}/trial/${FAKE}/record`);
await page.getByTestId("clerk-section-iv2").waitFor({ timeout: 20000 });
const iv2 = page.getByTestId("clerk-input-iv2");
const iv3 = page.getByTestId("clerk-input-iv3");
const finalizeButton = page.getByTestId("clerk-finalize");
check("clerk record: opens in 'Soạn' with two empty sections, copy/print hidden",
  (await page.getByTestId("clerk-mode-compose").getAttribute("aria-selected")) === "true" && (await iv2.inputValue()) === "" && (await iv3.inputValue()) === ""
  && (await page.getByRole("button", { name: "In / lưu PDF" }).count()) === 0);
check("clerk record: 'Chốt biên bản' locked while a section is empty", await finalizeButton.isDisabled());
check("clerk record: GET's notices shown under 'Lưu ý' (not an error)",
  (await page.getByTestId("clerk-notices-iv2").innerText()).includes("Lưu ý") && (await page.getByTestId("clerk-notices-iv2").innerText()).includes("Mục 2 chưa có nội dung.")
  && !((await page.getByTestId("clerk-notices-iv2").getAttribute("class")) ?? "").includes("red"));
await page.waitForFunction(() => document.querySelector('[data-testid="clerk-copy-notes-iv2"]'), null, { timeout: 10000 }).catch(() => {});
await page.getByTestId("clerk-copy-notes-iv2").click();
check("clerk record: 'Chép từ ghi chép' fills the empty section with the notes", (await iv2.inputValue()) === world.clerk.notes);
check("clerk record: one section empty, still locked", await finalizeButton.isDisabled());
const IV3_TEXT = `Kiểm sát viên Vũ Xuân Việt trình bày luận tội, đề nghị xử bị cáo theo khoản 1 Điều 173 Bộ luật Hình sự. Luật sư Trịnh Thị Thảo bào chữa, nêu bị cáo đã bồi thường 5.000.000 đồng. Trần H. đồng ý với luật sư. Hai bên đối đáp một vòng về tình tiết giảm nhẹ của bị cáo.`;
await iv3.fill(IV3_TEXT);
check("clerk record: both sections written, 'Chốt biên bản' enabled", await finalizeButton.isEnabled());
await page.getByTestId("clerk-save").click();
await page.waitForFunction(() => document.querySelector('[data-testid="clerk-notices-iv3"]')?.innerText.includes("Trần H."), null, { timeout: 10000 }).catch(() => {});
const draftPuts = () => world.clerkBodies.filter((b) => b.method === "PUT" && b.path === "/record/draft");
check("clerk record: PUT /record/draft body is exactly {iv2, iv3}",
  draftPuts().length === 1 && JSON.stringify(draftPuts()[0].body) === JSON.stringify({ iv2: world.clerk.notes, iv3: IV3_TEXT }));
const iv3Notices = page.getByTestId("clerk-notices-iv3");
check("clerk record: notices after saving - unknown_name (with the full-name hint) and unknown_amount, as 'Lưu ý'",
  (await iv3Notices.locator('[data-code="unknown_name"]').count()) === 1 && (await iv3Notices.innerText()).includes("tên đầy đủ")
  && (await iv3Notices.locator('[data-code="unknown_amount"]').count()) === 1 && (await iv3Notices.innerText()).includes("Lưu ý"));
check("clerk record: 'Đã lưu lúc' after the save", /Đã lưu lúc/.test(await page.getByTestId("clerk-save-status").innerText()));
await shot(page, "clerk-record-compose-desktop");
await iv2.fill(`**Chủ tọa** hỏi bị cáo ${FULL.BI_CAO} về diễn biến; bị cáo khai đã lấy máy tính xách tay vì cần tiền trả nợ và thừa nhận hành vi. Người làm chứng ${FULL.NLC_1} xác nhận đã nhìn thấy bị cáo rời khỏi nhà bị hại vào buổi tối hôm đó.`);
check("clerk record: edits after saving mark the notices as stale", (await page.getByTestId("clerk-notices-iv3").count()) === 1 && (await page.getByTestId("clerk-save-status").innerText()).includes("chưa lưu"));
await page.getByTestId("clerk-save").click();
await page.waitForFunction(() => !document.querySelector('[data-testid="clerk-input-iv2"]').value.includes("**"), null, { timeout: 10000 }).catch(() => {});
check("clerk record: the server's cleaned text replaces the textarea", !(await iv2.inputValue()).includes("**") && (await iv2.inputValue()).startsWith("Chủ tọa hỏi"));
const savedIv2 = await iv2.inputValue();
await iv2.fill("a".repeat(4001));
const longCounter = page.getByTestId("clerk-counter-iv2");
const longOk = (await longCounter.getAttribute("data-length")) === "long" && ((await longCounter.getAttribute("class")) ?? "").includes("amber") && (await page.getByTestId("clerk-save").isEnabled());
await iv2.fill("a".repeat(6001));
check("clerk record: > 4000 soft warning (saving allowed); > 6000 hard cap blocks save and finalise",
  longOk && (await longCounter.getAttribute("data-length")) === "over" && (await page.getByTestId("clerk-save").isDisabled()) && (await finalizeButton.isDisabled()));
await iv2.fill(savedIv2);
await page.getByTestId("clerk-mode-preview").click();
await page.getByTestId("trial-record").waitFor({ timeout: 10000 });
const preview = page.getByTestId("trial-record");
check("clerk preview: draft line, the saved IV.2/IV.3 with the author note and 'Người học soạn'",
  (await page.getByTestId("record-preamble").innerText()).includes("Bản nháp") && (await preview.getByTestId("record-user-text").first().innerText()).includes("Chủ tọa hỏi bị cáo")
  && (await preview.getByTestId("record-author-note").count()) === 2 && (await preview.getByText("Người học soạn").count()) === 2);
await page.getByTestId("clerk-mode-compose").click();
check("clerk record: back to 'Soạn' keeps the text", (await iv2.inputValue()) === savedIv2 && (await iv3.inputValue()) === IV3_TEXT);
// Cancelled confirm: nothing is sent.
dialogAnswer = false;
const bodiesBefore = world.clerkBodies.length;
await finalizeButton.click();
await page.waitForTimeout(500);
check("clerk finalise: cancelling the confirm sends nothing", world.clerkBodies.length === bodiesBefore);
dialogAnswer = true;
const FINAL_IV3 = `${IV3_TEXT} Bị cáo xin giảm nhẹ.`;
await iv3.fill(FINAL_IV3);
await finalizeButton.click();
await page.getByTestId("trial-record").waitFor({ timeout: 10000 });
await page.waitForTimeout(300);
const lastTwo = world.clerkBodies.slice(-2).map((b) => `${b.method} ${b.path}`);
check("clerk finalise: saves the draft first (latest text), then POST /record/finalize",
  lastTwo.join() === "PUT /record/draft,POST /record/finalize" && world.clerkBodies.at(-2).body.iv3 === FINAL_IV3);
check("clerk finalised: view only - no textarea, no mode tabs, no draft line, 'Đã chốt'",
  (await page.locator("textarea").count()) === 0 && (await page.getByTestId("clerk-mode-compose").count()) === 0
  && (await page.getByTestId("record-preamble").count()) === 0 && (await page.getByTestId("clerk-record-status").innerText()).includes("Đã chốt"));
check("clerk finalised: IV.2/IV.3 labelled 'Người học soạn' with the author note, other sections as before",
  (await page.getByTestId("record-author-note").first().innerText()).includes("Do Thư ký (người học) ghi")
  && (await page.getByTestId("record-content-label").allInnerTexts()).join() === "Nguyên văn,Người học soạn,Người học soạn,Nguyên văn");
await page.getByRole("button", { name: "Sao chép văn bản" }).click();
await page.waitForTimeout(300);
check("clerk finalised: copy gives the server text", (await page.evaluate(() => navigator.clipboard.readText())) === clerkRecordText({ iv2: world.clerk.iv2, iv3: world.clerk.iv3, finalized: true }));
await shot(page, "clerk-record-final-desktop");
await page.goto(`${BASE}/trial/${FAKE}/record`);
await page.getByTestId("trial-record").waitFor({ timeout: 20000 });
check("clerk finalised: reopening shows the view directly", (await page.locator("textarea").count()) === 0 && (await page.getByTestId("clerk-record-status").innerText()).includes("Đã chốt"));
for (const [width, height] of [[1440, 900], [1920, 1080]]) {
  await page.setViewportSize({ width, height });
  await page.waitForTimeout(300);
  const gap = await page.evaluate(() => {
    const card = document.querySelector('[data-testid="trial-record"]');
    let scroller = card.parentElement;
    while (scroller && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
    scroller.scrollTop = scroller.scrollHeight;
    return document.documentElement.scrollHeight - window.innerHeight;
  });
  check(`clerk record ${width}x${height}: no page scroll below the frame (${gap}px), no overflow`, gap <= 0 && (await noPageOverflow(page)));
}
await context.close();

// Record conflicts: every refusal is a Vietnamese message on the same screen, never a blank page.
async function openClerkRecord(viewport = { width: 1440, height: 900 }) {
  resetWorld();
  world.role = "thu_ky";
  world.state = clerkDone();
  world.clerk.iv2 = "Mục hai đã lưu từ trước, đủ dài để không bị coi là trống.";
  world.clerk.draftUpdatedAt = "2026-10-29T02:00:00.000000+00:00";
  const opened = await open({ viewport, ...(viewport.width < 500 ? { isMobile: true, hasTouch: true } : {}) });
  answerDialogs(opened.page);
  await opened.page.goto(`${BASE}/trial/${FAKE}/record`);
  await opened.page.getByTestId("clerk-section-iv2").waitFor({ timeout: 20000 });
  return opened;
}
const clerkErrorText = (page) => page.getByTestId("clerk-error").waitFor({ timeout: 10000 }).then(() => page.getByTestId("clerk-error").innerText(), () => "");

({ context, page } = await openClerkRecord());
check("clerk record: saved draft loaded into the editor", (await page.getByTestId("clerk-input-iv2").inputValue()) === world.clerk.iv2);
await page.getByTestId("clerk-input-iv3").fill("Mục ba viết trên màn hình.");
world.finalize = (route) => fulfillError(route, 409, "trial_record_section_empty", { state: world.state });
await page.getByTestId("clerk-finalize").click();
check("clerk 409 trial_record_section_empty: Vietnamese message, editor still there", (await clerkErrorText(page)).includes("còn trống") && (await page.getByTestId("clerk-input-iv3").isVisible()));
world.finalize = null;
world.draftPut = (route) => fulfillError(route, 409, "trial_not_clerk", { state: world.state });
await page.getByTestId("clerk-input-iv3").fill("Mục ba sửa lần hai.");
await page.getByTestId("clerk-save").click();
await page.waitForFunction(() => document.querySelector('[data-testid="clerk-error"]')?.innerText.includes("Thư ký"), null, { timeout: 10000 }).catch(() => {});
check("clerk 409 trial_not_clerk: Vietnamese message", (await page.getByTestId("clerk-error").innerText()).includes("không phải vai Thư ký"));
world.draftPut = (route) => fulfillError(route, 422, "validation_error");
await page.getByTestId("clerk-save").click();
await page.waitForFunction(() => document.querySelector('[data-testid="clerk-error"]')?.innerText.includes("6.000"), null, { timeout: 10000 }).catch(() => {});
check("clerk 422: clear message about the 6.000 cap", (await page.getByTestId("clerk-error").innerText()).includes("tối đa 6.000 ký tự"));
world.draftPut = (route) => route.abort("failed");
await page.getByTestId("clerk-save").click();
await page.waitForFunction(() => document.querySelector('[data-testid="clerk-error"]')?.innerText.includes("Mất kết nối"), null, { timeout: 10000 }).catch(() => {});
check("clerk network error: 'Mất kết nối', text kept", (await page.getByTestId("clerk-error").innerText()).includes("Mất kết nối") && (await page.getByTestId("clerk-input-iv3").inputValue()) === "Mục ba sửa lần hai.");
world.draftPut = (route) => {
  world.clerk.finalized = true;
  world.clerk.iv3 = "Mục ba đã chốt ở cửa sổ khác.";
  return fulfillError(route, 409, "trial_record_finalized", { state: world.state });
};
await page.getByTestId("clerk-save").click();
await page.getByTestId("trial-record").waitFor({ timeout: 10000 });
check("clerk 409 trial_record_finalized: switches to the view with a notice",
  (await page.getByTestId("clerk-record-notice").innerText()).includes("đã được chốt") && (await page.locator("textarea").count()) === 0
  && (await page.getByTestId("trial-record").innerText()).includes("Mục ba đã chốt ở cửa sổ khác."));
await context.close();

// Record before the hearing ends: the existing "chưa hoàn thành" message.
resetWorld();
world.role = "thu_ky";
world.state = clerkStep(6);
({ context, page } = await open());
await page.goto(`${BASE}/trial/${FAKE}/record`);
check("clerk record before completion: 'chỉ có khi phiên tòa đã hoàn thành', not blank",
  await page.getByText("Biên bản chỉ có khi phiên tòa đã hoàn thành.").waitFor({ timeout: 15000 }).then(() => true, () => false));
await context.close();

// Phone and a short laptop screen: the editor fits, no horizontal scroll.
for (const viewport of [{ width: 390, height: 844 }, { width: 1280, height: 600 }]) {
  ({ context, page } = await openClerkRecord(viewport));
  const actions = await page.getByTestId("clerk-actions").boundingBox();
  check(`clerk record ${viewport.width}x${viewport.height}: no page overflow, action bar on screen`,
    (await noPageOverflow(page)) && actions !== null && actions.y + actions.height <= viewport.height + 1 && actions.x >= -1);
  await shot(page, `clerk-record-compose-${viewport.width}x${viewport.height}`);
  await context.close();
}

// =============================== Bị cáo (defendant, contract 5.3, 3.3) ===============================
const DEF_MARK = "Câu trả lời mẫu của bị cáo";
const q2 = defendantQuestion(60, 2, "CHU_TOA", "Bị cáo cho biết họ tên, tuổi, nơi cư trú, nghề nghiệp, trình độ học vấn, tiền án, tiền sự?", { prefill: IDENTITY_PREFILL });
const q2b = defendantQuestion(62, 2, "CHU_TOA", "Bị cáo có đề nghị thay đổi người tiến hành tố tụng không?");
const q4 = defendantQuestion(70, 4, "HOI_THAM_1", "Bị cáo lấy chiếc máy tính vào lúc nào?", { decline: true });
const q4b = defendantQuestion(72, 4, "CHU_TOA", "Sau đó bị cáo mang tài sản đi đâu?", { decline: true });
const q9 = defendantQuestion(90, 9, "CHU_TOA", "Bị cáo được nói lời sau cùng.");
const defState = (step, o = {}) => baseState({ current_step: step, step_title: `Bước ${step}`, version: 40 + step, text_limits: { min: 1, max: 1500 }, ...o });
const asking = (step, question, o = {}) => defState(step, { allowed_actions: question.pending.decline_note ? ["speak", "decline"] : ["speak"], pending_question: question.pending, ...o });
const userUtt = (seq, step, text, o = {}) => utt(seq, step, "BI_CAO", text, { is_user: true, ...o });
const withLines = (...lines) => [...makeUtterances(10), ...lines];
const sentTurns = [];
// A /turn answer: the student's line (if any), the AI's next lines, then the new state.
const answerTurn = (lines, next) => (route, body) => {
  sentTurns.push(body);
  world.state = next;
  world.utterances.push(...lines);
  return fulfillSse(route, lines.map((u) => sseEvent("utterance", u)).join("") + sseEvent("state", next) + sseEvent("done", {}));
};
const pendingQuote = (page) => page.getByTestId("trial-pending-question");

// /trial/new: the card is selectable once bi_cao is in config.user_roles, and the case is created.
resetWorld();
world.config = config({ user_roles: ["bi_cao", "ksv", "luat_su", "nguoi_xem", "thu_ky"] });
({ context, page } = await open());
answerDialogs(page);
await page.goto(`${BASE}/trial/new`);
await page.getByTestId("role-bi_cao").waitFor({ timeout: 20000 });
const defCard = page.getByTestId("role-bi_cao");
check("defendant new: card enabled, contract description, pill Điều 61 BLTTHS, no 'Sắp có'",
  (await defCard.getByRole("radio").isEnabled()) && (await defCard.innerText()).includes("Trả lời xét hỏi, tự bào chữa và nói lời sau cùng")
  && (await defCard.getByRole("button", { name: "Xem toàn văn Điều 61 BLTTHS" }).count()) === 1 && !(await defCard.innerText()).includes("Sắp có"));
check("defendant new: Chủ tọa still 'Sắp có'", (await page.getByTestId("role-chu_toa").getByRole("radio").isDisabled()) && (await page.getByTestId("role-chu_toa").innerText()).includes("Sắp có"));
let defCreateBody = null;
world.create = (route, body) => {
  defCreateBody = body;
  return fulfillSse(route, sseEvent("session", { session_id: FAKE, title: "Vụ mẫu" }) + sseEvent("state", baseState()) + sseEvent("done", {}));
};
await defCard.getByRole("radio").click();
await page.getByRole("radio", { name: /Tội trộm cắp tài sản/ }).click();
await shot(page, "defendant-new-desktop");
world.role = "bi_cao";
world.utterances = withLines(q2.utterance);
world.state = asking(2, q2);
await page.getByRole("button", { name: "Tạo vụ án" }).click();
check("defendant new: created with exactly the 5 fields, user_role bi_cao",
  (await page.waitForURL(`**/trial/${FAKE}`, { timeout: 15000 }).then(() => true, () => false))
  && Object.keys(defCreateBody).sort().join() === "crime_key,has_related_party,user_role,victim_present,witness_count" && defCreateBody.user_role === "bi_cao");

// Step 2: the identity question, answer prefilled from pending_question.prefill, no decline.
const answerBox = page.getByTestId("trial-input");
await answerBox.waitFor({ timeout: 20000 });
await page.waitForTimeout(600);
check("defendant step 2: identity answer prefilled from pending_question.prefill", (await answerBox.inputValue()) === IDENTITY_PREFILL);
check("defendant step 2: the waiting question quoted with who asks it",
  (await pendingQuote(page).innerText()).includes("Câu hỏi đang chờ · Chủ tọa Nguyễn Văn An") && (await pendingQuote(page).innerText()).includes(q2.pending.text));
check("defendant step 2: counter 1-1.500, 'Trả lời', no 'Từ chối trả lời', no end-slot",
  /\/1\.500 ký tự/.test(await page.getByTestId("trial-counter").innerText()) && (await page.getByTestId("trial-send").innerText()).includes("Trả lời")
  && (await page.getByTestId("trial-decline").count()) === 0 && (await page.getByTestId("trial-end-slot").count()) === 0);
check("defendant: header 'Vai của bạn: Bị cáo'", (await page.getByText("Vai của bạn: Bị cáo").count()) === 1);
const defAside = page.locator('aside[aria-label="Hồ sơ vụ án"]');
const roleTab = defAside.getByRole("tab", { name: "Vai của bạn" });
check("defendant panel: 'Vai của bạn' is the first tab", (await defAside.getByRole("tab").first().innerText()).trim() === "Vai của bạn");
await roleTab.click();
const brief = defAside.getByTestId("trial-role-brief");
check("defendant panel: role_brief with the note verbatim first, stance, knowledge list, demeanor; the tab is the selected one",
  (await roleTab.getAttribute("aria-selected")) === "true" && (await defAside.getByRole("tab", { name: "Tóm tắt" }).getAttribute("aria-selected")) === "false"
  && (await defAside.getByTestId("trial-role-brief-note").innerText()).trim() === ROLE_BRIEF_NOTE && (await brief.innerText()).includes("Lập trường mẫu")
  && (await brief.locator("li").count()) === 2 && (await brief.innerText()).includes("Bình tĩnh, hơi lo lắng"));
check("defendant: the role brief is never put in the answer box", !(await answerBox.inputValue()).includes("Lập trường mẫu"));
await page.mouse.move(0, 0);
await page.waitForTimeout(300);
await shot(page, "defendant-step2-desktop");
await context.close();

// Answering: exact body, the box clears, the next question is quoted (no prefill).
sentTurns.length = 0;
resetWorld();
world.role = "bi_cao";
world.utterances = withLines(q2.utterance);
({ context, page } = await open());
answerDialogs(page);
await openHearing(page, asking(2, q2));
world.turn = answerTurn([userUtt(61, 2, IDENTITY_PREFILL), q2b.utterance], asking(2, q2b, { version: 43 }));
await page.getByTestId("trial-send").click();
await page.waitForFunction((text) => document.querySelector('[data-testid="trial-pending-question"]')?.innerText.includes(text), q2b.pending.text, { timeout: 10000 }).catch(() => {});
check("defendant answer: body exactly {expected_step, expected_version, action speak, text}, no addressee",
  JSON.stringify(sentTurns[0]) === JSON.stringify({ expected_step: 2, expected_version: 42, action: "speak", text: IDENTITY_PREFILL }));
check("defendant answer: shown as the student's line, box cleared, next question quoted",
  (await page.locator('[data-seq="61"][data-testid="trial-user-utterance"]').innerText()).includes("Bạn · Bị cáo")
  && (await page.getByTestId("trial-input").inputValue()) === "" && (await pendingQuote(page).innerText()).includes(q2b.pending.text));
await context.close();

// Steps 4-5: decline with a confirm, the neutral note with the server's citations, 1500 cap.
sentTurns.length = 0;
resetWorld();
world.role = "bi_cao";
world.utterances = withLines(q4.utterance);
({ context, page } = await open());
answerDialogs(page);
await openHearing(page, asking(4, q4));
check("defendant step 4: 'Từ chối trả lời' next to 'Trả lời', question from Hội thẩm quoted",
  (await page.getByTestId("trial-decline").isVisible()) && (await pendingQuote(page).innerText()).includes("Câu hỏi đang chờ · Hội thẩm"));
await page.getByTestId("trial-decline-note-toggle").click();
const declineNoteBox = page.getByTestId("trial-decline-note");
check("defendant decline note: server text and both citations as article pills, no review badge",
  (await declineNoteBox.innerText()).includes(DECLINE_TEXT)
  && (await declineNoteBox.getByRole("button", { name: "Xem toàn văn điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự" }).count()) === 1
  && (await declineNoteBox.getByRole("button", { name: "Xem toàn văn điểm b khoản 2 Điều 308 Bộ luật Tố tụng hình sự" }).count()) === 1
  && !/đang chờ nhóm luật duyệt/.test(await page.locator("body").innerText()));
await page.getByTestId("trial-input").fill("x".repeat(1501));
check("defendant step 4: 1501 characters blocked", (await page.getByTestId("trial-send").isDisabled()) && /1\.501\/1\.500/.test(await page.getByTestId("trial-counter").innerText()));
await page.getByTestId("trial-input").fill("");
await shot(page, "defendant-step4-desktop");
world.turn = answerTurn([userUtt(71, 4, "Bị cáo không trả lời câu hỏi này.", { kind: "procedural" }), q4b.utterance], asking(4, q4b, { version: 45 }));
dialogAnswer = false;
await page.getByTestId("trial-decline").click();
await page.waitForTimeout(500);
check("defendant decline: cancelling the confirm sends nothing", sentTurns.length === 0);
dialogAnswer = true;
await page.getByTestId("trial-decline").click();
await page.waitForFunction((text) => document.querySelector('[data-testid="trial-pending-question"]')?.innerText.includes(text), q4b.pending.text, { timeout: 10000 }).catch(() => {});
check("defendant decline: body exactly {expected_step 4, expected_version 44, action decline}",
  JSON.stringify(sentTurns[0]) === JSON.stringify({ expected_step: 4, expected_version: 44, action: "decline" }));
const declineLine = page.locator('[data-seq="71"]');
check("defendant decline: the procedural line on the student's side, neutral (not the primary bubble), next question waits",
  (await declineLine.getAttribute("data-testid")) === "trial-user-procedural" && (await declineLine.innerText()).includes("Bạn · Bị cáo")
  && (await declineLine.innerText()).includes("Bị cáo không trả lời câu hỏi này.") && !((await declineLine.innerHTML()).includes("bg-primary"))
  && (await pendingQuote(page).innerText()).includes(q4b.pending.text));
// 409 trial_action_not_allowed: soft notice, state and transcript re-read, no blank screen.
world.turn = (route, body) => {
  sentTurns.push(body);
  world.state = defState(4, { allowed_actions: ["advance:5"], version: 50, text_limits: null });
  return fulfillError(route, 409, "trial_action_not_allowed", { state: world.state });
};
let defGets = world.requests.filter((r) => r.method === "GET" && r.path.endsWith(FAKE)).length;
await page.getByTestId("trial-decline").click();
await page.getByTestId("trial-soft-notice").waitFor({ timeout: 10000 });
check("defendant 409 trial_action_not_allowed: soft Vietnamese notice, state adopted, transcript re-read",
  (await page.getByTestId("trial-soft-notice").innerText()).includes("Phiên tòa vừa thay đổi trạng thái") && (await page.getByTestId("trial-advance").isVisible())
  && world.requests.filter((r) => r.method === "GET" && r.path.endsWith(FAKE)).length > defGets);
// HTTP refusals before streaming: Vietnamese, on the screen, the answer kept.
const refusals = [
  [422, "validation_error", "Dữ liệu gửi lên không hợp lệ"],
  [429, "rate_limit_exceeded", "thao tác hơi nhanh"],
  [503, "data_unavailable", "Máy chủ dữ liệu đang tạm gián đoạn"],
  [401, "http_error", "Phiên đăng nhập đã hết hạn"]
];
for (const [status, code, wording] of refusals) {
  await openHearing(page, asking(4, q4b));
  world.turn = (route) => fulfillError(route, status, code);
  await page.getByTestId("trial-input").fill(`${DEF_MARK} ${status}.`);
  await page.getByTestId("trial-send").click();
  await page.getByTestId("trial-error").waitFor({ timeout: 10000 }).catch(() => {});
  check(`defendant ${status} ${code}: '${wording}' on screen, answer kept`,
    (await page.getByTestId("trial-error").innerText().catch(() => "")).includes(wording) && (await page.getByTestId("trial-input").inputValue()) === `${DEF_MARK} ${status}.`);
}
await openHearing(page, asking(4, q4b));
world.turn = (route) => route.abort("failed");
await page.getByTestId("trial-input").fill(`${DEF_MARK} mạng.`);
await page.getByTestId("trial-send").click();
check("defendant network error: 'Mất kết nối', state re-read", (await page.getByTestId("trial-error").waitFor({ timeout: 10000 }).then(() => page.getByTestId("trial-error").innerText(), () => "")).includes("Mất kết nối"));
await openHearing(page, asking(4, q4b));
world.turn = (route) => {
  world.state = asking(4, q4b, { version: 60 });
  return fulfillError(route, 409, "trial_version_mismatch", { state: world.state });
};
await page.getByTestId("trial-input").fill(`${DEF_MARK} 409.`);
await page.getByTestId("trial-send").click();
await page.getByTestId("trial-soft-notice").waitFor({ timeout: 10000 });
check("defendant 409 version mismatch: soft notice, answer kept", (await page.getByTestId("trial-input").inputValue()) === `${DEF_MARK} 409.`);
await context.close();

// Steps 7-8: the presiding judge's invitation quoted, "Không bổ sung" / "Không có ý kiến", 1-3000.
sentTurns.length = 0;
resetWorld();
world.role = "bi_cao";
const invite7 = utt(80, 7, "CHU_TOA", "Bị cáo Trần Đức Hùng có bổ sung ý kiến bào chữa cho mình không?", { kind: "procedural" });
world.utterances = withLines(utt(79, 7, "LUAT_SU", "Bài bào chữa mẫu."), invite7);
({ context, page } = await open());
answerDialogs(page);
await openHearing(page, defState(7, { allowed_actions: ["speak", "end_slot"], text_limits: { min: 1, max: 3000 } }));
check("defendant step 7: the presiding judge's invitation quoted ('Chủ tọa mời')",
  (await pendingQuote(page).innerText()).includes("Chủ tọa mời") && (await pendingQuote(page).innerText()).includes(invite7.text));
check("defendant step 7: 'Không bổ sung' button, counter /3.000, no decline",
  (await page.getByTestId("trial-end-slot").innerText()).trim() === "Không bổ sung" && /\/3\.000 ký tự/.test(await page.getByTestId("trial-counter").innerText())
  && (await page.getByTestId("trial-decline").count()) === 0);
await page.getByTestId("trial-input").fill("y".repeat(3001));
check("defendant step 7: 3001 characters blocked", await page.getByTestId("trial-send").isDisabled());
await page.getByTestId("trial-input").fill("");
await shot(page, "defendant-step7-desktop");
world.turn = answerTurn([userUtt(81, 7, "Bị cáo không bổ sung ý kiến bào chữa.", { kind: "procedural" })], defState(7, { allowed_actions: ["advance:8"], version: 48, text_limits: null }));
await page.getByTestId("trial-end-slot").click();
await page.getByTestId("trial-advance").waitFor({ timeout: 10000 });
check("defendant 'Không bổ sung': body exactly {expected_step 7, expected_version 47, action end_slot}; line on the student's side",
  JSON.stringify(sentTurns[0]) === JSON.stringify({ expected_step: 7, expected_version: 47, action: "end_slot" })
  && (await page.locator('[data-seq="81"]').getAttribute("data-testid")) === "trial-user-procedural");
const invite8 = utt(85, 8, "CHU_TOA", "Bị cáo Trần Đức Hùng có ý kiến tranh luận, đối đáp gì với Kiểm sát viên không?", { kind: "procedural" });
world.utterances.push(invite8);
await openHearing(page, defState(8, { allowed_actions: ["speak", "end_slot"], text_limits: { min: 1, max: 3000 } }));
check("defendant step 8: 'Không có ý kiến' and the step-8 invitation", (await page.getByTestId("trial-end-slot").innerText()).trim() === "Không có ý kiến"
  && (await pendingQuote(page).innerText()).includes(invite8.text) && (await page.getByTestId("trial-send").innerText()).includes("Trình bày"));
const DEBATE = `${DEF_MARK}: bị cáo không đồng ý với giá trị tài sản.`;
world.turn = answerTurn([userUtt(86, 8, DEBATE), utt(87, 8, "KSV", "Kiểm sát viên đáp lại (mẫu).")], defState(8, { allowed_actions: ["advance:9"], version: 49, text_limits: null }));
await page.getByTestId("trial-input").fill(DEBATE);
await page.getByTestId("trial-send").click();
await page.getByTestId("trial-advance").waitFor({ timeout: 10000 });
check("defendant step 8: speaking sends speak with the text, then only 'Sang bước tiếp theo'",
  JSON.stringify(sentTurns[1]) === JSON.stringify({ expected_step: 8, expected_version: 48, action: "speak", text: DEBATE }) && (await page.getByTestId("trial-input").count()) === 0);

// Step 9: the last word - one answer, no decline, no end-slot, no question box afterwards.
world.utterances.push(q9.utterance);
await openHearing(page, asking(9, q9, { text_limits: { min: 1, max: 3000 } }));
check("defendant step 9: 'Nói lời sau cùng', no decline, no end-slot, large box",
  (await page.getByTestId("trial-send").innerText()).includes("Nói lời sau cùng") && (await page.getByTestId("trial-decline").count()) === 0
  && (await page.getByTestId("trial-end-slot").count()) === 0 && (await pendingQuote(page).innerText()).includes(q9.pending.text));
const LAST_WORD = `${DEF_MARK}: bị cáo xin Hội đồng xét xử khoan hồng.`;
world.turn = answerTurn([userUtt(91, 9, LAST_WORD)], defState(9, { allowed_actions: ["advance:10"], version: 50, text_limits: null }));
await page.getByTestId("trial-input").fill(LAST_WORD);
await page.getByTestId("trial-send").click();
await page.getByTestId("trial-advance").waitFor({ timeout: 10000 });
check("defendant step 9: after the last word no input or question remains",
  (await page.getByTestId("trial-input").count()) === 0 && (await pendingQuote(page).count()) === 0);
await context.close();

// Record: the same layout as KSV (summary IV.2, verbatim IV.3/IV.4).
resetWorld();
world.role = "bi_cao";
({ context, page } = await open());
await page.goto(`${BASE}/trial/${FAKE}/record`);
await page.getByTestId("trial-record").waitFor({ timeout: 20000 });
check("defendant record: unchanged layout (labels as KSV), no clerk editor, no draft line",
  (await page.getByTestId("record-content-label").allInnerTexts()).join() === "Nguyên văn,Tóm tắt,Nguyên văn,Nguyên văn"
  && (await page.locator("textarea").count()) === 0 && (await page.getByTestId("record-preamble").count()) === 0);
await context.close();

// Other roles: no "Vai của bạn" tab, nothing breaks without the key.
for (const role of ["ksv", "luat_su", "nguoi_xem", "thu_ky"]) {
  resetWorld();
  world.role = role;
  ({ context, page } = await open());
  const state = role === "nguoi_xem" ? baseState({ current_step: 5, allowed_actions: ["advance:6"], procedure_note: procedureNote(5) })
    : role === "thu_ky" ? baseState({ current_step: 5, allowed_actions: ["advance:6"], clerk_prompt: clerkPrompt(5) }) : baseState();
  await openHearing(page, state, role);
  if (role === "thu_ky") await page.locator("aside").getByRole("tab", { name: "Hồ sơ vụ án" }).click();
  check(`${role}: no 'Vai của bạn' tab, no decline, no pending-question quote`,
    (await page.getByRole("tab", { name: "Vai của bạn" }).count()) === 0 && (await page.getByTestId("trial-decline").count()) === 0
    && (await pendingQuote(page).count()) === 0 && (await page.getByRole("tab", { name: "Tóm tắt" }).count()) >= 1);
  await context.close();
}

// Viewports: phone (drawer has the tab), short laptop, large desktop.
resetWorld();
world.role = "bi_cao";
world.utterances = withLines(q4.utterance);
({ context, page } = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }));
await openHearing(page, asking(4, q4));
info = await scrollInfo(page);
check(`defendant 390px step 4: no page overflow, dock ${info.dockH}px ≤ 60% of the screen, latest line visible`,
  (await noPageOverflow(page)) && info.dockH <= 506 && info.latestVisible);
await shot(page, "defendant-step4-mobile");
await page.getByRole("button", { name: "Hồ sơ vụ án" }).click();
const defDrawer = page.getByRole("dialog", { name: "Hồ sơ vụ án" });
await defDrawer.getByRole("tab", { name: "Vai của bạn" }).click();
check("defendant 390px: drawer has 'Vai của bạn' with the note, all 6 tabs inside, no overflow",
  (await defDrawer.getByTestId("trial-role-brief-note").innerText()).trim() === ROLE_BRIEF_NOTE && (await defDrawer.getByRole("tab").count()) === 6
  && (await defDrawer.getByRole("tablist").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)) && (await noPageOverflow(page)));
await shot(page, "defendant-role-brief-mobile");
await context.close();
for (const [width, height] of [[1280, 600], [1440, 900], [1920, 1080]]) {
  ({ context, page } = await open({ viewport: { width, height } }));
  await openHearing(page, asking(4, q4));
  info = await scrollInfo(page);
  check(`defendant ${width}x${height}: no page overflow, latest line above the dock`, (await noPageOverflow(page)) && info.latestVisible);
  if (width !== 1440) await shot(page, `defendant-step4-${width}x${height}`);
  await context.close();
}

// =============================== Chủ tọa (presiding judge, contract 5.4) ===============================
const ALL_ROLES = ["bi_cao", "chu_toa", "ksv", "luat_su", "nguoi_xem", "thu_ky"];
const chairBodies = [];
const chairAside = (page) => page.locator('aside[aria-label="Điều hành và hồ sơ vụ án"]');
const chairRow = (scope, key) => scope.getByTestId(`chair-item-${key}`);
const settle = async (page) => {
  await page.waitForTimeout(250);
  await page.waitForFunction(() => !document.querySelector('[data-testid="trial-status"]'), null, { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(150);
};
const oneClick = async (page, key, scope = chairAside(page)) => {
  await chairRow(scope, key).getByTestId("chair-use-template").click();
  await settle(page);
};
const advanceChair = async (page) => {
  await page.getByTestId("trial-advance").click();
  await settle(page);
};
const lastBody = () => chairBodies[chairBodies.length - 1];
const thuKyLine = () => utt(1, 1, "THU_KY", "Báo cáo Hội đồng xét xử, những người được triệu tập đều có mặt.", { kind: "procedural" });
// A presiding session already at `step` (every earlier step done), the simulator answering /turn.
async function openChair(page, o = {}, lines = [thuKyLine()]) {
  const c = newChair(o);
  world.role = "chu_toa";
  world.utterances = [...lines];
  world.turn = chairTurn(world, c, chairBodies);
  await openHearing(page, chairState(c), "chu_toa");
  return c;
}

// /trial/new: the card is selectable once chu_toa is in config.user_roles.
resetWorld();
chairBodies.length = 0;
world.config = config({ user_roles: ALL_ROLES });
({ context, page } = await open());
answerDialogs(page);
await page.goto(`${BASE}/trial/new`);
const chairCard = page.getByTestId("role-chu_toa");
await chairCard.waitFor({ timeout: 20000 });
check("chair new: card enabled, 'Chủ tọa phiên tòa', contract description, pill Điều 45 BLTTHS, no 'Sắp có'",
  (await chairCard.getByRole("radio").isEnabled()) && (await chairCard.innerText()).includes("Chủ tọa phiên tòa")
  && (await chairCard.innerText()).includes("Điều hành phiên tòa, tự quyết định hình phạt và tuyên án")
  && (await chairCard.getByRole("button", { name: "Xem toàn văn Điều 45 BLTTHS" }).count()) === 1 && !(await chairCard.innerText()).includes("Sắp có"));
check("chair new: every other role card still enabled", (await Promise.all(["ksv", "luat_su", "bi_cao", "thu_ky", "nguoi_xem"].map((key) => page.getByTestId(`role-${key}`).getByRole("radio").isEnabled()))).every(Boolean));
let chairCreateBody = null;
const chairSession = newChair();
world.create = (route, body) => {
  chairCreateBody = body;
  return fulfillSse(route, sseEvent("session", { session_id: FAKE, title: "Vụ mẫu" }) + sseEvent("utterance", thuKyLine()) + sseEvent("state", chairState(chairSession)) + sseEvent("done", {}));
};
await chairCard.getByRole("radio").click();
await page.getByRole("radio", { name: /Tội trộm cắp tài sản/ }).click();
await shot(page, "chair-new-desktop");
world.role = "chu_toa";
world.utterances = [thuKyLine()];
world.state = chairState(chairSession);
world.turn = chairTurn(world, chairSession, chairBodies);
await page.getByRole("button", { name: "Tạo vụ án" }).click();
check("chair new: created with exactly the 5 fields, user_role chu_toa",
  (await page.waitForURL(`**/trial/${FAKE}`, { timeout: 15000 }).then(() => true, () => false))
  && Object.keys(chairCreateBody).sort().join() === "crime_key,has_related_party,user_role,victim_present,witness_count" && chairCreateBody.user_role === "chu_toa");
await page.getByTestId("trial-advance").waitFor({ timeout: 20000 });
check("chair step 1: the clerk (AI) reported; only 'Sang bước tiếp theo', no checklist, header 'Vai của bạn: Chủ tọa phiên tòa'",
  (await page.locator('[data-seq="1"]').innerText()).includes("Thư ký") && (await page.getByTestId("chair-checklist").count()) === 0
  && (await page.getByTestId("chair-composer").count()) === 0 && (await page.getByText("Vai của bạn: Chủ tọa phiên tòa").count()) === 1);
await advanceChair(page);
check("chair step 1: advance body exactly {expected_step 1, expected_version 20, advance, target_step 2}",
  JSON.stringify(chairBodies[0]) === JSON.stringify({ expected_step: 1, expected_version: 20, action: "advance", target_step: 2 }));

// Step 2: the checklist from state.presiding.
await chairAside(page).getByTestId("chair-checklist").waitFor({ timeout: 10000 });
const chairPanel = chairAside(page);
check("chair step 2: side panel opens on 'Điều hành', 7 items, 6 required, hoi_yeu_cau optional",
  (await chairPanel.getByRole("tab", { name: "Điều hành" }).getAttribute("aria-selected")) === "true"
  && (await chairPanel.locator('[data-testid^="chair-item-"]').count()) === 7 && (await chairPanel.locator('[data-testid^="chair-item-"][data-required]').count()) === 6
  && (await chairRow(chairPanel, "hoi_yeu_cau").innerText()).includes("Tùy chọn") && (await chairRow(chairPanel, "khai_mac").innerText()).includes("Bắt buộc"));
check("chair step 2: khai mạc first - only it has buttons; the others 'Chưa làm được lúc này'",
  (await chairRow(chairPanel, "khai_mac").getByTestId("chair-use-template").count()) === 1
  && (await chairRow(chairPanel, "kiem_tra_can_cuoc").getByTestId("chair-use-template").count()) === 0
  && (await chairRow(chairPanel, "kiem_tra_can_cuoc").innerText()).includes("Chưa làm được lúc này"));
const khaiMacTemplate = chairRow(chairPanel, "khai_mac").getByTestId("chair-template");
check("chair step 2: template previewed as 'Lời mẫu gợi ý' (long one clamped, 'Xem đủ'), basis pills, no review badge",
  (await khaiMacTemplate.innerText()).includes("Lời mẫu gợi ý") && (await khaiMacTemplate.getByRole("button", { name: "Xem đủ" }).count()) === 1
  && (await chairRow(chairPanel, "khai_mac").getByRole("button", { name: "Xem toàn văn Điều 301" }).count()) === 1
  && !(await page.locator("body").innerText()).includes("chờ nhóm luật duyệt"));
check("chair step 2: before khai mạc no remark target either; step button not ready",
  (await page.getByTestId("chair-composer").count()) === 1 && (await page.getByTestId("chair-target").count()) === 1
  && !(await page.getByTestId("chair-target").innerText()).includes("Phát biểu khác") && (await page.getByTestId("trial-advance").getAttribute("data-ready")) === null);
await shot(page, "chair-step2-desktop");

// The step button with required items left: nothing is sent, the missing items are listed and flash.
let sentBefore = chairBodies.length;
await page.getByTestId("trial-advance").click();
await page.waitForTimeout(200);
const missingLine = page.getByTestId("chair-missing");
check("chair missing (local): no request sent, list names the 6 required items",
  chairBodies.length === sentBefore && (await missingLine.innerText()).includes("Khai mạc, đọc quyết định") && (await missingLine.innerText()).includes("Người làm chứng cam đoan")
  && !(await missingLine.innerText()).includes("Hỏi yêu cầu triệu tập thêm"));
check("chair missing (local): required rows flash, the optional one does not",
  (await chairRow(chairPanel, "khai_mac").getAttribute("data-flash")) === "true" && (await chairRow(chairPanel, "cam_doan_nlc").getAttribute("data-flash")) === "true"
  && (await chairRow(chairPanel, "hoi_yeu_cau").getAttribute("data-flash")) === null);
await shot(page, "chair-step2-missing-flash");

// "Dùng lời mẫu": one click, item key only (empty text = template).
await page.getByTestId("chair-input").fill("");
await oneClick(page, "khai_mac");
check("chair one-click template: body exactly {expected_step 2, expected_version 21, item, khai_mac}, no text",
  JSON.stringify(lastBody()) === JSON.stringify({ expected_step: 2, expected_version: 21, action: "item", item: "khai_mac" }));
const khaiMacLine = page.locator('[data-testid="trial-user-utterance"]').last();
check("chair transcript: the student's line on their side, 'Bạn · Chủ tọa', procedure_item label shown",
  (await khaiMacLine.innerText()).includes("Bạn · Chủ tọa") && (await khaiMacLine.getByTestId("trial-procedure-item").innerText()).includes("Khai mạc"));
check("chair: khai mạc marked done, the missing list cleared, remark now offered",
  (await chairRow(chairPanel, "khai_mac").getAttribute("data-done")) === "true" && (await missingLine.count()) === 0
  && (await page.getByTestId("chair-target").innerText()).includes("Phát biểu khác"));

// A draft in the box survives a one-click template; the identity answer comes back.
await page.getByTestId("chair-target").selectOption("remark");
await page.getByTestId("chair-input").fill("Bản nháp phát biểu đang gõ");
await oneClick(page, "kiem_tra_can_cuoc");
check("chair: a typed draft is kept across a one-click template; the defendant's identity answer appears",
  (await page.getByTestId("chair-input").inputValue()) === "Bản nháp phát biểu đang gõ" && lastBody().item === "kiem_tra_can_cuoc"
  && (await page.locator('[data-testid="trial-ai-utterance"]').last().innerText()).includes("Bị cáo"));

// Remark without and with an addressee.
await page.getByTestId("chair-send").click();
await settle(page);
check("chair remark: body {remark, text} without addressee by default; box cleared",
  JSON.stringify(lastBody()) === JSON.stringify({ expected_step: 2, expected_version: 23, action: "remark", text: "Bản nháp phát biểu đang gõ" })
  && (await page.getByTestId("chair-input").inputValue()) === "");
await page.getByTestId("chair-target").selectOption("remark");
await page.getByTestId("chair-remark-addressee").selectOption("KSV");
await page.getByTestId("chair-input").fill("Đề nghị Kiểm sát viên cho biết ý kiến.");
await page.getByTestId("chair-send").click();
await settle(page);
check("chair remark: addressee sent, the answer appears, counter 'Còn 3 lần phát biểu khác'",
  lastBody().action === "remark" && lastBody().addressee === "KSV" && (await page.locator('[data-testid="trial-ai-utterance"]').last().innerText()).includes("Kiểm sát viên")
  && (await chairPanel.getByTestId("chair-counters").innerText()).includes("Còn 3 lần phát biểu khác"));
check("chair remark: the 1.500 cap from presiding.limits", (await (async () => {
  await page.getByTestId("chair-target").selectOption("remark");
  await page.getByTestId("chair-input").fill("a".repeat(1501));
  const ok = (await page.getByTestId("chair-send").isDisabled()) && (await page.getByTestId("chair-validation").innerText()).includes("1.500")
    && (await page.getByTestId("chair-counter").innerText()).includes("1.501/1.500");
  await page.getByTestId("chair-input").fill("");
  return ok;
})()));

// "Tự soạn": the item into the composer with its template, edited, sent with text.
await chairRow(chairPanel, "kiem_tra_co_mat").getByTestId("chair-compose").click();
await page.waitForTimeout(200);
const coMatTemplate = await page.getByTestId("chair-input").inputValue();
check("chair 'Tự soạn': the target is the item, its template is in the box, focus on the box",
  (await page.getByTestId("chair-target").inputValue()) === "item:kiem_tra_co_mat" && coMatTemplate.includes(CHAIR_MARK)
  && (await page.evaluate(() => document.activeElement?.getAttribute("data-testid"))) === "chair-input");
await page.getByTestId("chair-input").fill(`${coMatTemplate} Bổ sung của tôi.`);
await page.getByTestId("chair-send").click();
await settle(page);
check("chair 'Tự soạn': body {item, kiem_tra_co_mat, text} with the edited text; label 'Thực hiện' path",
  lastBody().action === "item" && lastBody().item === "kiem_tra_co_mat" && lastBody().text === `${coMatTemplate} Bổ sung của tôi.`);
for (const key of ["giai_thich_quyen", "hoi_thay_doi", "cam_doan_nlc"]) await oneClick(page, key);
check("chair step 2: all required done -> the step button is ready, 'Đủ mục bắt buộc'",
  (await page.getByTestId("trial-advance").getAttribute("data-ready")) === "true" && (await page.getByTestId("chair-composer").innerText()).includes("Đủ mục bắt buộc"));
await advanceChair(page);
check("chair advance: body {advance, target_step 3}", lastBody().action === "advance" && lastBody().target_step === 3);

// Step 3: invite, the KSV reads.
await oneClick(page, "moi_cong_bo_cao_trang");
check("chair invite: body {invite, moi_cong_bo_cao_trang}; KSV answers", JSON.stringify(Object.keys(lastBody())) === JSON.stringify(["expected_step", "expected_version", "action", "item"])
  && lastBody().action === "invite" && (await page.locator('[data-testid="trial-ai-utterance"]').last().innerText()).includes("Kiểm sát viên"));
await advanceChair(page);

// Step 4: questions.
check("chair step 4: composer defaults to 'Đặt câu hỏi', addressees from ask:, counter 'Còn 10 câu hỏi'",
  (await page.getByTestId("chair-target").inputValue()) === "ask" && (await page.getByTestId("chair-ask-addressee").locator("option").count()) === 3
  && (await chairPanel.getByTestId("chair-counters").innerText()).includes("Còn 10 câu hỏi"));
check("chair step 4: 'Hỏi bị cáo' one-click template; 'Hỏi người khác' needs a chosen addressee (no one-click)",
  (await chairRow(chairPanel, "hoi_bi_cao").getByTestId("chair-use-template").count()) === 1 && (await chairRow(chairPanel, "hoi_nguoi_khac").getByTestId("chair-use-template").count()) === 0
  && (await chairRow(chairPanel, "hoi_nguoi_khac").getByTestId("chair-compose").innerText()).includes("Soạn câu hỏi"));
await page.getByTestId("chair-input").fill("a".repeat(1501));
check("chair ask: over 1.500 blocks 'Hỏi'", (await page.getByTestId("chair-send").isDisabled()) && (await page.getByTestId("chair-validation").innerText()).includes("1.500"));
await page.getByTestId("chair-ask-addressee").selectOption("NLC_1");
await page.getByTestId("chair-input").fill("Người làm chứng thấy sự việc lúc mấy giờ?");
await page.getByTestId("chair-send").click();
await settle(page);
check("chair ask: body exactly {ask, addressee NLC_1, text}; 'Còn 9 câu hỏi'; line shows who was asked",
  JSON.stringify(Object.keys(lastBody())) === JSON.stringify(["expected_step", "expected_version", "action", "addressee", "text"]) && lastBody().addressee === "NLC_1"
  && (await chairPanel.getByTestId("chair-counters").innerText()).includes("Còn 9 câu hỏi")
  && (await page.locator('[data-testid="trial-user-utterance"]').last().innerText()).includes("→ hỏi Người làm chứng"));
check("chair step 4: hỏi bị cáo still missing -> step button not ready", (await page.getByTestId("trial-advance").getAttribute("data-ready")) === null);
await oneClick(page, "hoi_bi_cao");
check("chair ask one-click: {ask, BI_CAO, template text}", lastBody().action === "ask" && lastBody().addressee === "BI_CAO" && lastBody().text.includes(CHAIR_MARK));
await shot(page, "chair-step4-desktop");
await advanceChair(page);

// Step 5: closing only after both invitations (order from the server).
check("chair step 5: 'Kết thúc xét hỏi' not available before the invitations", (await chairRow(chairPanel, "ket_thuc_xet_hoi").getByTestId("chair-use-template").count()) === 0);
for (const key of ["moi_ksv_hoi", "moi_ls_hoi", "ket_thuc_xet_hoi"]) await oneClick(page, key);
await advanceChair(page);
await oneClick(page, "moi_luan_toi");
await advanceChair(page);
for (const key of ["moi_bao_chua", "moi_bi_hai_trinh_bay"]) await oneClick(page, key);
await advanceChair(page);

// Step 8: round 2 note, Điều 323 once.
check("chair step 8: the 2-round note (Q12) next to 'vòng 2'", (await chairRow(chairPanel, "vong_2").getByTestId("chair-item-note").innerText()).trim() === DEBATE_NOTE);
check("chair step 8: no return before the first round", (await chairRow(chairPanel, "tro_lai_xet_hoi").getByTestId("chair-return").count()) === 0
  && (await chairRow(chairPanel, "tro_lai_xet_hoi").innerText()).includes("Một lần mỗi phiên"));
await oneClick(page, "moi_doi_dap");
check("chair debate: one invitation, KSV then luật sư answer", lastBody().item === "moi_doi_dap"
  && (await page.locator('[data-testid="trial-ai-utterance"]').nth(-2).innerText()).includes("Kiểm sát viên") && (await page.locator('[data-testid="trial-ai-utterance"]').last().innerText()).includes("Luật sư"));
check("chair Điều 323: after a round the return is offered, 'còn lượt' and its consequence shown",
  (await chairRow(chairPanel, "tro_lai_xet_hoi").getByTestId("chair-return").count()) === 1 && (await chairRow(chairPanel, "tro_lai_xet_hoi").innerText()).includes("còn lượt")
  && (await chairRow(chairPanel, "tro_lai_xet_hoi").innerText()).includes("về lại bước 8"));
await shot(page, "chair-step8-desktop");
dialogAnswer = false;
sentBefore = chairBodies.length;
await chairRow(chairPanel, "tro_lai_xet_hoi").getByTestId("chair-return").click();
await page.waitForTimeout(300);
check("chair Điều 323: cancelling the confirm sends nothing", chairBodies.length === sentBefore);
dialogAnswer = true;
await chairRow(chairPanel, "tro_lai_xet_hoi").getByTestId("chair-return").click();
await settle(page);
check("chair Điều 323: body exactly {return_to_questioning}", JSON.stringify(Object.keys(lastBody())) === JSON.stringify(["expected_step", "expected_version", "action"]) && lastBody().action === "return_to_questioning");
check("chair in return: step bar 'Trở lại xét hỏi', banner, short checklist (hỏi lại, mời, kết thúc)",
  (await page.getByRole("navigation", { name: "Tiến trình phiên tòa" }).innerText()).includes("Trở lại xét hỏi") && (await chairPanel.getByTestId("chair-in-return").count()) === 1
  && (await chairPanel.locator('[data-testid^="chair-item-"]').count()) === 4 && (await chairPanel.getByTestId("chair-counters").innerText()).includes("Còn 3 câu hỏi"));
await shot(page, "chair-return-desktop");
await oneClick(page, "ket_thuc_xet_hoi");
check("chair in return: step button reads 'Về lại bước 8'", (await page.getByTestId("trial-advance").innerText()).includes("Về lại bước 8"));
await advanceChair(page);
check("chair back at 8: target_step 8 sent; return used shown; no return item; round 1 required again",
  lastBody().target_step === 8 && (await chairPanel.getByTestId("chair-return-used").count()) === 1 && (await chairRow(chairPanel, "tro_lai_xet_hoi").count()) === 0
  && (await chairRow(chairPanel, "moi_doi_dap").getAttribute("data-done")) === null);
await oneClick(page, "moi_doi_dap");
await oneClick(page, "ket_thuc_tranh_luan");
await advanceChair(page);

// Step 9: after the last word nobody may question the defendant.
await oneClick(page, "moi_loi_sau_cung");
await page.getByTestId("chair-target").selectOption("remark");
const remarkOptions = await page.getByTestId("chair-remark-addressee").locator("option").allInnerTexts();
check("chair step 9: after the last word, remark addressees exclude the defendant; hint cites Điều 324",
  remarkOptions.length === 5 && !remarkOptions.some((text) => text.startsWith("Bị cáo")) && (await page.getByTestId("trial-step-hint").innerText()).includes("Điều 324"));
await advanceChair(page);
check("chair step 10: 'Sắp có' placeholder, no error, no composer", (await page.getByTestId("chair-coming-soon").count()) === 1
  && (await page.getByTestId("trial-error").count()) === 0 && (await page.getByTestId("chair-composer").count()) === 0);
await shot(page, "chair-step10-soon");
await context.close();

// 409 trial_procedure_incomplete from the server (a stale state offered the step button).
resetWorld();
chairBodies.length = 0;
({ context, page } = await open());
answerDialogs(page);
{
  const c = newChair({ step: 2, done: ["khai_mac"] });
  world.role = "chu_toa";
  world.utterances = [thuKyLine()];
  world.turn = chairTurn(world, c, chairBodies);
  const stale = chairState(c);
  await openHearing(page, { ...stale, allowed_actions: [...stale.allowed_actions, "advance:3"] }, "chu_toa");
}
await page.getByTestId("trial-advance").click();
await settle(page);
check("chair 409 procedure_incomplete: advance sent, missing items listed from missing_items, rows flash, no error box",
  lastBody()?.action === "advance" && (await page.getByTestId("chair-missing").innerText()).includes("Kiểm tra căn cước bị cáo")
  && (await chairRow(chairAside(page), "kiem_tra_can_cuoc").getAttribute("data-flash")) === "true" && (await page.getByTestId("trial-error").count()) === 0
  && (await page.getByTestId("trial-advance").getAttribute("data-ready")) === null);
await context.close();

// Version mismatch: re-sync and keep the question being typed.
resetWorld();
chairBodies.length = 0;
({ context, page } = await open());
{
  const c = await openChair(page, { step: 4, version: 30 });
  c.version = 31; // another tab moved the session on
  world.state = chairState(c);
}
let chairGets = world.requests.filter((r) => r.method === "GET" && r.path.endsWith(FAKE)).length;
await page.getByTestId("chair-input").fill("Câu hỏi đang gõ dở của tôi");
await page.getByTestId("chair-send").click();
await settle(page);
check("chair 409 version mismatch: soft notice, GET re-read, the typed question kept",
  (await page.getByTestId("trial-soft-notice").count()) === 1 && world.requests.filter((r) => r.method === "GET" && r.path.endsWith(FAKE)).length > chairGets
  && (await page.getByTestId("chair-input").inputValue()) === "Câu hỏi đang gõ dở của tôi");
await page.getByTestId("chair-send").click();
await settle(page);
check("chair after re-sync: the same question goes through with the new version", lastBody().expected_version === 31 && (await page.getByTestId("chair-input").inputValue()) === "");

// Every 409 of contract 6 for this role, and the HTTP errors: a Vietnamese line, the screen stays.
const CHAIR_409 = {
  trial_item_not_available: "chưa làm được lúc này", trial_item_done: "đã làm rồi", trial_return_not_allowed: "Chưa trở lại xét hỏi được",
  trial_return_used: "đã trở lại xét hỏi một lần", trial_decision_missing: "lưu bản nháp quyết định", trial_decision_invalid: "còn lỗi cần sửa",
  trial_decision_locked: "đã chốt", trial_pronouncement_missing: "Chưa có lời tuyên", trial_not_presiding: "không phải vai Chủ tọa",
  trial_turn_limit: "vừa thay đổi trạng thái", trial_missing_addressee: "chọn người được hỏi", trial_text_too_long: "dài quá", trial_text_too_short: "ngắn hơn",
  trial_empty_text: "chưa nhập", trial_action_not_allowed: "vừa thay đổi trạng thái", trial_not_active: "đã kết thúc hoặc đã bị bỏ", trial_guard_exhausted: null
};
const errorLine = async (page) => ((await page.getByTestId("trial-soft-notice").count()) ? page.getByTestId("trial-soft-notice") : page.getByTestId("trial-error")).innerText().catch(() => "");
let codesOk = true;
const failedCodes = [];
for (const [code, expected] of Object.entries(CHAIR_409)) {
  resetWorld();
  ({ context, page } = await open());
  const c = await openChair(page, { step: 4, version: 40 });
  world.turn = (route) => fulfillError(route, 409, code, { state: chairState(c), fields: code.startsWith("trial_item") ? { item: "moi_hoi_tham_hoi" } : undefined });
  await oneClick(page, "moi_hoi_tham_hoi");
  const text = await errorLine(page);
  const ok = (expected === null ? (await page.getByTestId("trial-error").count()) === 0 : text.includes(expected)) && (await page.getByTestId("trial-composer-dock").isVisible());
  if (!ok) failedCodes.push(code);
  codesOk = codesOk && ok;
  await context.close();
}
check(`chair: every 409 code gives its Vietnamese line, the screen stays (${failedCodes.join(", ") || "all"})`, codesOk);
const HTTP_ERRORS = [[401, "http_error", "Phiên đăng nhập đã hết hạn"], [404, "http_error", "Không tìm thấy phiên tòa"], [422, "validation_error", "không hợp lệ"],
  [429, "rate_limit_exceeded", "thao tác hơi nhanh"], [503, "data_unavailable", "tạm gián đoạn"], [0, "network", "Mất kết nối"]];
let httpOk = true;
const failedHttp = [];
for (const [status, code, expected] of HTTP_ERRORS) {
  resetWorld();
  ({ context, page } = await open());
  await openChair(page, { step: 4, version: 40 });
  world.turn = (route) => (status === 0 ? route.abort("failed") : fulfillError(route, status, code));
  await oneClick(page, "moi_hoi_tham_hoi");
  const ok = (await page.getByTestId("trial-error").innerText().catch(() => "")).includes(expected) && (await page.getByTestId("trial-composer-dock").isVisible());
  if (!ok) failedHttp.push(status);
  httpOk = httpOk && ok;
  await context.close();
}
check(`chair: 401/404/422/429/503/network each show a Vietnamese error, no blank page (${failedHttp.join(", ") || "all"})`, httpOk);

// The guard pause in a presiding session is the system's, never the presiding judge's.
resetWorld();
({ context, page } = await open());
{
  const c = newChair({ step: 4, version: 40 });
  const pause = utt(5, 4, "HE_THONG", "Hội đồng xét xử tạm nghỉ để kiểm tra lại nội dung.", { kind: "notice", speaker_role: "Hệ thống", speaker_name: "" });
  world.role = "chu_toa";
  world.utterances = [thuKyLine(), pause];
  await openHearing(page, chairState(c, { awaiting: "ai", allowed_actions: ["continue"] }), "chu_toa");
}
check("chair guard pause: notice speaker 'Hệ thống', 'Tiếp tục' offered, no chair composer",
  (await page.getByTestId("trial-notice").innerText()).trim().startsWith("Hệ thống:") && (await page.getByTestId("trial-paused").count()) === 1
  && (await page.getByTestId("chair-composer").count()) === 0);
await context.close();

// Minimum operations, steps 2-9, one click each (templates) and the step button.
resetWorld();
chairBodies.length = 0;
({ context, page } = await open());
await openChair(page, { step: 2, version: 21 });
let chairClicks = 0;
for (let guard = 0; guard < 40 && (await page.getByTestId("chair-coming-soon").count()) === 0; guard++) {
  if ((await page.getByTestId("trial-advance").getAttribute("data-ready")) === "true") {
    await advanceChair(page);
  } else {
    const next = chairAside(page).locator('[data-testid^="chair-item-"][data-required]:not([data-done])').getByTestId("chair-use-template").first();
    await next.click();
    await settle(page);
  }
  chairClicks++;
}
check(`chair minimum: steps 2-9 in ${chairClicks} clicks (backend minimum 25 for this case shape), reaches step 10`,
  chairClicks === 25 && (await page.getByTestId("chair-coming-soon").count()) === 1);
await context.close();

// Phone: the checklist is a drawer, the composer stays visible.
resetWorld();
chairBodies.length = 0;
({ context, page } = await open({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }));
answerDialogs(page);
await openChair(page, { step: 4, version: 40 }, makeUtterances(12));
info = await scrollInfo(page);
check(`chair 390px step 4: no page overflow, dock ${info.dockH}px ≤ 60% of the screen, latest line visible, 'Điều hành' button`,
  (await noPageOverflow(page)) && info.dockH <= 506 && info.latestVisible && (await page.getByTestId("chair-open-checklist").isVisible()) && (await page.getByTestId("chair-input").isVisible()));
await shot(page, "chair-step4-mobile");
await page.getByTestId("chair-open-checklist").click();
const chairDrawer = page.getByRole("dialog", { name: "Điều hành" });
await chairDrawer.getByTestId("chair-checklist").waitFor({ timeout: 5000 });
check("chair 390px: drawer holds the checklist, no overflow", (await chairDrawer.locator('[data-testid^="chair-item-"]').count()) === 3 && (await noPageOverflow(page)));
await shot(page, "chair-checklist-drawer-mobile");
await oneClick(page, "moi_hoi_tham_hoi", chairDrawer);
check("chair 390px: one-click from the drawer sends and closes the drawer", lastBody().item === "moi_hoi_tham_hoi" && (await chairDrawer.count()) === 0);
await page.getByTestId("trial-advance").click();
await page.waitForTimeout(400);
check("chair 390px: step button with items missing opens the drawer with the rows flashing",
  (await chairDrawer.count()) === 1 && (await chairRow(chairDrawer, "hoi_bi_cao").getAttribute("data-flash")) === "true");
await shot(page, "chair-missing-mobile");
await page.getByRole("button", { name: "Đóng điều hành", exact: true }).click();
await page.getByTestId("chair-input").focus();
check("chair 390px: the drawer closes, the box is reachable", (await chairDrawer.count()) === 0 && (await page.evaluate(() => document.activeElement?.getAttribute("data-testid"))) === "chair-input");
await context.close();
for (const [width, height] of [[1280, 600], [1440, 900], [1920, 1080]]) {
  resetWorld();
  ({ context, page } = await open({ viewport: { width, height } }));
  await openChair(page, { step: 4, version: 40 }, makeUtterances(12));
  info = await scrollInfo(page);
  check(`chair ${width}x${height}: no page overflow, latest line above the dock, checklist in the side panel, no drawer button`,
    (await noPageOverflow(page)) && info.latestVisible && (await chairAside(page).getByTestId("chair-checklist").isVisible()) && !(await page.getByTestId("chair-open-checklist").isVisible()));
  if (width !== 1440) await shot(page, `chair-step4-${width}x${height}`);
  await context.close();
}

// Other roles: no presiding UI anywhere.
for (const role of ["ksv", "bi_cao", "nguoi_xem"]) {
  resetWorld();
  world.role = role;
  ({ context, page } = await open());
  await openHearing(page, role === "nguoi_xem" ? baseState({ current_step: 5, allowed_actions: ["advance:6"], procedure_note: procedureNote(5) }) : baseState(), role);
  check(`${role}: no 'Điều hành' panel or presiding composer`, (await page.getByTestId("chair-checklist").count()) === 0 && (await page.getByTestId("chair-composer").count()) === 0
    && (await page.getByRole("tab", { name: "Điều hành" }).count()) === 0);
  await context.close();
}

const badConsole = consoleMessages.filter((m) => m.includes(TRANSCRIPT_MARKER) || m.includes("Chú giải mẫu") || m.includes(CLERK_MARK) || m.includes(DEF_MARK) || m.includes(CHAIR_MARK) || m.includes(IDENTITY_PREFILL.slice(0, 30)) || m.includes(CLERK_PREFILL.slice(0, 40)) || /Uncaught|TypeError/.test(m));
if (process.env.E2E_DEBUG) badConsole.forEach((m) => console.log(`  console: ${m.slice(0, 200)}`));
// Regression: nothing may stretch the document past the record (absolutely positioned sr-only labels
// used to resolve against <body>, leaving hundreds of px of empty page under the h-screen frame).
for (const [width, height] of [[1440, 900], [1920, 1080]]) {
  resetWorld();
  ({ context, page } = await open({ viewport: { width, height } }));
  await page.goto(`${BASE}/trial/${FAKE}/record`);
  await page.getByTestId("trial-record").waitFor({ timeout: 20000 });
  await page.waitForTimeout(500);
  const gap = await page.evaluate(() => {
    const card = document.querySelector('[data-testid="trial-record"]');
    let scroller = card.parentElement;
    while (scroller && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
    scroller.scrollTop = scroller.scrollHeight;
    window.scrollTo(0, document.documentElement.scrollHeight);
    const cardBottom = card.getBoundingClientRect().bottom + window.scrollY;
    return { docOverCard: document.documentElement.scrollHeight - cardBottom, docOverViewport: document.documentElement.scrollHeight - window.innerHeight };
  });
  check(`record ${width}x${height}: document ends ≤ 120px below the record (${Math.round(gap.docOverCard)}px), no page scroll (${gap.docOverViewport}px)`,
    gap.docOverCard <= 120 && gap.docOverViewport <= 0);
  await context.close();
}

check("console: no transcript text, no page errors", badConsole.length === 0);
await browser.close();
console.log(failureCount() === 0 ? "ALL PASS" : `${failureCount()} FAILED`);
