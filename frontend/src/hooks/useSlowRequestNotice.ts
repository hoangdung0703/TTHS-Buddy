"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { SLOW_REQUEST_NOTICE_DELAY_MS } from "@/lib/serverWakeup";

/**
 * Shows a notice when a request has produced nothing for SLOW_REQUEST_NOTICE_DELAY_MS, so a
 * Render Free cold boot (~45s, see DEPLOYMENT.md) reads as "the server is waking up" instead of
 * as a frozen page.
 *
 * Returns `isSlow` plus the two calls that bracket a request. `stop()` is safe to call more than
 * once and from a finally block, which is how every caller here uses it.
 *
 * The timer is cleared on unmount as well as on stop - navigating away mid-request would
 * otherwise leave a setState pointing at a gone component.
 */
export function useSlowRequestNotice(): {
  isSlow: boolean;
  start: () => void;
  stop: () => void;
} {
  const [isSlow, setIsSlow] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = useCallback((): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const start = useCallback((): void => {
    clear();
    setIsSlow(false);
    timerRef.current = setTimeout(() => setIsSlow(true), SLOW_REQUEST_NOTICE_DELAY_MS);
  }, [clear]);

  const stop = useCallback((): void => {
    clear();
    setIsSlow(false);
  }, [clear]);

  useEffect(() => clear, [clear]);

  return { isSlow, start, stop };
}
