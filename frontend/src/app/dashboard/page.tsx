"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { ProgressRing } from "@/components/quiz/ProgressRing";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthSession } from "@/hooks/useAuthSession";
import { getKeywordsYesterday, getQuizStatsV2, getWeakTopics } from "@/lib/api";
import type { KeywordYesterday, QuizStatsV2, WeakTopic } from "@/lib/types";

type LoadState = "loading" | "ready" | "error";

interface DashboardData {
  keywords: KeywordYesterday[];
  weakTopics: WeakTopic[];
  quizStats: QuizStatsV2;
}

function getGreeting(hour: number): string {
  if (hour < 12) {
    return "Chào buổi sáng";
  }

  if (hour < 18) {
    return "Chào buổi chiều";
  }

  return "Chào buổi tối";
}

function getStudentDisplayName(email: string | null): string {
  if (email === null) {
    return "bạn";
  }

  return email.split("@")[0];
}

function HeroShell({
  eyebrow,
  message,
  cta
}: {
  eyebrow: string;
  message: ReactNode;
  cta: ReactNode;
}) {
  return (
    <Card className="border-accent/25 bg-accent/[0.06]">
      <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="mb-1 inline-flex w-fit items-center rounded-full bg-accent px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-accent-foreground">
            {eyebrow}
          </p>
          <div className="font-serif text-lg font-light text-foreground">{message}</div>
        </div>
        <div className="shrink-0">{cta}</div>
      </CardContent>
    </Card>
  );
}

// Khi ngân hàng đề rỗng (đang chờ ngân hàng mới) thì không gợi ý "làm bộ đề" - không có bộ nào để
// làm. Hero chuyển sang gợi ý Chat, thứ duy nhất vẫn dùng được đầy đủ lúc đó.
function NoBankHero() {
  return (
    <HeroShell
      eyebrow="Gợi ý hôm nay · Trợ lý AI"
      message={
        <>
          Ngân hàng đề trắc nghiệm đang được cập nhật.
          <span className="mt-1 block font-sans text-sm font-normal text-muted-foreground">
            Trong lúc chờ, hỏi trợ lý AI về bất kỳ Điều luật nào bạn đang vướng - câu trả lời luôn
            kèm căn cứ pháp lý.
          </span>
        </>
      }
      cta={
        <Button asChild className="rounded-full">
          <Link href="/chat">Hỏi trợ lý AI</Link>
        </Button>
      }
    />
  );
}

// Tiến độ trắc nghiệm tổng hợp, dùng chung state đã fetch cho Khối 1 (không gọi API riêng).
function QuizHero({ quizStats }: { quizStats: QuizStatsV2 }) {
  return (
    <HeroShell
      eyebrow="Gợi ý hôm nay · Trắc nghiệm"
      message={
        <>
          <div className="mb-1 flex items-center gap-3">
            <ProgressRing correct={quizStats.correct_total} total={quizStats.questions_total} size={44} />
            <span>
              Đã làm{" "}
              <span className="font-semibold">
                {quizStats.quiz_sets_attempted}/{quizStats.total_quiz_sets}
              </span>{" "}
              bộ đề, tỉ lệ đúng <span className="font-semibold">{quizStats.average_score_percentage}%</span>.
            </span>
          </div>
          Làm tiếp bộ đề tiếp theo để giữ phong độ.
        </>
      }
      cta={
        <Button asChild className="rounded-full">
          <Link href="/quiz">Vào trắc nghiệm</Link>
        </Button>
      }
    />
  );
}

