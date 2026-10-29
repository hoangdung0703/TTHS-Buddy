"use client";

import { useEffect, useState } from "react";

import { getTrialFeatureStatus, probeTrialFeature, subscribeTrialFeature, type TrialFeatureStatus } from "@/lib/api";

// Whether "Phiên tòa giả định" is on for the signed-in user. The answer is kept per user in memory
// (lib/trialFeatureCache.ts via probeTrialFeature): the first caller for a user triggers the one
// HEAD /api/trials probe, a sign-in, sign-out or account switch resets it to "unknown", and every
// subscriber is told when it changes. "unknown" hides the menu but redirects nowhere.
export function useTrialFeature(): TrialFeatureStatus {
  const [status, setStatus] = useState<TrialFeatureStatus>(getTrialFeatureStatus);

  useEffect(() => {
    const unsubscribe = subscribeTrialFeature(setStatus);
    let cancelled = false;
    void probeTrialFeature().then((result) => {
      if (!cancelled) {
        setStatus(result);
      }
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  return status;
}
