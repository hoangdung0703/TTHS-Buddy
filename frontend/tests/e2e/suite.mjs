// Mocked browser suite for "Phiên tòa giả định" (0 Gemini calls, no real backend or account).
// Run tests/e2e/build.sh first, then `node tests/e2e/suite.mjs`. Prints PASS/FAIL lines only and
// exits non-zero when anything fails. Set E2E_SHOTS=<dir> to also save screenshots there.
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { FAKE, FULL, SHORT, OBSERVER_PREAMBLE, TRANSCRIPT_MARKER, config, makeUtterances, procedureNote, recordText, utt } from "./fixtures.mjs";
import {
  BASE, baseState, check, chromium, failureCount, fulfillError, fulfillSse, installStreamingTurn, newPage, noPageOverflow, signIn, signOut,
  openHearing, resetWorld, scrollInfo, sseEvent, world
} from "./lib.mjs";

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

const badConsole = consoleMessages.filter((m) => m.includes(TRANSCRIPT_MARKER) || m.includes("Chú giải mẫu") || /Uncaught|TypeError/.test(m));
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
