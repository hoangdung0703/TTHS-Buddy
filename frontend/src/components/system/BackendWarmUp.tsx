"use client";

import { useEffect } from "react";

import { warmUpBackend } from "@/lib/serverWakeup";

/**
 * Renders nothing; exists so a SERVER component (the landing page) can still trigger the backend
 * wake-up ping, which needs a browser and an effect. Client components that already exist -
 * AuthForm, AuthenticatedLayout - call warmUpBackend() directly instead of mounting this.
 */
export function BackendWarmUp(): null {
  useEffect(() => {
    warmUpBackend();
  }, []);
  return null;
}
