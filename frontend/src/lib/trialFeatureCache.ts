// Per-user memory of whether "Phiên tòa giả định" is on. Pure (no React, no fetch, no "@/" imports)
// so tests/trialFeatureCache.test.mjs can load it with Node; api.ts wires it to Supabase and fetch.
//
// With TRIAL_ALLOWED_EMAILS the answer depends on who asks, so it is keyed by the signed-in user's
// id: a different user (sign-in, sign-out, account switch) starts again from "unknown". There is no
// probe without a token. Each user is probed once per page load; only a definite answer is kept, so a
// network error or 5xx leaves "unknown" and the next caller asks again. Memory only, never storage.

export type TrialFeatureStatus = "unknown" | "enabled" | "disabled";
export type KnownTrialFeatureStatus = Exclude<TrialFeatureStatus, "unknown">;

export interface TrialFeatureUser {
  id: string;
  token: string;
}

export interface TrialFeatureDeps {
  // The signed-in user, or null when signed out.
  currentUser: () => Promise<TrialFeatureUser | null>;
  // One probe request made with this token. Throwing counts as "unknown".
  probe: (token: string) => Promise<TrialFeatureStatus>;
}

export interface TrialFeatureCache {
  getStatus: () => TrialFeatureStatus;
  getUserId: () => string | null;
  subscribe: (listener: (status: TrialFeatureStatus) => void) => () => void;
  // Resolves with the current user's status; "unknown" when signed out or the probe failed.
  probe: () => Promise<TrialFeatureStatus>;
  // A trial request made as `userId` answered definitively (2xx = enabled, flag 404 = disabled).
  remember: (status: KnownTrialFeatureStatus, userId: string | null) => void;
  // The signed-in user changed (or signed out: null). Drops the previous user's answer.
  setUser: (userId: string | null) => void;
}

export function createTrialFeatureCache(deps: TrialFeatureDeps): TrialFeatureCache {
  let userId: string | null = null;
  let status: TrialFeatureStatus = "unknown";
  let inFlight: { userId: string; promise: Promise<TrialFeatureStatus> } | null = null;
  const listeners = new Set<(status: TrialFeatureStatus) => void>();

  function notify(): void {
    listeners.forEach((listener) => listener(status));
  }

  function setUser(nextUserId: string | null): void {
    if (nextUserId === userId) {
      return;
    }
    const changed = status !== "unknown";
    userId = nextUserId;
    status = "unknown";
    inFlight = null;
    if (changed) {
      notify();
    }
  }

  function remember(next: KnownTrialFeatureStatus, forUserId: string | null): void {
    if (forUserId === null) {
      return;
    }
    setUser(forUserId);
    if (status !== next) {
      status = next;
      notify();
    }
  }

  async function probe(): Promise<TrialFeatureStatus> {
    const user = await deps.currentUser();
    setUser(user?.id ?? null);
    if (user === null) {
      return "unknown";
    }
    if (status !== "unknown") {
      return status;
    }
    if (inFlight !== null && inFlight.userId === user.id) {
      return inFlight.promise;
    }
    const request = deps
      .probe(user.token)
      .catch((): TrialFeatureStatus => "unknown")
      .then((result) => {
        // A sign-out or account switch while the request ran makes its answer someone else's.
        if (userId !== user.id) {
          return "unknown";
        }
        if (inFlight?.promise === request) {
          inFlight = null;
        }
        if (result !== "unknown") {
          remember(result, user.id);
        }
        return status;
      });
    inFlight = { userId: user.id, promise: request };
    return request;
  }

  return {
    getStatus: () => status,
    getUserId: () => userId,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    probe,
    remember,
    setUser
  };
}
