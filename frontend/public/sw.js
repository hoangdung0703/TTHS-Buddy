// Hand-written service worker (no Workbox/next-pwa) - the PWA scope here is deliberately
// small ("installable app", not offline-first, see requirements.md "Feature - PWA"), so a
// build-integrated precache manifest would be more machinery than the job needs.
//
// Rules, matching requirements.md exactly:
//   1. Static assets (JS/CSS/font/icon, incl. Next's hashed /_next/static chunks): cache-first.
//   2. /api/* : network-only, always, including GET - never serve or store a cached response.
//      Chat/quiz/dashboard data must always be fresh; a stale cache hit would look like a
//      real (wrong) answer instead of an obvious error.
//   3. Full-page navigations that fail while offline: serve the /offline fallback page
//      instead of the browser's default "no internet" error screen.

const CACHE_VERSION = "v2";
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const OFFLINE_CACHE = `offline-${CACHE_VERSION}`;
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(OFFLINE_CACHE).then((cache) => cache.add(OFFLINE_URL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== STATIC_CACHE && key !== OFFLINE_CACHE)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isStaticAsset(request, url) {
  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    return true;
  }
  return ["script", "style", "font", "image"].includes(request.destination);
}

async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) {
    return cached;
  }

  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, response.clone());
  }
  return response;
}

async function navigationWithOfflineFallback(request) {
  try {
    return await fetch(request);
  } catch {
    const cache = await caches.open(OFFLINE_CACHE);
    const fallback = await cache.match(OFFLINE_URL);
    return fallback ?? Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // Explicit network-only: no respondWith interception beyond a bare fetch pass-through, so a
  // failure surfaces to the caller as a normal rejected fetch() - never a hang, never cached data.
  if (isApiRequest(url)) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(navigationWithOfflineFallback(request));
    return;
  }

  if (isStaticAsset(request, url)) {
    event.respondWith(cacheFirst(request));
  }
});
