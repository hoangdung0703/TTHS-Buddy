import { Check } from "lucide-react";

interface ProgressRingProps {
  correct: number;
  total: number;
  size?: number;
}

// Shared between /quiz's set-selection grid and the dashboard's Khối 1 "MCQ tổng hợp" hero ring
// (see requirements.md "Phase 7 v2") - do not fork a second copy for the dashboard.
export function ProgressRing({ correct, total, size = 36 }: ProgressRingProps) {
  const strokeWidth = size <= 48 ? 2.5 : 5;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = total > 0 ? (correct / total) * circumference : 0;
  const isComplete = total > 0 && correct === total;

  return (
    <div className="relative flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
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
        <Check className="absolute text-accent" style={{ width: size * 0.4, height: size * 0.4 }} strokeWidth={2.5} />
      ) : (
        <span className="absolute font-sans font-semibold text-primary" style={{ fontSize: size * 0.24 }}>
          {correct}/{total}
        </span>
      )}
    </div>
  );
}
