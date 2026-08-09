import { CheckCircle2, XCircle } from "lucide-react";

import type { ChatStreamGradingEvent } from "@/lib/types";

// Reuses the exact matched/missing visual language already built (and WCAG AA contrast-audited -
// see EssayBankRunner.tsx / commit 69f1454) for the Essay module: emerald-600 for matched,
// amber-700 (not amber-600) for missing, icon + plain text rows rather than a filled badge.
// Deliberately no score/percentage anywhere - "Sinh tình huống minh họa" Lượt 2's core philosophy
// (chữa bài, không chấm điểm), same as Essay grading already has no score field either.
interface ScenarioGradingResultProps {
  result: ChatStreamGradingEvent;
}

export function ScenarioGradingResult({ result }: ScenarioGradingResultProps) {
  const missingToShow = result.missing_points_display ?? result.missing_points;

  return (
    <div className="mt-3 space-y-3 border-t border-border pt-3">
      <div>
        <p className="mb-1.5 text-xs font-semibold text-muted-foreground">Ý đã có</p>
        {result.matched_points.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có ý nào khớp với tình huống.</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {result.matched_points.map((point) => (
              <li key={point} className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                {point}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-muted-foreground">Ý còn thiếu</p>
        {missingToShow.length === 0 ? (
          <p className="text-sm text-muted-foreground">Không thiếu ý nào.</p>
        ) : (
          <ul className="space-y-1.5 text-sm">
            {missingToShow.map((point) => (
              <li key={point} className="flex items-start gap-2">
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                {point}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
