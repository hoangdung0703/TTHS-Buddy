"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { EssayBankMiniTracker } from "@/components/essay/EssayBankMiniTracker";
import { ProgressRing } from "@/components/quiz/ProgressRing";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthSession } from "@/hooks/useAuthSession";
import { getEssayBanksV2, getKeywordsYesterday, getQuizStatsV2, getWeakTopics } from "@/lib/api";
import { ESSAY_BANK_TITLES } from "@/lib/essayBankPresentation";
import type { EssayBankCategory, EssayBankV2, KeywordYesterday, QuizStatsV2, WeakTopic } from "@/lib/types";

type LoadState = "loading" | "ready" | "error";

interface DashboardData {
  keywords: KeywordYesterday[];
  weakTopics: WeakTopic[];
  quizStats: QuizStatsV2;
  essayBanks: EssayBankV2[];
}

// essay_attempts.category (Phase 5a/5b v2 Buoc B, xem backend get_weak_topics) giờ đã là bank
// category THẬT do server suy ra từ lịch sử luyện tập tự luận của chính user, không còn phải
// đoán từ text topic_category ở client nữa. Fallback này chỉ dùng cho 1 weak-topic tới hoàn toàn
// từ quiz (chưa từng có lần luyện tự luận nào để suy ra bank thật).
const FALLBACK_ESSAY_BANK_CATEGORY: EssayBankCategory = "ly_thuyet";

function getEssayBankCategory(topic: WeakTopic): EssayBankCategory {
  return topic.essay_bank_category ?? FALLBACK_ESSAY_BANK_CATEGORY;
}

function getLowestScoringTopic(weakTopics: WeakTopic[]): WeakTopic | null {
  return weakTopics.reduce<WeakTopic | null>((lowest, topic) => {
    if (lowest === null || topic.score_percentage < lowest.score_percentage) {
      return topic;
    }
    return lowest;
  }, null);
}

// Hero rotation (requirements.md "Feature — Redesign Dashboard Hero"): 3 variant xoay tuần tự
// mỗi lần vào lại /dashboard hoặc refresh, lưu index thuần UI-state trong localStorage (không
// phải dữ liệu nhạy cảm, không cần backend). User hoàn toàn mới (chưa có weak-topic) chỉ xoay
// Variant 2/3 vì chưa có gì để gợi ý ở Variant 1.
type HeroVariant = "essay" | "quiz" | "minigame";

const HERO_VARIANT_STORAGE_KEY = "ttbuddy_dashboard_hero_variant_index";

function getNextHeroVariantIndex(variantCount: number): number {
  if (typeof window === "undefined") {
    return 0;
  }
  const stored = Number.parseInt(window.localStorage.getItem(HERO_VARIANT_STORAGE_KEY) ?? "", 10);
  const previous = Number.isNaN(stored) ? -1 : stored;
  const next = (previous + 1) % variantCount;
  window.localStorage.setItem(HERO_VARIANT_STORAGE_KEY, String(next));
  return next;
}

