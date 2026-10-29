// Shared helpers for the mocked browser suite (see README.md). Nothing here talks to a real backend
// or a real Supabase project: the app is built against two fake origins and every request to them is
// answered by the routes below. Never logs trial text, credentials or tokens.
import { createRequire } from "node:module";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { config, FAKE, caseFile, participants, steps, makeUtterances, recordDoc, recordText, COURT_NAME, DISCLAIMER } from "./fixtures.mjs";

export const PORT = Number(process.env.E2E_PORT ?? 3011);
export const BASE = `http://localhost:${PORT}`;
// Must match the values build.sh bakes into the build.
export const API_ORIGIN = "http://api.e2e.test";
export const SUPABASE_ORIGIN = "http://supabase.e2e.test";

// Playwright is not a dependency of the project. Use $PLAYWRIGHT_MODULE, a resolvable "playwright",
// or the copy npx keeps in its cache (`npx -y playwright@1.64.0 --version` puts one there).
function loadPlaywright() {
  const require = createRequire(import.meta.url);
  const candidates = [process.env.PLAYWRIGHT_MODULE, "playwright"].filter(Boolean);
  const npxRoot = join(homedir(), ".npm", "_npx");
  if (existsSync(npxRoot)) {
    for (const dir of readdirSync(npxRoot)) {
      const path = join(npxRoot, dir, "node_modules", "playwright");
      if (existsSync(path)) candidates.push(path);
    }
  }
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // try the next one
    }
  }
  throw new Error("Playwright not found. Set PLAYWRIGHT_MODULE or run `npx -y playwright@1.64.0 install chromium` once.");
}
export const { chromium } = loadPlaywright();

// --- Results -------------------------------------------------------------------------------------

