"use client";

import { ArrowRight, FileText, Lock, Play, Send, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  composerMode,
  endSlotLabel,
  GUARD_EXHAUSTED_MESSAGE,
  parseAllowedActions,
  TRIAL_TEXT_DEFAULT_MAX,
  stepHint,
  textLimitsForState,
  validateTrialText
} from "@/lib/trialRules";
import type { TrialParticipant, TrialState, TrialStepInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

export type ComposerAction =
  | { action: "speak"; text: string; addressee?: string }
  | { action: "end_slot" }
  | { action: "continue" }
  | { action: "advance"; target_step: number };

interface TrialComposerProps {
  sessionId: string;
  state: TrialState;
  userRole: string;
  steps: TrialStepInfo[];
  participants: Record<string, TrialParticipant>;
  // A stream is running: the composer is locked whatever the state says.
  busy: boolean;
  statusMessage: string | null;
  // True when the last utterance is a guard-pause notice, to word the "Tiếp tục" box.
  lastWasPause: boolean;
  indictmentText: string | null;
  draft: string;
  onDraftChange: (value: string) => void;
  onAction: (action: ComposerAction) => void;
  onAbandon: () => void;
  onDelete: () => void;
}

// Every control here comes from state.allowed_actions (contract Mục 9.3): nothing is inferred.
export function TrialComposer({
  sessionId,
  state,
  userRole,
  steps,
  participants,
  busy,
  statusMessage,
  lastWasPause,
  indictmentText,
  draft,
  onDraftChange,
  onAction,
  onAbandon,
  onDelete
}: TrialComposerProps) {
  const mode = composerMode(state);
  const actions = parseAllowedActions(state.allowed_actions);
  const limits = textLimitsForState(state);
  const [addressee, setAddressee] = useState<string>("");
  const [touched, setTouched] = useState(false);
  const textareaId = useId();
  const counterId = useId();
  const hintId = useId();

  // The chosen addressee, falling back to the first allowed one when the list changes.
  const chosenAddressee = actions.addressees?.includes(addressee) ? addressee : (actions.addressees?.[0] ?? "");

  useEffect(() => {
    setTouched(false);
  }, [state.current_step]);

  const hint = stepHint(state.current_step, userRole, mode === "speak");
  const nextStepTitle = actions.advanceTo !== null ? steps.find((step) => step.number === actions.advanceTo)?.title : undefined;

  if (busy || mode === "waiting") {
    return (
      <Frame hint={hint} hintId={hintId}>
        <div role="status" aria-live="polite" data-testid="trial-composer-locked" className="flex items-center gap-3 rounded-xl border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            {busy ? "Lượt của các vai khác. Bạn chờ trong giây lát." : "Đang chờ máy chủ cập nhật lượt."}
            {busy && statusMessage ? <span className="block text-xs">{statusMessage}</span> : null}
          </span>
          {busy ? (
            <span className="flex gap-1" aria-hidden="true">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
            </span>
          ) : null}
        </div>
      </Frame>
    );
  }

  if (mode === "finished") {
    return state.status === "completed" ? (
      <div data-testid="trial-finished" className="flex flex-col items-center gap-3 rounded-xl border border-primary/15 bg-card px-5 py-6 text-center shadow-sm">
        <p className="font-serif text-xl font-light text-foreground">Phiên tòa kết thúc</p>
        <p className="max-w-md text-sm text-muted-foreground">Bạn có thể xem lại toàn bộ diễn biến ở trên hoặc mở biên bản phiên tòa để in và lưu.</p>
        <Button asChild className="rounded-full">
          <Link href={`/trial/${sessionId}/record`}>
            <FileText className="h-4 w-4" />
            Xem biên bản
          </Link>
        </Button>
      </div>
    ) : (
      <div data-testid="trial-abandoned" className="rounded-xl border border-border bg-muted/40 px-5 py-4 text-center text-sm text-muted-foreground">
        Phiên tòa này đã bị bỏ. Bạn chỉ có thể xem lại diễn biến.{" "}
        <Link href="/trial" className="font-medium text-primary underline-offset-2 hover:underline">
          Về danh sách
        </Link>
      </div>
    );
  }

  if (mode === "exhausted") {
    return (
      <Frame hint={hint} hintId={hintId}>
        <div role="alert" data-testid="trial-guard-exhausted" className="flex flex-col gap-3 rounded-xl border border-border bg-card px-4 py-4">
          <p className="text-sm text-foreground">{GUARD_EXHAUSTED_MESSAGE}</p>
          <p className="text-xs text-muted-foreground">
            AI đã tạm nghỉ nhiều lần liên tiếp ở cùng một chỗ vì chưa tạo được lời thoại đúng hồ sơ và quy định. Bấm “Bỏ phiên” để
            giữ lại diễn biến đã có, hoặc “Xóa phiên” để xóa hẳn; sau đó tạo vụ án mới.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={onAbandon}>
              <XCircle className="h-4 w-4" />
              Bỏ phiên
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete} className="hover:bg-red-100 hover:text-red-700">
              <Trash2 className="h-4 w-4" />
              Xóa phiên
            </Button>
          </div>
        </div>
      </Frame>
    );
  }

  if (mode === "paused") {
    return (
      <Frame hint={hint} hintId={hintId}>
        <div data-testid="trial-paused" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <p className="min-w-0 flex-1 text-sm text-foreground">
            {lastWasPause
              ? "Hội đồng xét xử đang tạm nghỉ để kiểm tra lại nội dung. Bấm “Tiếp tục” khi bạn sẵn sàng."
              : "Lượt trình bày của AI bị gián đoạn (mất kết nối hoặc trang được tải lại). Bấm “Tiếp tục” để AI làm tiếp."}
          </p>
          <Button size="sm" className="rounded-full" onClick={() => onAction({ action: "continue" })}>
            <Play className="h-4 w-4" />
            Tiếp tục
          </Button>
        </div>
      </Frame>
    );
  }

  if (mode === "advance") {
    return (
      <Frame hint={`Bước ${state.current_step} đã xong.${nextStepTitle ? ` Tiếp theo: ${nextStepTitle}.` : ""}`} hintId={hintId}>
        <div className="flex justify-end">
          <Button className="rounded-full" data-testid="trial-advance" onClick={() => actions.advanceTo !== null && onAction({ action: "advance", target_step: actions.advanceTo })}>
            Sang bước tiếp theo
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </Frame>
    );
  }

  // mode === "speak"
  const validation = validateTrialText(draft, limits);
  const needsAddressee = actions.addressees !== null;
  const canSend = actions.canSpeak && validation === null && (!needsAddressee || chosenAddressee !== "");
  const isLong = limits.max > TRIAL_TEXT_DEFAULT_MAX;
  const length = draft.length;
  const overMax = length > limits.max;
  const trimmedLength = draft.trim().length;
  const belowMin = limits.min > 1 && trimmedLength < limits.min;
  const showIndictmentFill = state.current_step === 3 && userRole === "ksv" && indictmentText !== null && indictmentText.length > 0;

  function submit(): void {
    setTouched(true);
    if (!canSend) {
      return;
    }
    onAction(needsAddressee ? { action: "speak", text: draft, addressee: chosenAddressee } : { action: "speak", text: draft });
  }

  return (
    <Frame hint={hint} hintId={hintId}>
      {actions.canSpeak ? (
        <form
          data-testid="trial-composer"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
          className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3"
        >
          {needsAddressee ? (
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor={`${textareaId}-addressee`} className="text-sm font-medium text-foreground">
                Hỏi:
              </label>
              <select
                id={`${textareaId}-addressee`}
                value={chosenAddressee}
                onChange={(event) => setAddressee(event.target.value)}
                className="min-h-11 min-w-0 max-w-full flex-1 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:border-ring focus:outline-none sm:flex-none"
              >
                {actions.addressees?.map((id) => (
                  <option key={id} value={id}>
                    {participants[id] ? `${participants[id].role} · ${participants[id].name}` : id}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <label htmlFor={textareaId} className="sr-only">
            {limits.label}
          </label>
          <Textarea
            id={textareaId}
            data-testid="trial-input"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              // Ctrl/Cmd+Enter sends; plain Enter is a newline (long speeches need paragraphs).
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
            aria-describedby={`${counterId} ${hintId}`}
            aria-invalid={touched && validation !== null}
            placeholder={needsAddressee ? "Nhập câu hỏi..." : `${limits.label}...`}
            className={cn(
              "resize-y text-sm leading-relaxed [@media(max-height:640px)]:min-h-[64px]",
              isLong ? "min-h-[120px] sm:min-h-[180px]" : "min-h-[72px] sm:min-h-[88px]"
            )}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p
              id={counterId}
              data-testid="trial-counter"
              className={cn("text-xs tabular-nums", overMax ? "font-medium text-red-600" : limits.min > 1 && !belowMin ? "text-emerald-700" : "text-muted-foreground")}
            >
              {length.toLocaleString("vi-VN")}/{limits.max.toLocaleString("vi-VN")} ký tự
              {limits.min > 1 ? ` · tối thiểu ${limits.min.toLocaleString("vi-VN")}` : ""}
            </p>
            {showIndictmentFill ? (
              <Button type="button" variant="outline" size="sm" onClick={() => onDraftChange(indictmentText ?? "")}>
                <FileText className="h-4 w-4" />
                Điền sẵn cáo trạng từ hồ sơ
              </Button>
            ) : null}
          </div>
          {/* An empty box only disables "Gửi"; the message appears once there is text to judge. */}
          {((touched && length > 0) || overMax) && validation !== null ? (
            <p role="alert" data-testid="trial-validation" className="text-xs text-red-600">
              {validation}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center justify-end gap-2">
            {actions.canEndSlot ? (
              <Button type="button" variant="outline" size="sm" className="rounded-full" data-testid="trial-end-slot" onClick={() => onAction({ action: "end_slot" })}>
                {endSlotLabel(state.current_step)}
              </Button>
            ) : null}
            <Button type="submit" size="sm" className="rounded-full" disabled={!canSend} data-testid="trial-send">
              <Send className="h-4 w-4" />
              {state.current_step === 6 || state.current_step === 7 ? "Trình bày" : "Gửi"}
            </Button>
          </div>
          <p className="hidden text-right text-[0.7rem] text-muted-foreground md:block">Ctrl/⌘ + Enter để gửi</p>
        </form>
      ) : actions.canEndSlot ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-sm text-muted-foreground">Bạn đã dùng hết số lượt ở phần này.</p>
          <Button variant="outline" size="sm" className="rounded-full" data-testid="trial-end-slot" onClick={() => onAction({ action: "end_slot" })}>
            {endSlotLabel(state.current_step)}
          </Button>
        </div>
      ) : null}
    </Frame>
  );
}

function Frame({ hint, hintId, children }: { hint: string; hintId: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      {hint ? (
        <p id={hintId} data-testid="trial-step-hint" className="text-xs leading-relaxed text-muted-foreground [@media(max-height:640px)]:sr-only">
          {hint}
        </p>
      ) : null}
      {children}
    </div>
  );
}
