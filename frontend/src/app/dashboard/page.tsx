"use client";

import { AlertCircle, BookOpenCheck, MessageSquare, MessagesSquare, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress-bar";
import { useAuthSession } from "@/hooks/useAuthSession";
import { getDashboardStats, getKeywordsYesterday, getWeakTopics } from "@/lib/api";
import type { DashboardStats, KeywordYesterday, WeakTopic } from "@/lib/types";

type LoadState = "loading" | "ready" | "error";

interface DashboardData {
  stats: DashboardStats;
  keywords: KeywordYesterday[];
  weakTopics: WeakTopic[];
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

export default function DashboardPage() {
  const { email } = useAuthSession();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  function loadDashboard(): void {
    setLoadState("loading");

    Promise.all([getDashboardStats(), getKeywordsYesterday(), getWeakTopics()])
      .then(([stats, keywords, weakTopics]) => {
        setData({ stats, keywords, weakTopics });
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
          <Button asChild className="rounded-full">
            <Link href="/chat">
              <MessageSquare className="mr-2 h-4 w-4" />
              Hỏi trợ lý AI
            </Link>
          </Button>
        </div>

        {loadState === "loading" ? (
          <div className="grid gap-4 md:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-24 animate-pulse rounded-lg border border-border bg-muted/60" />
            ))}
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
            <div className="grid gap-4 md:grid-cols-3">
              <Card>
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-accent-foreground">
                    <BookOpenCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-2xl font-semibold text-foreground">{data.stats.total_quiz_attempts}</p>
                    <p className="text-xs text-muted-foreground">Bài đã làm</p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-accent-foreground">
                    <BookOpenCheck className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-2xl font-semibold text-foreground">{data.stats.dieu_studied_count}</p>
                    <p className="text-xs text-muted-foreground">Điều đã học</p>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-accent text-accent-foreground">
                    <MessagesSquare className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-2xl font-semibold text-foreground">{data.stats.average_score}%</p>
                    <p className="text-xs text-muted-foreground">Điểm trung bình</p>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
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
                            {keyword.dieu_number} · {keyword.keyword}
                          </Badge>
                        </Link>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="font-serif text-base font-light tracking-tight">Tiến độ trắc nghiệm</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-baseline gap-2">
                    <p className="text-3xl font-semibold text-foreground">{data.stats.average_score}%</p>
                    <p className="text-sm text-muted-foreground">điểm trung bình</p>
                  </div>
                  <ProgressBar percentage={data.stats.average_score} />
                  <p className="text-sm text-muted-foreground">{data.stats.total_quiz_attempts} bài đã làm</p>
                </CardContent>
              </Card>
            </div>

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
                  data.weakTopics.map((topic) => (
                    <div key={topic.topic_category} className="space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{topic.topic_category}</p>
                          <Badge variant={topic.score_percentage < 50 ? "danger" : "warning"}>
                            {topic.score_percentage}%
                          </Badge>
                        </div>
                        <Button asChild variant="outline" size="sm">
                          <Link href="/quiz">Ôn tập</Link>
                        </Button>
                      </div>
                      <ProgressBar percentage={topic.score_percentage} />
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>
    </AuthenticatedLayout>
  );
}
