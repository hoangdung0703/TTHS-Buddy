"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getSupabaseClient } from "@/lib/supabaseClient";

type AuthMode = "sign-in" | "sign-up";

interface AuthFormProps {
  mode: AuthMode;
}

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const supabase = getSupabaseClient();

    void supabase.auth.getSession().then(({ data }) => {
      if (data.session !== null) {
        router.replace("/dashboard");
      }
    });
  }, [router]);

  const isSignIn = mode === "sign-in";

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const supabase = getSupabaseClient();
      const authResponse = isSignIn
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });

      if (authResponse.error !== null) {
        setError(authResponse.error.message);
        return;
      }

      if (!isSignIn && authResponse.data.session === null) {
        setMessage("Account created. Check your email to confirm the signup if required, then sign in.");
        return;
      }

      router.replace("/dashboard");
    } catch (submitError) {
      const errorMessage = submitError instanceof Error ? submitError.message : "Authentication failed";
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-16">
      <section className="w-full max-w-md rounded-3xl border border-border bg-card/95 p-8 shadow-2xl">
        <div className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-muted-foreground">
            {isSignIn ? "Sign in" : "Sign up"}
          </p>
          <h1 className="text-3xl font-semibold text-foreground">
            {isSignIn ? "Welcome back" : "Create your account"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Use your Supabase email/password credentials to continue.
          </p>
        </div>

        <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
          <label className="block space-y-2">
            <span className="text-sm font-medium text-foreground">Email</span>
            <input
              className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none transition focus:border-ring"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
            />
          </label>

          <label className="block space-y-2">
            <span className="text-sm font-medium text-foreground">Password</span>
            <input
              className="w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none transition focus:border-ring"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete={isSignIn ? "current-password" : "new-password"}
              minLength={6}
            />
          </label>

          {error.length > 0 ? (
            <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          ) : null}

          {message.length > 0 ? (
            <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {message}
            </p>
          ) : null}

          <Button className="w-full" type="submit" disabled={loading}>
            {loading ? "Please wait..." : isSignIn ? "Sign in" : "Sign up"}
          </Button>
        </form>

        <p className="mt-6 text-sm text-muted-foreground">
          {isSignIn ? "Need an account?" : "Already have an account?"}{" "}
          <Link className="font-medium text-foreground underline underline-offset-4" href={isSignIn ? "/register" : "/login"}>
            {isSignIn ? "Sign up" : "Sign in"}
          </Link>
        </p>
      </section>
    </main>
  );
}