function pickHeroVariant(index: number, hasWeakTopic: boolean): HeroVariant {
  const variants: HeroVariant[] = hasWeakTopic ? ["essay", "quiz", "minigame"] : ["quiz", "minigame"];
  return variants[index] ?? variants[0];
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

// Variant 1 - Essay: gợi ý ngân hàng tự luận theo weak-topic yếu nhất, kèm tiến độ ngân hàng đó
// (X/Y câu đã luyện, lấy từ đúng data source Khối 2 hiện có, không gọi API riêng).
function EssayHero({ topic, essayBanks }: { topic: WeakTopic; essayBanks: EssayBankV2[] }) {
  const category = getEssayBankCategory(topic);
  const bank = essayBanks.find((b) => b.category === category) ?? null;
  const attempted = bank?.progress.kind !== "untouched" ? (bank?.progress.attempted_count ?? 0) : 0;

  return (
    <HeroShell
      eyebrow="Gợi ý hôm nay · Tự luận"
      message={
        <>
          Chủ đề <span className="italic">{topic.topic_category}</span> đang ở{" "}
          <span className="inline-flex items-center rounded-full bg-accent px-2 py-0.5 font-sans text-sm font-semibold text-accent-foreground">
            {topic.score_percentage}%
          </span>{" "}
          - đây là chủ đề yếu nhất của bạn.
          {bank !== null ? (
            <span className="mt-1 block text-sm font-sans font-normal text-muted-foreground">
              Ngân hàng {ESSAY_BANK_TITLES[category]}: {attempted}/{bank.total_questions} câu đã luyện.
            </span>
          ) : null}
        </>
      }
      cta={
        <Button asChild className="rounded-full">
          <Link href={`/essay/${category}`}>Luyện tập ngay</Link>
        </Button>
      }
    />
  );
}

// Variant 2 - MCQ: tiến độ trắc nghiệm tổng hợp, dùng chung state đã fetch cho Khối 1 (không gọi
// API riêng).
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

// Variant 3 - Minigame: gợi ý "Tôi hỏi bạn trả lời", không hiện tiến độ (minigame không track
// hoàn thành theo thiết kế).
function MinigameHero() {
  return (
    <HeroShell
      eyebrow="Gợi ý hôm nay · Minigame"
      message={
        <>Thử sức với &ldquo;Tôi hỏi bạn trả lời&rdquo; - một câu hỏi tự luận ngẫu nhiên từ toàn bộ ngân hàng, không giới hạn chủ đề.</>
      }
      cta={
        <Button asChild className="rounded-full">
          <Link href="/essay/practice">Thử ngay</Link>
        </Button>
      }
    />
  );
}

function DashboardHero({
  variant,
  weakTopics,
  quizStats,
  essayBanks
}: {
  variant: HeroVariant;
  weakTopics: WeakTopic[];
  quizStats: QuizStatsV2;
  essayBanks: EssayBankV2[];
}) {
  if (variant === "essay") {
    const lowestTopic = getLowestScoringTopic(weakTopics);
    if (lowestTopic !== null) {
      return <EssayHero topic={lowestTopic} essayBanks={essayBanks} />;
    }
  }

  if (variant === "quiz") {
    return <QuizHero quizStats={quizStats} />;
  }

  return <MinigameHero />;
}

export default function DashboardPage() {
  const { email } = useAuthSession();
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [data, setData] = useState<DashboardData | null>(null);
  const [heroVariant, setHeroVariant] = useState<HeroVariant | null>(null);
  const heroVariantPicked = useRef(false);

  useEffect(() => {
    loadDashboard();
  }, []);

  function loadDashboard(): void {
    setLoadState("loading");

    Promise.all([getKeywordsYesterday(), getWeakTopics(), getQuizStatsV2(), getEssayBanksV2()])
      .then(([keywords, weakTopics, quizStats, essayBanks]) => {
        setData({ keywords, weakTopics, quizStats, essayBanks });
        setLoadState("ready");

        if (!heroVariantPicked.current) {
          heroVariantPicked.current = true;
          const variantCount = weakTopics.length > 0 ? 3 : 2;
          const index = getNextHeroVariantIndex(variantCount);
          setHeroVariant(pickHeroVariant(index, weakTopics.length > 0));
        }
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

        {loadState === "ready" && data !== null && heroVariant !== null ? (
          <>
            <DashboardHero
              variant={heroVariant}
              weakTopics={data.weakTopics}
              quizStats={data.quizStats}
              essayBanks={data.essayBanks}
            />

            <div className="grid gap-4 md:grid-cols-2">
              {/* Khối 1 - MCQ tổng hợp (data thật: GET /api/quiz/stats) */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-serif text-base font-light tracking-tight">Trắc nghiệm</CardTitle>
                </CardHeader>
                <CardContent className="flex items-center gap-5">
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
                </CardContent>
              </Card>

              {/* Khối 2 - 4 tracker tự luận song song (data thật: GET /api/essay/banks) */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-serif text-base font-light tracking-tight">Tự luận theo ngân hàng</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-3">
                    {data.essayBanks.map((bank) => (
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
                          Điều {keyword.dieu_number} · {keyword.keyword}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Khối 4 - Chủ đề cần ôn lại (data thật). Nút "Ôn tập" mở /chat với câu hỏi tự động
                về đúng chủ đề, phân biệt có chủ đích với Hero Variant 1 (cũng gợi ý weak-topic
                nhưng dẫn vào luyện tập tự luận): Hero = "làm bài", đây = "hiểu lại khái niệm". */}
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
