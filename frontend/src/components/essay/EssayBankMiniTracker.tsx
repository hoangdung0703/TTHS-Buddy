import Link from "next/link";

import { ESSAY_BANK_ACCENT, ESSAY_BANK_ICON } from "@/lib/essayBankPresentation";
import type { EssayBankV2 } from "@/lib/types";
import { cn } from "@/lib/utils";

interface EssayBankMiniTrackerProps {
  bank: EssayBankV2;
}

// Compact variant of /essay's EssayBankCard for the dashboard's Khối 2 (see requirements.md
// "Phase 7 v2") - same icon/accent language via lib/essayBankPresentation, but only shows the
// attempted-count progress bar (no %/score: essay answers are rubric-graded, not right/wrong,
// so a score-like number here would be misleading next to Khối 1's MCQ percentage).
export function EssayBankMiniTracker({ bank }: EssayBankMiniTrackerProps) {
  const Icon = ESSAY_BANK_ICON[bank.category];
  const accent = ESSAY_BANK_ACCENT[bank.category];
  const pct = bank.progress.kind !== "untouched" ? bank.progress.attempted_count / bank.total_questions : 0;
  const attempted = bank.progress.kind !== "untouched" ? bank.progress.attempted_count : 0;

  return (
    <Link
      href={`/essay/${bank.category}`}
      className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3 transition-colors hover:bg-primary/[0.03]"
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
            accent === "gold" ? "bg-accent/10 text-accent" : "bg-primary/[0.07] text-primary"
          )}
        >
          <Icon size={14} strokeWidth={1.6} />
        </span>
        <span className="truncate text-xs font-medium text-foreground">{bank.title}</span>
      </div>

      <div className="h-1.5 overflow-hidden rounded-full bg-primary/[0.08]">
        {pct > 0 && (
          <div
            className={cn("h-full rounded-full transition-all", accent === "gold" ? "bg-accent" : "bg-primary")}
            style={{ width: `${pct * 100}%` }}
          />
        )}
      </div>

      <span className="text-[0.7rem] text-muted-foreground">
        {attempted} / {bank.total_questions} câu
      </span>
    </Link>
  );
}
