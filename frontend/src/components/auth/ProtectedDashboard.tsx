"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getSupabaseClient } from "@/lib/supabaseClient";

interface ProtectedDashboardState {
  loading: boolean;
  email: string | null;
}

export function ProtectedDashboard() {
  const router = useRouter();
  const [state, setState] = useState<ProtectedDashboardState>({ loading: true, email: null });

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

  async function handleLogout(): Promise<void> {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/login");
  }

  if (state.loading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6 py-16">
        <section className="rounded-3xl border border-border bg-card px-8 py-6 shadow-xl">
          Đang kiểm tra phiên đăng nhập...
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-16">
      <section className="w-full max-w-xl rounded-3xl border border-border bg-card/95 p-8 shadow-2xl">
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-muted-foreground">Protected route</p>
        <h1 className="mt-2 text-4xl font-semibold text-foreground">Đã đăng nhập</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          {state.email !== null ? `Signed in as ${state.email}` : "Signed in session detected."}
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Button type="button" onClick={handleLogout} variant="secondary">
            Sign out
          </Button>
          <Button type="button" variant="outline" onClick={() => router.push("/")}>Home</Button>
        </div>
      </section>
    </main>
  );
}
