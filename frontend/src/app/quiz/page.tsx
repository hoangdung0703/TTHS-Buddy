"use client";

// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
// Route này TẠM THỜI thay thế luồng Quiz Phase 5a gốc (5 bộ x 18 câu, backend thật đã chạy) bằng
// UI mock mới (15 bộ x 5 câu mcq_4choice thuần túy) theo thiết kế Figma mới của nhóm luật. Việc
// route khỏi backend thật là có chủ đích - PHẢI hoàn thành Bước 2 (backend thật) trước khi nhóm
// luật UAT, không được để UAT trên bản mock này.
import { Check } from "lucide-react";
import Link from "next/link";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { MOCK_QUIZ_SETS_V2, QUIZ_SET_V2_TOTAL_QUESTIONS } from "@/lib/mockDataV2";
import type { QuizSetSummaryV2 } from "@/lib/types";
import { cn } from "@/lib/utils";

function ProgressRing({ correct, total }: { correct: number; total: number }) {
  const size = 36;
  const strokeWidth = 2.5;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (correct / total) * circumference;
  const isComplete = correct === total;

  return (
    <div className="relative flex h-9 w-9 shrink-0 items-center justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsl(var(--primary) / 0.1)" strokeWidth={strokeWidth} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={isComplete ? "hsl(var(--accent))" : "hsl(var(--primary))"}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          className="transition-[stroke-dasharray] duration-300"
        />
      </svg>
      {isComplete ? (
        <Check className="absolute h-3.5 w-3.5 text-accent" strokeWidth={2.5} />
      ) : (
        <span className="absolute font-sans text-[9px] font-semibold text-primary">
          {correct}/{total}
        </span>
      )}
    </div>
  );
}

function QuizSetCard({ set }: { set: QuizSetSummaryV2 }) {
  const { status } = set;
  const isDone = status.kind === "done";
  const isInProgress = status.kind === "in_progress";
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
        {(isDone || isInProgress) && <ProgressRing correct={status.correct_count} total={set.total_questions} />}
      </div>

      <div className="min-h-[1.1rem] font-sans text-xs">
        {isDone && (
          <span className={status.correct_count === set.total_questions ? "text-accent" : "text-muted-foreground"}>
            {status.correct_count === set.total_questions
              ? `Hoàn thành · ${set.total_questions}/${set.total_questions} đúng`
              : `Đã hoàn thành · ${status.correct_count}/${set.total_questions} đúng`}
          </span>
        )}
        {isInProgress && <span className="text-primary">Đang làm · {status.correct_count}/{set.total_questions} đúng</span>}
        {status.kind === "untouched" && <span className="text-muted-foreground/60">Chưa làm</span>}
      </div>

      <span className="rounded-full bg-primary px-3 py-1 text-center font-sans text-xs font-medium text-primary-foreground opacity-0 transition-opacity group-hover:opacity-100">
        {isDone ? "Làm lại" : isInProgress ? "Tiếp tục" : "Bắt đầu"}
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
  const inProgress = sets.filter((set) => set.status.kind === "in_progress").length;
  const totalCorrect = sets.reduce((acc, set) => (set.status.kind !== "untouched" ? acc + set.status.correct_count : acc), 0);
  const totalAttempted = (done + inProgress) * QUIZ_SET_V2_TOTAL_QUESTIONS;

  return (
    <div className="mb-10 flex flex-wrap gap-x-8 gap-y-2 rounded-xl border border-border bg-primary/[0.04] px-5 py-3.5">
      <Stat label="Bộ đề hoàn thành" value={`${done} / ${sets.length}`} />
      <div className="w-px self-stretch bg-border" />
      <Stat label="Đang làm" value={String(inProgress)} />
      <div className="w-px self-stretch bg-border" />
      <Stat label="Tổng số câu đúng" value={totalAttempted > 0 ? `${totalCorrect} / ${totalAttempted}` : "—"} />
    </div>
  );
}

export default function QuizPage() {
  const sets = MOCK_QUIZ_SETS_V2;

  return (
    <AuthenticatedLayout title="Trắc nghiệm">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6">
          <h1 className="mb-1.5 font-serif text-3xl font-light tracking-tight text-foreground">Trắc nghiệm</h1>
          <p className="text-sm font-light text-muted-foreground">
            Chọn 1 trong {sets.length} bộ đề — mỗi bộ {QUIZ_SET_V2_TOTAL_QUESTIONS} câu
          </p>
        </div>

        <ProgressSummary sets={sets} />

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {sets.map((set) => (
            <QuizSetCard key={set.quiz_set_id} set={set} />
          ))}
        </div>

        <p className="mt-10 text-center text-xs text-muted-foreground/60">
          Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </p>
      </div>
    </AuthenticatedLayout>
  );
}
