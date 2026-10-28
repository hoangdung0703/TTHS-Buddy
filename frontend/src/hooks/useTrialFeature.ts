"use client";

import { useEffect, useState } from "react";

import { getTrialFeatureStatus, probeTrialFeature, subscribeTrialFeature, type TrialFeatureStatus } from "@/lib/api";

// Whether "Phiên tòa giả định" is on for this backend. The first caller after login triggers the one
// HEAD /api/trials probe (see probeTrialFeature); everyone else reads the in-memory answer and is
// told when a later trial request discovers the flag changed.
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
