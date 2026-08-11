"use client";

import { useMemo, useState } from "react";

import type { EssayBankQuestionListItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type Filter = "all" | "not_done" | "needs_review";

interface EssayQuestionGridProps {
  questions: EssayBankQuestionListItem[];
  onSelect: (order: number) => void;
}

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tất cả" },
  { key: "not_done", label: "Chưa làm" },
  { key: "needs_review", label: "Cần ôn lại" },
];

// 3-state grid tile - navy đặc (done), amber tint (needs_review), viền navy nhạt/nền trắng
// (not_done). Cùng token đã audit WCAG AA đang dùng ở nơi khác trong app (bg-primary,
// amber-100/amber-800 - xem badge.tsx variant="warning", EssayBankRunner missing_points list).
function statusClasses(status: EssayBankQuestionListItem["status"]): string {
  switch (status) {
    case "done":
      return "border-transparent bg-primary text-primary-foreground hover:opacity-90";
    case "needs_review":
      return "border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200/70";
    case "not_done":
    default:
      return "border-primary/15 bg-card text-foreground hover:border-primary/30 hover:bg-primary/[0.03]";
  }
}

export function EssayQuestionGrid({ questions, onSelect }: EssayQuestionGridProps) {
  const [filter, setFilter] = useState<Filter>("all");

  const counts = useMemo(
    () => ({
      all: questions.length,
      not_done: questions.filter((q) => q.status === "not_done").length,
      needs_review: questions.filter((q) => q.status === "needs_review").length,
    }),
    [questions]
  );

  const visible = useMemo(
    () => (filter === "all" ? questions : questions.filter((q) => q.status === filter)),
    [questions, filter]
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={cn(
              "min-h-11 rounded-full border px-4 text-sm font-medium transition-colors",
              filter === key
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-card text-foreground hover:border-primary/30"
            )}
          >
            {label} ({counts[key]})
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-primary" /> Đã hoàn thành
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full border border-amber-300 bg-amber-100" /> Cần ôn lại
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full border border-primary/15 bg-card" /> Chưa làm
        </span>
      </div>

      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">Không có câu hỏi nào ở bộ lọc này.</p>
      ) : (
        <div className="grid grid-cols-5 gap-2.5 sm:grid-cols-6 md:grid-cols-8">
          {visible.map((question) => (
            <button
              key={question.question_id}
              type="button"
              onClick={() => onSelect(question.order)}
              aria-label={`Câu ${question.order}`}
              className={cn(
                "flex min-h-11 min-w-11 items-center justify-center rounded-xl border text-sm font-medium shadow-sm transition-colors",
                statusClasses(question.status)
              )}
            >
              {question.order}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
