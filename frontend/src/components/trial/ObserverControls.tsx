"use client";

import { ArrowRight, BookOpen, ChevronDown, Loader2, Lock, Play } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { ArticlePill } from "@/components/trial/ArticlePill";
import type { ComposerAction } from "@/components/trial/TrialComposer";
import { Button } from "@/components/ui/button";
import { LAW_VERSION_BLTTHS, parseAllowedActions, type ComposerMode } from "@/lib/trialRules";
import type { TrialProcedureNote, TrialState, TrialStepInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ObserverControlsProps {
  state: TrialState;
  mode: ComposerMode;
  steps: TrialStepInfo[];
  busy: boolean;
  statusMessage: string | null;
  lastWasPause: boolean;
  onAction: (action: ComposerAction) => void;
}

// The composer area of an observer session (contract 5.1): no input, only the procedure note of the
// current step and the one button state.allowed_actions offers ("advance:N" or "continue"). While a
// turn runs, the AI may speak for several to tens of seconds, so the area shows the server's status
// line and the elapsed time, and the button stays locked.
export function ObserverControls({ state, mode, steps, busy, statusMessage, lastWasPause, onAction }: ObserverControlsProps) {
  const actions = parseAllowedActions(state.allowed_actions);
  const nextStep = actions.advanceTo !== null ? steps.find((step) => step.number === actions.advanceTo) : undefined;
  // Steps whose note the reader collapsed. Every other step opens its note by default; kept here
  // (not in the card) so it survives the progress view of a running turn. Memory only.
  const [collapsedSteps, setCollapsedSteps] = useState<ReadonlySet<number>>(() => new Set());

  function toggleNote(step: number): void {
    setCollapsedSteps((current) => {
      const next = new Set(current);
      if (!next.delete(step)) {
        next.add(step);
      }
      return next;
    });
  }

  if (busy) {
    return <ObserverProgress statusMessage={statusMessage} />;
  }

  return (
    <div className="flex flex-col gap-2">
      {state.procedure_note ? (
        <ProcedureNoteCard
          note={state.procedure_note}
          open={!collapsedSteps.has(state.procedure_note.step)}
          onToggle={() => state.procedure_note && toggleNote(state.procedure_note.step)}
        />
      ) : null}
      {mode === "advance" && actions.advanceTo !== null ? (
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <p className="min-w-0 text-xs text-muted-foreground">
            Bước {state.current_step} đã xong.
            {nextStep ? ` Tiếp theo: ${nextStep.title}.` : ""}
          </p>
          <Button
            className="ml-auto rounded-full"
            data-testid="trial-advance"
            onClick={() => actions.advanceTo !== null && onAction({ action: "advance", target_step: actions.advanceTo })}
          >
            Sang bước tiếp theo
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      ) : mode === "paused" ? (
        <div data-testid="trial-paused" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <p className="min-w-0 flex-1 text-sm text-foreground">
            {lastWasPause
              ? "Hội đồng xét xử đang tạm nghỉ để kiểm tra lại nội dung. Bấm “Tiếp tục xem” khi bạn sẵn sàng."
              : "Phần trình bày bị gián đoạn (mất kết nối hoặc trang được tải lại). Bấm “Tiếp tục xem” để xem tiếp."}
          </p>
          <Button size="sm" className="rounded-full" data-testid="trial-continue" onClick={() => onAction({ action: "continue" })}>
            <Play className="h-4 w-4" />
            Tiếp tục xem
          </Button>
        </div>
      ) : (
        <div role="status" data-testid="trial-composer-locked" className="flex items-center gap-3 rounded-xl border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Đang chờ máy chủ cập nhật lượt.</span>
        </div>
      )}
    </div>
  );
}

function ObserverProgress({ statusMessage }: { statusMessage: string | null }) {
  const [elapsed, setElapsed] = useState(0);

  // Mounted only while a turn runs, so the count starts at 0 for every turn.
  useEffect(() => {
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex flex-col gap-2">
      <div role="status" aria-live="polite" data-testid="trial-observer-progress" className="flex flex-col gap-2 rounded-xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-foreground">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="min-w-0 flex-1">{statusMessage ?? "Đang chuẩn bị phần tiếp theo..."}</span>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground" aria-label={`Đã chờ ${elapsed} giây`}>
            {elapsed}s
          </span>
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/60" />
        </div>
        <p className="text-xs text-muted-foreground">Các vai đang trình bày. Phần dài như luận tội, đối đáp hay tuyên án có thể mất vài chục giây.</p>
      </div>
      <Button className="ml-auto rounded-full" disabled data-testid="trial-observer-busy-button">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        Đang diễn ra...
      </Button>
    </div>
  );
}

// Static explanation of the step (not AI-generated). A draft not yet reviewed by the legal team
// carries a small label.
function ProcedureNoteCard({ note, open, onToggle }: { note: TrialProcedureNote; open: boolean; onToggle: () => void }) {
  const bodyId = useId();

  return (
    <section data-testid="trial-procedure-note" aria-label="Chú giải thủ tục" className="rounded-xl border border-primary/15 bg-card">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={onToggle}
        className="flex min-h-11 w-full items-center gap-2 rounded-xl px-4 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <BookOpen className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 flex-1 text-sm font-medium text-foreground">
          Chú giải thủ tục
          <span className="font-normal text-muted-foreground"> · Bước {note.step}: {note.title}</span>
        </span>
        {note.reviewed ? null : (
          <span data-testid="trial-procedure-draft" className="hidden shrink-0 rounded-full border border-border bg-secondary px-2 py-0.5 text-[0.7rem] font-medium text-secondary-foreground sm:inline">
            Bản nháp, đang chờ nhóm luật duyệt
          </span>
        )}
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden="true" />
      </button>
      {open ? (
        <div id={bodyId} data-testid="trial-procedure-note-body" className="flex max-h-[35vh] flex-col gap-2 overflow-y-auto px-4 pb-3">
          {note.reviewed ? null : (
            <span className="self-start rounded-full border border-border bg-secondary px-2 py-0.5 text-[0.7rem] font-medium text-secondary-foreground sm:hidden">
              Bản nháp, đang chờ nhóm luật duyệt
            </span>
          )}
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">{note.text}</p>
          {note.legal_basis.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Căn cứ BLTTHS:</span>
              {note.legal_basis.map((dieu) => (
                <ArticlePill key={dieu} dieu={dieu} lawVersion={LAW_VERSION_BLTTHS} label={`Điều ${dieu}`} />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
