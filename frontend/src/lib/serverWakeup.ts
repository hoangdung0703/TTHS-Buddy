// Render Free spins the backend down after ~15 minutes with no requests, and the first request
// after that waits for the instance to boot - measured 46.45s and 44.14s on two independent cold
// samples, against warm requests of 0.19-0.27s (see DEPLOYMENT.md "Instance Type"). Whoever
// arrives first pays that, on top of the normal request time.
//
// Two mitigations live here, and neither one removes the wait - only the Instance Type does:
//
//  1. warmUpBackend(): a fire-and-forget ping sent as soon as a page mounts, so the boot overlaps
//     the time the student spends reading the page or typing their credentials instead of being
//     paid later, in full, on their first real request.
//  2. SLOW_REQUEST_* : the copy and threshold for telling the student what the wait is, rather
//     than leaving a spinner to imply the app is broken.

const HEALTH_PATH = "/api/health";
const WARM_UP_MIN_INTERVAL_MS = 10 * 60 * 1000;
const WARM_UP_STORAGE_KEY = "ttths:lastWarmUpAt";

// Long enough that a warm request (0.2s, or ~13s for a real chat answer) never trips it, short
// enough to land well before a 45s boot finishes.
export const SLOW_REQUEST_NOTICE_DELAY_MS = 7000;
export const SLOW_REQUEST_NOTICE =
  "Máy chủ đang khởi động lại sau thời gian nghỉ, lần đầu có thể mất tới 1 phút.";

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

// sessionStorage, not localStorage: the point is "once per browsing session per 10 minutes", and
// a value that outlives the tab would suppress the ping for a student who comes back hours later
// to a service that has long since gone back to sleep. Every access is wrapped - sessionStorage
// throws in private-mode Safari and can be blocked outright by site-data settings, and a warm-up
// ping must never be the thing that breaks a page render.
function shouldPingNow(): boolean {
  try {
    const last = window.sessionStorage.getItem(WARM_UP_STORAGE_KEY);
    if (last === null) {
      return true;
    }
    const elapsed = Date.now() - Number(last);
    return !Number.isFinite(elapsed) || elapsed >= WARM_UP_MIN_INTERVAL_MS;
  } catch {
    // Storage unavailable: ping anyway. An extra ping costs one cheap request; skipping it would
    // hand the student the full boot wait.
    return true;
  }
}

function recordPing(): void {
  try {
    window.sessionStorage.setItem(WARM_UP_STORAGE_KEY, String(Date.now()));
  } catch {
    // Ignored on purpose - see shouldPingNow.
  }
}

/**
 * Fire-and-forget wake-up ping. Deliberately:
 *  - mode "no-cors", so it works regardless of what CORS_ALLOWED_ORIGINS currently says and can
 *    never surface a console CORS error; the response is opaque and we do not read it, because
 *    the only thing that matters is that the request reached the instance and started the boot.
 *  - no Authorization header. /api/health is the one unauthenticated route, and sending a token
 *    to wake a server up would put it in logs for no reason.
 *  - every failure swallowed. If the backend is down, warming up is not the caller's problem to
 *    report; the real request that follows will surface a real error.
 *  - returns void, not a promise to await. Awaiting it would reintroduce exactly the delay this
 *    exists to hide.
 */
export function warmUpBackend(): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!shouldPingNow()) {
    return;
  }
  recordPing();
  try {
    void fetch(`${apiBaseUrl()}${HEALTH_PATH}`, {
      method: "GET",
      mode: "no-cors",
      cache: "no-store",
      credentials: "omit"
    }).catch(() => {
      // Ignored on purpose.
    });
  } catch {
    // Ignored on purpose - a synchronous throw (malformed base URL) must not break the page.
  }
}
