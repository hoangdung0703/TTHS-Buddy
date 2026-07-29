"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getSupabaseClient } from "@/lib/supabaseClient";

interface AuthSessionState {
  loading: boolean;
  email: string | null;
}

// Redirects to /login whenever there is no active Supabase session, and keeps
// the returned email in sync with sign-in / sign-out events.
export function useAuthSession(): AuthSessionState {
  const router = useRouter();
  const [state, setState] = useState<AuthSessionState>({ loading: true, email: null });

  useEffect(() => {
    const supabase = getSupabaseClient();

    const loadSession = async (): Promise<void> => {
      const { data } = await supabase.auth.getSession();
      const session = data.session;

      if (session === null) {
        router.replace("/login");
        return;
      }

      setState({ loading: false, email: session.user.email ?? null });
    };

    void loadSession();

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session === null) {
        router.replace("/login");
        return;
      }

      setState({ loading: false, email: session.user.email ?? null });
    });

    return () => {
      subscription.subscription.unsubscribe();
    };
  }, [router]);

  return state;
}
