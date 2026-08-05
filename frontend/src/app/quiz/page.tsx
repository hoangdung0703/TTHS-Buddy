"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { ProgressRing } from "@/components/quiz/ProgressRing";
import { Button } from "@/components/ui/button";
import { getQuizSetsV2 } from "@/lib/api";
import type { QuizSetSummaryV2 } from "@/lib/types";
import { cn } from "@/lib/utils";

function QuizSetCard({ set }: { set: QuizSetSummaryV2 }) {
  const { status } = set;
  const isDone = status.kind === "done";
  const label = `Bộ đề ${String(set.quiz_set_id).padStart(2, "0")}`;

  return (
    <Link
      href={`/quiz/${set.quiz_set_id}`}
      className={cn(
        "group flex flex-col gap-2.5 rounded-xl border px-4 py-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md",
        isDone ? "border-accent/30 bg-accent/[0.06]" : "border-border bg-card hover:bg-primary/[0.03]"
      )}
    >
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "font-sans text-xs font-semibold uppercase tracking-wider",
            isDone ? "text-accent" : "text-primary"
          )}
        >
          {label}
        </span>
        {isDone && <ProgressRing correct={status.correct_count} total={set.total_questions} />}
      </div>

      <div className="min-h-[1.1rem] font-sans text-xs">
        {isDone ? (
          <span className={status.correct_count === set.total_questions ? "text-accent" : "text-muted-foreground"}>
            {status.correct_count === set.total_questions
              ? `Hoàn thành · ${set.total_questions}/${set.total_questions} đúng`
              : `Đã hoàn thành · ${status.correct_count}/${set.total_questions} đúng`}
          </span>
        ) : (
          <span className="text-muted-foreground/60">Chưa làm</span>
        )}
      </div>

      <span className="rounded-full bg-primary px-3 py-1 text-center font-sans text-xs font-medium text-primary-foreground opacity-0 transition-opacity group-hover:opacity-100">
        {isDone ? "Làm lại" : "Bắt đầu"}
      </span>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-sans text-[0.7rem] font-normal uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="font-serif text-base font-normal tracking-tight text-foreground">{value}</span>
    </div>
  );
}

function ProgressSummary({ sets }: { sets: QuizSetSummaryV2[] }) {
  const done = sets.filter((set) => set.status.kind === "done").length;
  const totalCorrect = sets.reduce((acc, set) => (set.status.kind === "done" ? acc + set.status.correct_count : acc), 0);
  const totalAttempted = done * (sets[0]?.total_questions ?? 5);

  return (
    <div className="mb-10 flex flex-wrap gap-x-8 gap-y-2 rounded-xl border border-border bg-primary/[0.04] px-5 py-3.5">
      <Stat label="Bộ đề hoàn thành" value={`${done} / ${sets.length}`} />
      <div className="w-px self-stretch bg-border" />
      <Stat label="Tổng số câu đúng" value={totalAttempted > 0 ? `${totalCorrect} / ${totalAttempted}` : "—"} />
    </div>
  );
}

export default function QuizPage() {
  const [sets, setSets] = useState<QuizSetSummaryV2[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    loadSets();
  }, []);

  function loadSets(): void {
    setLoadError(false);
    setSets(null);
    getQuizSetsV2()
      .then(setSets)
      .catch(() => setLoadError(true));
  }

  return (
    <AuthenticatedLayout title="Trắc nghiệm">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6">
          <h1 className="mb-1.5 font-serif text-3xl font-light tracking-tight text-foreground">Trắc nghiệm</h1>
          <p className="text-sm font-light text-muted-foreground">
            {sets ? `Chọn 1 trong ${sets.length} bộ đề — mỗi bộ ${sets[0]?.total_questions ?? 5} câu` : "Đang tải danh sách bộ đề..."}
          </p>
        </div>

        {loadError ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Không tải được danh sách bộ đề.</span>
            <Button variant="outline" size="sm" onClick={loadSets}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {sets === null && !loadError ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {Array.from({ length: 10 }).map((_, index) => (
              <div key={index} className="h-24 animate-pulse rounded-xl border border-border bg-muted/60" />
            ))}
          </div>
        ) : null}

        {sets !== null ? (
          <>
            <ProgressSummary sets={sets} />

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {sets.map((set) => (
                <QuizSetCard key={set.quiz_set_id} set={set} />
              ))}
            </div>
          </>
        ) : null}

        <p className="mt-10 text-center text-xs text-muted-foreground/60">
          Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </p>
      </div>
    </AuthenticatedLayout>
  );
}
