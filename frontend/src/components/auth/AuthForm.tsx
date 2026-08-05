"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactElement, useEffect, useState } from "react";
import { ArrowLeft, Eye, EyeOff, Scale } from "lucide-react";

import { BackgroundOrbs } from "@/components/brand/BackgroundOrbs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getSupabaseClient } from "@/lib/supabaseClient";

// Sizing/shape only — border, bg, text, and focus-ring colors now come from the shared
// Input component's own semantic defaults (border-border/bg-background/ring-ring), which
// resolve to this palette automatically. ring-offset-card is the one deliberate override:
// these inputs sit on the card surface, not the page background, so the ring offset needs
// to match its immediate surroundings to render crisply.
const inputClass = "h-11 rounded-[0.6rem] bg-card px-3.5 focus-visible:ring-offset-card";

type AuthMode = "sign-in" | "sign-up";

interface AuthFormProps {
  mode: AuthMode;
}

function GoogleIcon({ className }: { className?: string }): ReactElement {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path
        d="M23.04 12.27c0-.79-.07-1.54-.2-2.27H12v4.3h6.19a5.28 5.28 0 0 1-2.29 3.47v2.88h3.7c2.17-1.99 3.42-4.93 3.42-8.38Z"
        fill="#4285F4"
      />
      <path
        d="M12 24c3.1 0 5.7-1.03 7.6-2.79l-3.7-2.88c-1.03.69-2.35 1.1-3.9 1.1-3 0-5.54-2.03-6.45-4.75H1.73v2.97A12 12 0 0 0 12 24Z"
        fill="#34A853"
      />
      <path
        d="M5.55 14.68A7.19 7.19 0 0 1 5.18 12c0-.93.16-1.83.37-2.68V6.35H1.73A12 12 0 0 0 0 12c0 1.94.46 3.77 1.73 5.65l3.82-2.97Z"
        fill="#FBBC05"
      />
      <path
        d="M12 4.77c1.68 0 3.19.58 4.38 1.71l3.29-3.29C17.7 1.19 15.1 0 12 0A12 12 0 0 0 1.73 6.35l3.82 2.97C6.46 6.6 9 4.77 12 4.77Z"
        fill="#EA4335"
      />
    </svg>
  );
}

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [showPassword, setShowPassword] = useState<boolean>(false);
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

  async function handleGoogleSignIn(): Promise<void> {
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const supabase = getSupabaseClient();
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/dashboard` },
      });

      if (oauthError !== null) {
        setError(oauthError.message);
        setLoading(false);
      }
      // On success the browser redirects to Google, so no further state update here.
    } catch (oauthError) {
      const errorMessage = oauthError instanceof Error ? oauthError.message : "Google sign-in failed";
      setError(errorMessage);
      setLoading(false);
    }
  }

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
    <main className="relative flex min-h-screen flex-col items-center justify-center gap-8 bg-background px-4 py-12 font-sans">
      <BackgroundOrbs />

      <div className="relative z-10 flex w-full max-w-[420px] flex-col gap-8">
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Scale className="h-4 w-4" />
            </span>
            <span className="font-serif text-lg font-normal tracking-tight text-foreground">TTHS Buddy</span>
          </Link>
          <Link
            href="/"
            className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={13} strokeWidth={1.8} />
            Trang chủ
          </Link>
        </div>

        <div className="w-full rounded-[1.25rem] border border-primary/[0.07] bg-card p-8 shadow-[0_8px_48px_rgba(30,36,96,0.10),0_1px_4px_rgba(30,36,96,0.06)] sm:p-11">
          <div className="mb-8">
            <h1 className="mb-2 font-serif text-[1.75rem] font-light leading-tight tracking-tight text-foreground">
              {isSignIn ? (
                "Chào mừng trở lại"
              ) : (
                <>
                  Bắt đầu hành trình
                  <br />
                  <span className="italic text-primary">học tập</span>
                </>
              )}
            </h1>
            <p className="text-sm font-light text-muted-foreground">
              {isSignIn ? "Tiếp tục hành trình ôn tập của bạn." : "Miễn phí. Không cần thẻ tín dụng."}
            </p>
          </div>

          <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-foreground">Email</span>
              <Input
                type="email"
                placeholder="ten@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
                className={inputClass}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-foreground">Mật khẩu</span>
              <div className="relative">
                <Input
                  type={showPassword ? "text" : "password"}
                  placeholder={isSignIn ? "••••••••" : "Tối thiểu 6 ký tự"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete={isSignIn ? "current-password" : "new-password"}
                  minLength={6}
                  className={`${inputClass} pr-10`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                >
                  {showPassword ? <EyeOff size={15} strokeWidth={1.6} /> : <Eye size={15} strokeWidth={1.6} />}
                </button>
              </div>
            </label>

            {error.length > 0 ? (
              <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
            ) : null}

            {message.length > 0 ? (
              <p className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {message}
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={loading}
              className="mt-1 h-auto w-full rounded-full px-6 py-3.5 text-[0.93rem] font-medium tracking-[0.01em] shadow-[0_4px_20px_rgba(30,36,96,0.22)] focus-visible:ring-offset-card active:scale-[0.99]"
            >
              {loading ? "Đang xử lý..." : isSignIn ? "Đăng nhập" : "Tạo tài khoản miễn phí"}
            </Button>
          </form>

          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs font-light uppercase tracking-wide text-muted-foreground/70">hoặc</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <Button
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => void handleGoogleSignIn()}
            className="h-auto w-full gap-2.5 rounded-full border-primary/[0.12] bg-card px-6 py-3.5 text-[0.93rem] font-medium text-foreground hover:bg-muted/50 focus-visible:ring-offset-card active:scale-[0.99]"
          >
            <GoogleIcon className="h-4 w-4 shrink-0" />
            Tiếp tục với Google
          </Button>

          {!isSignIn && (
            <p className="mt-5 text-center text-xs leading-relaxed text-muted-foreground/80">
              Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp.
            </p>
          )}

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isSignIn ? "Chưa có tài khoản?" : "Đã có tài khoản?"}{" "}
            <Link
              className="font-medium text-primary underline-offset-4 hover:underline"
              href={isSignIn ? "/register" : "/login"}
            >
              {isSignIn ? "Đăng ký" : "Đăng nhập"}
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
