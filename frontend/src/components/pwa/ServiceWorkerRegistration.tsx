"use client";

import { useEffect } from "react";

// Only registered in production builds - Next dev serves unhashed, frequently-changing chunks
// via webpack HMR, and a cache-first service worker would fight that (stale/missing chunks
// after every edit) for zero benefit in local development.
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) {
      return;
    }

    void navigator.serviceWorker.register("/sw.js");
  }, []);

  return null;
}
