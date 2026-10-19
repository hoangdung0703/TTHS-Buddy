"use client";

import { Check } from "lucide-react";

import type { TrialStepInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

// 11-step progress (THIET-KE Mục 7, màn 3). Titles and legal bases come from the server's `steps`.
// Desktop: one numbered marker per step, title + BLTTHS articles on hover/focus. Below md: a
// one-line "Bước x/11 · title" with a thin bar.
export function StepBar({ steps, currentStep, completed }: { steps: TrialStepInfo[]; currentStep: number; completed: boolean }) {
  const total = steps.length;
  const current = steps.find((step) => step.number === currentStep);
  const doneCount = completed ? total : Math.max(0, currentStep - 1);

  return (
    <nav aria-label="Tiến trình phiên tòa" className="min-w-0">
      <div className="md:hidden">
        <p className="text-sm font-medium text-foreground">
          Bước {currentStep}/{total}
          {current ? ` · ${current.title}` : ""}
        </p>
        <div
          className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={completed ? total : currentStep}
          aria-label="Tiến độ phiên tòa"
        >
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${((completed ? total : currentStep) / total) * 100}%` }} />
        </div>
      </div>

      <ol className="hidden items-start md:flex">
        {steps.map((step, index) => {
          const isDone = step.number <= doneCount;
          const isCurrent = !completed && step.number === currentStep;
          const basis = step.legal_basis.length > 0 ? `Điều ${step.legal_basis.join(", ")} BLTTHS` : "";
          const tooltip = `${step.number}. ${step.title}${basis ? ` (${basis})` : ""}`;
          return (
            <li key={step.number} className="group relative flex min-w-0 flex-1 flex-col items-center" aria-current={isCurrent ? "step" : undefined}>
              {index > 0 ? (
                <span
                  aria-hidden="true"
                  className={cn("absolute right-1/2 top-3.5 h-px w-full", step.number <= doneCount + 1 ? "bg-primary/50" : "bg-border")}
                />
              ) : null}
              <span
                tabIndex={0}
                aria-label={`${tooltip}${isDone ? ", đã xong" : isCurrent ? ", đang diễn ra" : ", chưa tới"}`}
                className={cn(
                  "relative z-10 flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isDone && "border-primary bg-primary/10 text-primary",
                  isCurrent && "border-primary bg-primary text-primary-foreground",
                  !isDone && !isCurrent && "border-border bg-card text-muted-foreground opacity-60"
                )}
              >
                {isDone ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : step.number}
              </span>
              <span
                className={cn(
                  "mt-1.5 line-clamp-2 px-0.5 text-center text-[0.65rem] leading-tight",
                  isCurrent ? "font-medium text-foreground" : "text-muted-foreground",
                  !isCurrent && "hidden xl:block"
                )}
              >
                {step.title}
              </span>
              <span
                role="tooltip"
                className={cn(
                  "pointer-events-none absolute top-9 z-30 hidden w-56 rounded-md border border-border bg-popover px-3 py-2 text-left text-xs text-popover-foreground shadow-md group-focus-within:block group-hover:block",
                  index < 2 ? "left-0" : index >= total - 2 ? "right-0" : "left-1/2 -translate-x-1/2"
                )}
              >
                <span className="block font-medium">
                  {step.number}. {step.title}
                </span>
                {basis ? <span className="mt-0.5 block text-muted-foreground">Căn cứ: {basis}</span> : null}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
