import { cn } from "@/lib/utils";

interface ProgressBarProps {
  percentage: number;
  className?: string;
}

// Color communicates status per frontend.md: accent blue when healthy, amber mid-range,
// red below the 50% "needs review" threshold used across quiz and dashboard scoring.
function getProgressColor(percentage: number): string {
  if (percentage < 50) {
    return "bg-red-400";
  }

  if (percentage < 75) {
    return "bg-amber-400";
  }

  return "bg-primary";
}

export function ProgressBar({ percentage, className }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percentage));

  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}>
      <div
        className={cn("h-full rounded-full transition-all", getProgressColor(clamped))}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
