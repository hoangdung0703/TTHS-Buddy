"use client";

import { AlertCircle, MessageSquare, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { EssayBankMiniTracker } from "@/components/essay/EssayBankMiniTracker";
import { ProgressRing } from "@/components/quiz/ProgressRing";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress-bar";
import { useAuthSession } from "@/hooks/useAuthSession";
import { getKeywordsYesterday, getWeakTopics } from "@/lib/api";
// TODO: Phase 7 v2 - chờ Quiz v2/Essay v2 backend (Bước 2). Khối 1 và Khối 2 đọc mock ở đây
// (xem requirements.md "Phase 7 v2"), Khối 3/Khối 4/Hero's weak-topic detection dùng data thật
// bên dưới (getKeywordsYesterday/getWeakTopics, không đổi).
import { getMockQuizOverallStatsV2, mapWeakTopicToEssayBankCategoryMock, MOCK_ESSAY_BANKS_V2 } from "@/lib/mockDataV2";
import type { KeywordYesterday, WeakTopic } from "@/lib/types";

type LoadState = "loading" | "ready" | "error";

interface DashboardData {
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

// Hero - "Gợi ý hành động" (requirements.md "Phase 7 v2"): weak-topics thật quyết định có
// gợi ý cụ thể hay CTA chung, mapping topic -> essay bank là mock cho tới Bước 2.
function DashboardHero({ weakTopics }: { weakTopics: WeakTopic[] }) {
  const lowestTopic = weakTopics.reduce<WeakTopic | null>((lowest, topic) => {
    if (lowest === null || topic.score_percentage < lowest.score_percentage) {
      return topic;
    }
    return lowest;
  }, null);

  if (lowestTopic === null) {
    return (
      <Card className="border-primary/15 bg-primary/[0.04]">
        <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-primary">Bắt đầu học tập</p>
            <p className="font-serif text-lg font-light text-foreground">
              Chưa có dữ liệu để gợi ý chủ đề cần ôn - hãy làm quen với hệ thống trước.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Button asChild className="rounded-full">
              <Link href="/quiz">Bắt đầu với 1 bộ trắc nghiệm</Link>
            </Button>
            <Button asChild variant="outline" className="rounded-full">
              <Link href="/chat">
                <MessageSquare className="mr-2 h-4 w-4" />
                Hỏi trợ lý AI
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const suggestedCategory = mapWeakTopicToEssayBankCategoryMock(lowestTopic.topic_category);

  return (
    <Card className="border-accent/25 bg-accent/[0.06]">
      <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-accent">Gợi ý hôm nay</p>
          <p className="font-serif text-lg font-light text-foreground">
            Chủ đề <span className="italic">{lowestTopic.topic_category}</span> đang ở{" "}
            <span className="font-normal text-accent">{lowestTopic.score_percentage}%</span> - đây là chủ đề yếu nhất của bạn.
          </p>
        </div>
        <Button asChild className="shrink-0 rounded-full">
          <Link href={`/essay/${suggestedCategory}`}>Luyện tập ngay</Link>
        </Button>
      </CardContent>
    </Card>
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

    Promise.all([getKeywordsYesterday(), getWeakTopics()])
      .then(([keywords, weakTopics]) => {
        setData({ keywords, weakTopics });
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
  }

  const quizStats = getMockQuizOverallStatsV2();

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
            <div className="grid gap-4 md:grid-cols-2">
              {[0, 1].map((index) => (
                <div key={index} className="h-40 animate-pulse rounded-lg border border-border bg-muted/60" />
              ))}
            </div>
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
            <DashboardHero weakTopics={data.weakTopics} />

            <div className="grid gap-4 md:grid-cols-2">
              {/* Khối 1 - MCQ tổng hợp (MOCK, xem requirements.md "Phase 7 v2") */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-serif text-base font-light tracking-tight">Trắc nghiệm</CardTitle>
                </CardHeader>
                <CardContent className="flex items-center gap-5">
                  <ProgressRing correct={quizStats.correct_total} total={quizStats.questions_attempted} size={88} />
                  <div className="space-y-1">
                    <p className="font-serif text-2xl font-normal text-foreground">{quizStats.overall_correct_percentage}%</p>
                    <p className="text-sm text-muted-foreground">tỉ lệ đúng tổng thể</p>
                    <p className="text-xs text-muted-foreground">
                      Đã làm {quizStats.sets_touched} / {quizStats.total_sets} bộ đề
                    </p>
                    <Button asChild variant="outline" size="sm" className="mt-1 rounded-full">
                      <Link href="/quiz">Vào trắc nghiệm</Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Khối 2 - 4 tracker tự luận song song (MOCK, xem requirements.md "Phase 7 v2") */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-serif text-base font-light tracking-tight">Tự luận theo ngân hàng</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-3">
                    {MOCK_ESSAY_BANKS_V2.map((bank) => (
                      <EssayBankMiniTracker key={bank.category} bank={bank} />
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Khối 3 - Từ khoá hôm qua (data thật, giữ nguyên) */}
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

            {/* Khối 4 - Chủ đề cần ôn lại (data thật, thêm CTA vào ngân hàng tự luận tương ứng - mapping mock) */}
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
                    const category = mapWeakTopicToEssayBankCategoryMock(topic.topic_category);

                    return (
                      <div key={topic.topic_category} className="space-y-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-foreground">{topic.topic_category}</p>
                            <Badge variant={topic.score_percentage < 50 ? "danger" : "warning"}>{topic.score_percentage}%</Badge>
                          </div>
                          <Button asChild variant="outline" size="sm">
                            <Link href={`/essay/${category}`}>Ôn tập</Link>
                          </Button>
                        </div>
                        <ProgressBar percentage={topic.score_percentage} />
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