let failures = 0;
export function check(name, ok) {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}`);
  if (!ok) {
    failures++;
    process.exitCode = 1;
  }
}
export const failureCount = () => failures;

// --- Fake Supabase session ---------------------------------------------------------------------------
// supabase-js reads its session from localStorage key sb-<first host label>-auth-token. A far-future
// expiry means it never tries to refresh. The token is an unsigned placeholder; only the mocked
// backend ever sees it.
const b64url = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
const FAR_FUTURE = 4102444800; // 2100-01-01
// Stable fake user id per email, so the app can tell users apart.
const userIdFor = (email) => `00000000-0000-4000-8000-${Buffer.from(email).toString("hex").padEnd(12, "0").slice(0, 12)}`;
export const DEFAULT_EMAIL = "sinhvien@e2e.test";

export function fakeSession(email = DEFAULT_EMAIL) {
  const user = { id: userIdFor(email), email, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" };
  return {
    access_token: `${b64url({ alg: "none", typ: "JWT" })}.${b64url({ sub: user.id, email, exp: FAR_FUTURE, role: "authenticated" })}.e2e`,
    refresh_token: `e2e-refresh-${user.id}`,
    token_type: "bearer",
    expires_in: 3600,
    expires_at: FAR_FUTURE,
    user
  };
}

// The email inside a fake bearer token, or null without one.
function emailFromAuthorization(header) {
  const token = header?.startsWith("Bearer ") ? header.slice("Bearer ".length) : null;
  try {
    return token ? JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString()).email ?? null : null;
  } catch {
    return null;
  }
}
const STORAGE_KEY = `sb-${new URL(SUPABASE_ORIGIN).hostname.split(".")[0]}-auth-token`;

// --- Mocked backend ------------------------------------------------------------------------------------

export const baseState = (overrides = {}) => ({
  session_id: FAKE, current_step: 6, step_title: "Kiểm sát viên luận tội", status: "active", awaiting: "user",
  allowed_actions: ["speak"], version: 10, text_limits: null, procedure_note: null, ...overrides
});

// Mutable world the routes answer from. Tests set what they need before navigating.
export const world = {
  // "on" | "off" | "head405" (a backend without the HEAD route)
  flag: "on",
  // TRIAL_ALLOWED_EMAILS: null = everyone signed in; a list = only those emails, everyone else
  // (signed out included) gets the flag-off 404.
  allowedEmails: null,
  // async (route) => boolean, consulted first for HEAD /api/trials; true = it answered (e.g. aborted).
  head: null,
  // Milliseconds every /api/trials* answer waits (a slow backend while the probe is pending).
  delay: 0,
  config: config(),
  role: "ksv",
  state: baseState(),
  utterances: makeUtterances(),
  // (route, body) => Promise; null answers 404.
  turn: null,
  create: null,
  requests: []
};

export function resetWorld() {
  Object.assign(world, { flag: "on", allowedEmails: null, head: null, delay: 0, config: config(), role: "ksv", state: baseState(), utterances: makeUtterances(), turn: null, create: null, requests: [] });
}

export const detail = () => ({
  state: world.state, title: caseFile.title, crime_key: "blhs_173", user_role: world.role, disclaimer: DISCLAIMER,
  court: { name: COURT_NAME, hearing_date: "28/10/2026", venue: "phường A, tỉnh X" },
  participants, case_file: caseFile, steps, utterances: world.utterances
});

const cors = {
  "access-control-allow-origin": BASE,
  "access-control-allow-headers": "authorization, content-type",
  "access-control-allow-methods": "GET, POST, HEAD, DELETE, OPTIONS"
};
const json = (status, body) => ({ status, headers: { ...cors, "content-type": "application/json" }, body: JSON.stringify(body) });
const notFound = () => json(404, { detail: "Not Found" });

export const sseEvent = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
export const fulfillSse = (route, body) => route.fulfill({ status: 200, headers: { ...cors, "content-type": "text/event-stream" }, body });
export const fulfillError = (route, status, code, extra = {}) =>
  route.fulfill(json(status, { error: { code, message: extra.message ?? "m" }, ...(extra.state ? { state: extra.state } : {}) }));

async function handleApi(route) {
  const request = route.request();
  const method = request.method();
  const path = new URL(request.url()).pathname;
  if (method === "OPTIONS") {
    return route.fulfill({ status: 204, headers: cors });
  }
  const email = emailFromAuthorization(request.headers().authorization);
  world.requests.push({ method, path, email });
  if (!path.startsWith("/api/trials")) {
    // Other features run on their built-in mock data; anything that still calls out gets a benign answer.
    const emptyLists = { "/api/chat/conversations": { conversations: [] }, "/api/notes": { notes: [] } };
    return route.fulfill(json(200, emptyLists[path] ?? {}));
  }
  if (world.delay > 0) {
    await new Promise((resolve) => setTimeout(resolve, world.delay));
  }
  if (world.flag === "off" || (world.allowedEmails !== null && !world.allowedEmails.includes(email))) {
    return route.fulfill(notFound());
  }
  if (email === null) {
    return route.fulfill(json(401, { error: { code: "http_error", message: "Not authenticated" } }));
  }
  if (path === "/api/trials") {
    if (method === "HEAD" && world.head) {
      if (await world.head(route)) return;
    }
    if (method === "HEAD") {
      return route.fulfill(world.flag === "head405" ? { status: 405, headers: cors } : { status: 204, headers: cors });
    }
    if (method === "GET") {
      return route.fulfill(json(200, { sessions: [], config: world.config }));
    }
    if (method === "POST" && world.create) {
      return world.create(route, JSON.parse(request.postData() ?? "{}"));
    }
    return route.fulfill(notFound());
  }
  if (path.startsWith(`/api/trials/${FAKE}`)) {
    if (path.endsWith("/record")) {
      const observer = world.role === "nguoi_xem";
      return route.fulfill(json(200, { session_id: FAKE, text: recordText({ observer }), record: recordDoc({ observer }) }));
    }
    if (path.endsWith("/turn") && world.turn) {
      return world.turn(route, JSON.parse(request.postData() ?? "{}"));
    }
    if (method === "GET") {
      return route.fulfill(json(200, detail()));
    }
  }
  return route.fulfill(json(404, { error: { code: "http_error", message: "Trial not found" } }));
}

// One browser context with the fake session, the mocked origins and console capture.
// Supabase Auth endpoints the app calls: password sign-in (any password; the session is the fake one
// for that email), sign-out, and anything else answered with an empty object.
async function handleSupabase(route) {
  const request = route.request();
  const url = new URL(request.url());
  const headers = { "access-control-allow-origin": BASE, "access-control-allow-headers": "*", "access-control-allow-methods": "*" };
  if (request.method() === "OPTIONS") {
    return route.fulfill({ status: 204, headers });
  }
  if (url.pathname === "/auth/v1/token" && url.searchParams.get("grant_type") === "password") {
    const { email } = JSON.parse(request.postData() ?? "{}");
    return route.fulfill({ status: 200, headers: { ...headers, "content-type": "application/json" }, body: JSON.stringify(fakeSession(email)) });
  }
  if (url.pathname === "/auth/v1/logout") {
    return route.fulfill({ status: 204, headers });
  }
  return route.fulfill({ status: 200, headers: { ...headers, "content-type": "application/json" }, body: "{}" });
}

// signedInAs: the email whose session is in storage when the app loads, or null to start signed out.
export async function newPage(browser, { viewport = { width: 1440, height: 900 }, consoleBucket, signedInAs = DEFAULT_EMAIL, ...options } = {}) {
  const context = await browser.newContext({ viewport, serviceWorkers: "block", ...options });
  if (signedInAs !== null) {
    await context.addInitScript(({ key, session }) => {
      try {
        // Only before the app's first load: a later sign-out must stay signed out.
        if (!window.sessionStorage.getItem("e2e-seeded")) {
          window.localStorage.setItem(key, JSON.stringify(session));
          window.sessionStorage.setItem("e2e-seeded", "1");
        }
      } catch {
        // storage blocked: the app redirects to /login and the check fails visibly
      }
    }, { key: STORAGE_KEY, session: fakeSession(signedInAs) });
  }
  await context.route(`${API_ORIGIN}/**`, handleApi);
  await context.route(`${SUPABASE_ORIGIN}/**`, handleSupabase);
  const page = await context.newPage();
  if (consoleBucket) {
    page.on("console", (message) => consoleBucket.push(message.text()));
    page.on("pageerror", (error) => consoleBucket.push(`${String(error)} @ ${page.url()} ${error.stack?.split("\n").slice(0, 3).join(" | ") ?? ""}`));
  }
  return { context, page };
}

// Replaces fetch for POST .../turn with a stream played from window.__e2eTurn (a list of
// { delay, event, data } steps, then the stream closes). Lets a check observe the screen while a
// long AI turn is still running, which route.fulfill (whole body at once) cannot. The request body
// is kept in window.__e2eTurnBodies.
export async function installStreamingTurn(context) {
  await context.addInitScript(() => {
    const original = window.fetch;
    window.__e2eTurnBodies = [];
    window.fetch = async (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      if (!url.endsWith("/turn") || !Array.isArray(window.__e2eTurn)) {
        return original(input, init);
      }
      window.__e2eTurnBodies.push(JSON.parse(init?.body ?? "{}"));
      const script = window.__e2eTurn;
      const encoder = new TextEncoder();
      const body = new ReadableStream({
        async start(controller) {
          for (const step of script) {
            await new Promise((resolve) => setTimeout(resolve, step.delay ?? 0));
            if (step.event) {
              controller.enqueue(encoder.encode(`event: ${step.event}\ndata: ${JSON.stringify(step.data ?? {})}\n\n`));
            }
          }
          controller.close();
        }
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    };
  });
}

export async function openHearing(page, state, role = world.role) {
  world.state = state;
  world.role = role;
  await page.goto(`${BASE}/trial/${FAKE}`);
  await page.getByTestId("trial-composer-dock").waitFor({ timeout: 20000 });
  await page.waitForTimeout(600);
}

export const scrollInfo = (page) => page.evaluate(() => {
  const dock = document.querySelector('[data-testid="trial-composer-dock"]');
  let container = dock.parentElement;
  while (container && !/(auto|scroll)/.test(getComputedStyle(container).overflowY)) container = container.parentElement;
  const items = document.querySelectorAll("[data-seq]");
  const last = items[items.length - 1].getBoundingClientRect();
  const dockBox = dock.getBoundingClientRect();
  return {
    top: container.scrollTop,
    distance: container.scrollHeight - container.scrollTop - container.clientHeight,
    latestVisible: last.bottom <= dockBox.top + 1 && last.bottom > 120,
    dockH: Math.round(dockBox.height)
  };
});

export const noPageOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

// Signs in through the real login form (fake Supabase answers) and waits for the dashboard.
export async function signIn(page, email) {
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "e2e-placeholder-password");
  await page.click('button[type="submit"]');
  await page.waitForURL("**/dashboard", { timeout: 20000 });
}

// Signs out with the top bar button (client-side, no reload) and waits for the login page.
export async function signOut(page) {
  await page.locator('button[title="Đăng xuất"]').click();
  await page.waitForURL("**/login", { timeout: 20000 });
}