export default function DashboardPage() {
  const { email } = useAuthSession();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  function loadDashboard(): void {
    setLoadState("loading");

    Promise.all([getKeywordsYesterday(), getWeakTopics(), getQuizStatsV2()])
      .then(([keywords, weakTopics, quizStats]) => {
        setData({ keywords, weakTopics, quizStats });
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
  }

  return (
    <AuthenticatedLayout title="Tổng quan học tập">
      <div className="relative isolate mx-auto max-w-6xl space-y-6 px-6 py-8">
        <div
          className="pointer-events-none absolute right-0 top-0 -z-10 h-[420px] w-[420px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(30,36,96,0.17) 0%, transparent 70%)", filter: "blur(64px)" }}
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute bottom-0 left-0 -z-10 h-[360px] w-[360px] rounded-full"
          style={{ background: "radial-gradient(circle, rgba(184,154,82,0.14) 0%, transparent 70%)", filter: "blur(56px)" }}
          aria-hidden="true"
        />

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="font-serif text-2xl font-light tracking-tight text-foreground">
              {getGreeting(new Date().getHours())}, {getStudentDisplayName(email)}
            </h2>
            <p className="text-sm text-muted-foreground">Đây là tổng quan học tập của bạn.</p>
          </div>
        </div>

        {loadState === "loading" ? (
          <div className="space-y-6">
            <div className="h-24 animate-pulse rounded-lg border border-border bg-muted/60" />
            <div className="h-40 animate-pulse rounded-lg border border-border bg-muted/60" />
          </div>
        ) : null}

        {loadState === "error" ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              Không tải được dữ liệu dashboard.
            </span>
            <Button variant="outline" size="sm" onClick={loadDashboard}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Thử lại
            </Button>
          </div>
        ) : null}

        {loadState === "ready" && data !== null ? (
          <>
            {data.quizStats.total_quiz_sets === 0 ? (
              <NoBankHero />
            ) : (
              <QuizHero quizStats={data.quizStats} />
            )}

            {/* Khối 1 - MCQ tổng hợp (data thật: GET /api/quiz/stats) */}
            <Card>
              <CardHeader>
                <CardTitle className="font-serif text-base font-light tracking-tight">Trắc nghiệm</CardTitle>
              </CardHeader>
              <CardContent>
                {data.quizStats.total_quiz_sets === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Ngân hàng đề đang được cập nhật - chưa có bộ đề nào để làm.
                  </p>
                ) : (
                  <div className="flex items-center gap-5">
                    <ProgressRing correct={data.quizStats.correct_total} total={data.quizStats.questions_total} size={88} />
                    <div className="space-y-1">
                      <p className="font-serif text-2xl font-normal text-foreground">{data.quizStats.average_score_percentage}%</p>
                      <p className="text-sm text-muted-foreground">tỉ lệ đúng tổng thể</p>
                      <p className="text-xs text-muted-foreground">
                        Đã làm {data.quizStats.quiz_sets_attempted} / {data.quizStats.total_quiz_sets} bộ đề
                      </p>
                      <Button asChild variant="outline" size="sm" className="mt-1 rounded-full">
                        <Link href="/quiz">Vào trắc nghiệm</Link>
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Khối 2 - Từ khoá hôm qua (data thật, giữ nguyên) */}
            <Card>
              <CardHeader>
                <CardTitle className="font-serif text-base font-light tracking-tight">Từ khoá hôm qua</CardTitle>
              </CardHeader>
              <CardContent>
                {data.keywords.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Chưa có câu hỏi nào được ghi nhận hôm qua.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {data.keywords.map((keyword) => (
                      <Link key={`${keyword.dieu_number}-${keyword.keyword}`} href="/chat">
                        <Badge variant="outline" className="hover:bg-accent">
                          Điều {keyword.dieu_number} · {keyword.keyword}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Khối 3 - Chủ đề cần ôn lại (data thật). Nút "Ôn tập" mở /chat với câu hỏi tự động
                về đúng chủ đề - "hiểu lại khái niệm", khác với Hero ở trên là "làm bài". */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="font-serif text-base font-light tracking-tight">Chủ đề cần ôn lại</CardTitle>
                  <Badge variant="warning">{data.weakTopics.length} chủ đề</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {data.weakTopics.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Không có chủ đề nào cần ôn lại.</p>
                ) : (
                  data.weakTopics.map((topic) => {
                    const chatQuery = `Giải thích cho tôi về: ${topic.topic_category}`;

                    return (
                      <div key={topic.topic_category} className="flex items-center justify-between gap-3">
                        <p className="text-sm font-medium text-foreground">{topic.topic_category}</p>
                        <Button asChild variant="outline" size="sm">
                          <Link href={`/chat?q=${encodeURIComponent(chatQuery)}`}>Ôn tập</Link>
                        </Button>
                      </div>
                    );
                  })
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>
    </AuthenticatedLayout>
  );
}
