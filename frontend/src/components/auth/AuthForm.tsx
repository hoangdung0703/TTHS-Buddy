"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type CSSProperties, type FormEvent, useEffect, useState } from "react";
import { BookOpenCheck, ListChecks, ScrollText } from "lucide-react";

import { Seal } from "@/components/brand/Seal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getSupabaseClient } from "@/lib/supabaseClient";
import { cn } from "@/lib/utils";

const appendixPoints = [
  { numeral: "I", icon: ScrollText, label: "Mọi câu trả lời đều có căn cứ điều luật cụ thể", delay: 440 },
  { numeral: "II", icon: ListChecks, label: "5 bộ đề trắc nghiệm, chấm điểm kèm giải thích", delay: 520 },
  { numeral: "III", icon: BookOpenCheck, label: "Theo dõi từ khoá và chủ đề cần ôn tập", delay: 600 }
];

const quoteLines = [
  { text: "Không ai", delay: 0 },
  { text: "bị xem là", delay: 100 },
  { text: "có tội.", delay: 200 }
];

function riseStyle(delayMs: number): CSSProperties {
  return { animationDelay: `${delayMs}ms`, animationFillMode: "both" };
}

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
    <main className="relative z-[2] flex min-h-screen">
      <aside className="relative hidden w-[42%] max-w-lg flex-col justify-between overflow-hidden bg-steel-blue-900 p-10 text-steel-blue-50 shadow-[10px_0_28px_rgba(17,27,41,0.12)] md:flex">
        <div className="flex items-start justify-between">
          <Link href="/" className="font-serif text-lg font-semibold text-white">
            TTHS Buddy
          </Link>
          <Seal size={92} className="-mr-2 -mt-2 text-seal-red-400" delayMs={780} />
        </div>

        <div className="space-y-6">
          <p className="font-serif text-4xl font-medium leading-[1.05] text-steel-blue-50">
            {quoteLines.map(({ text, delay }) => (
              <span key={text} className="block animate-rise-in" style={riseStyle(delay)}>
                {text}
              </span>
            ))}
          </p>
          <Badge
            variant="outline"
            className="animate-rise-in border-steel-blue-700 bg-transparent text-steel-blue-200"
            style={riseStyle(340)}
          >
            <span>#</span> Tinh thần Điều 13 · BLTTHS 2015
          </Badge>

          <ol className="border-t border-steel-blue-800/60 pt-1">
            {appendixPoints.map(({ numeral, icon: Icon, label, delay }, index) => (
              <li
                key={label}
                className={cn(
                  "flex animate-rise-in items-start gap-2.5 py-3 text-sm text-steel-blue-100",
                  index > 0 && "border-t border-steel-blue-800/60"
                )}
                style={riseStyle(delay)}
              >
                <span className="w-5 shrink-0 font-serif text-xs font-semibold text-steel-blue-300">{numeral}.</span>
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-steel-blue-300" strokeWidth={1.75} />
                <span>{label}</span>
              </li>
            ))}
          </ol>
        </div>

        <p className="text-[11px] font-medium uppercase leading-5 tracking-[0.18em] text-steel-blue-300">
          Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </p>
      </aside>

      <section className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center justify-between md:hidden">
            <Link href="/" className="font-serif text-lg font-semibold text-foreground">
              TTHS Buddy
            </Link>
            <Seal size={64} />
          </div>

          <div className="animate-rise-in space-y-2">
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-steel-blue-600">
              {isSignIn ? "Đăng nhập" : "Đăng ký"}
            </p>
            <h1 className="font-serif text-4xl font-semibold leading-tight text-foreground sm:text-5xl">
              {isSignIn ? "Chào mừng trở lại" : "Tạo tài khoản của bạn"}
            </h1>
            <p className="text-sm text-muted-foreground">
              Dùng email và mật khẩu để {isSignIn ? "tiếp tục học" : "bắt đầu học"}.
            </p>
          </div>

          <form
            className="mt-8 animate-rise-in space-y-4 [animation-delay:120ms]"
            style={{ animationFillMode: "both" }}
            onSubmit={handleSubmit}
          >
            <label className="block space-y-2">
              <span className="text-sm font-medium text-foreground">Email</span>
              <Input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
              />
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-foreground">Mật khẩu</span>
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                autoComplete={isSignIn ? "current-password" : "new-password"}
                minLength={6}
              />
            </label>

            {error.length > 0 ? (
              <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </p>
            ) : null}

            {message.length > 0 ? (
              <p className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {message}
              </p>
            ) : null}

            <Button className="w-full" size="lg" type="submit" disabled={loading}>
              {loading ? "Đang xử lý..." : isSignIn ? "Đăng nhập" : "Đăng ký"}
            </Button>
          </form>

          <p className="mt-6 text-sm text-muted-foreground">
            {isSignIn ? "Chưa có tài khoản?" : "Đã có tài khoản?"}{" "}
            <Link className="font-medium text-foreground underline underline-offset-4" href={isSignIn ? "/register" : "/login"}>
              {isSignIn ? "Đăng ký" : "Đăng nhập"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
