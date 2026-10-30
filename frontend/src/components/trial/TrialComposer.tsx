"use client";

import { ArrowRight, FileText, Info, Lock, Play, RotateCcw, Send, ShieldOff, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { ArticlePill } from "@/components/trial/ArticlePill";
import { ObserverControls } from "@/components/trial/ObserverControls";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  chairInvitation,
  composerMode,
  DECLINE_CONFIRM_MESSAGE,
  endSlotLabel,
  GUARD_EXHAUSTED_MESSAGE,
  isClerkRole,
  isDefendantRole,
  legalBasisArticle,
  parseAllowedActions,
  TRIAL_TEXT_DEFAULT_MAX,
  stepHint,
  textLimitsForState,
  usesObserverControls,
  validateTrialText
} from "@/lib/trialRules";
import type { TrialAttendanceEntry, TrialDeclineNote, TrialParticipant, TrialState, TrialStepInfo, TrialUtterance } from "@/lib/types";
import { cn } from "@/lib/utils";

export type ComposerAction =
  | { action: "speak"; text: string; addressee?: string }
  | { action: "end_slot" }
  | { action: "continue" }
  | { action: "decline" }
  | { action: "advance"; target_step: number }
  // Presiding judge (contract 5.4): no text = the item's template.
  | { action: "item" | "invite"; item: string; text?: string }
  | { action: "ask"; addressee: string; text: string }
  | { action: "remark"; text: string; addressee?: string }
  | { action: "return_to_questioning"; text?: string };

interface TrialComposerProps {
  // The session is completed but the record summary is still being written (final turn).
  recordPending?: boolean;
  sessionId: string;
  state: TrialState;
  userRole: string;
  steps: TrialStepInfo[];
  participants: Record<string, TrialParticipant>;
  // The transcript, for the presiding judge's invitation before a defendant's optional turn.
  utterances?: readonly TrialUtterance[];
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
  recordPending = false,
  sessionId,
  state,
  userRole,
  steps,
  participants,
  utterances = [],
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
  const limits = textLimitsForState(state, userRole);
  const [addressee, setAddressee] = useState<string>("");
  const [touched, setTouched] = useState(false);
  const textareaId = useId();
  const counterId = useId();
  const hintId = useId();

  // The chosen addressee, falling back to the first allowed one when the list changes.
  const chosenAddressee = actions.addressees?.includes(addressee) ? addressee : (actions.addressees?.[0] ?? "");

  const pendingSeq = state.pending_question?.seq ?? null;
  useEffect(() => {
    setTouched(false);
  }, [state.current_step, pendingSeq]);

  const hint = stepHint(state.current_step, userRole, mode === "speak");
  const nextStepTitle = actions.advanceTo !== null ? steps.find((step) => step.number === actions.advanceTo)?.title : undefined;

  // Observer (contract 5.1), and the clerk outside the step-1 report (5.2): no input at all; the
  // end-of-hearing bar and the guard fuse below are shared with the other roles.
  if (usesObserverControls(userRole, mode) && (busy || (mode !== "finished" && mode !== "exhausted"))) {
    return (
      <ObserverControls
        state={state}
        mode={mode}
        steps={steps}
        busy={busy}
        statusMessage={statusMessage}
        lastWasPause={lastWasPause}
        onAction={onAction}
      />
    );
  }

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

  // Finished: a one-line bar, not a card - it sits in the sticky dock and must not take a quarter of
  // the viewport away from the transcript.
  if (mode === "finished") {
    return state.status === "completed" ? (
      <div
        data-testid="trial-finished"
        role="status"
        className="flex min-h-12 flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-xl border border-primary/15 bg-card px-4 py-2 shadow-sm"
      >
        <p className="min-w-0 text-sm text-foreground">
          <span className="font-medium">Phiên tòa đã kết thúc.</span>
          {isClerkRole(userRole) ? <span className="ml-1 text-xs text-muted-foreground">Bạn viết mục IV.2, IV.3 và chốt biên bản.</span> : null}
          {recordPending ? (
            <span className="ml-1 text-xs text-muted-foreground">Biên bản đang được hoàn thiện; mở ngay thì mục tóm tắt có thể là nguyên văn.</span>
          ) : null}
        </p>
        <Button asChild size="sm" className="h-9 rounded-full">
          <Link href={`/trial/${sessionId}/record`}>
            <FileText className="h-4 w-4" />
            {isClerkRole(userRole) ? "Mở biên bản" : "Xem biên bản"}
          </Link>
        </Button>
      </div>
    ) : (
      <div data-testid="trial-abandoned" className="flex min-h-12 flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-muted/40 px-4 py-2 text-sm text-muted-foreground">
        <span>Phiên tòa này đã bị bỏ, chỉ xem lại được diễn biến.</span>
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
  // Clerk step-1 report (contract 5.2): the template is prefilled by the hearing screen; the
  // attendance list sits next to it for checking, and the template can be put back.
  const clerkReport = isClerkRole(userRole) ? (state.clerk_report ?? null) : null;
  // Defendant (contract 5.3): the question waiting for an answer, quoted from pending_question
  // (never looked up in the transcript); before the optional turns of steps 7-8, which have no
  // pending question, the presiding judge's invitation.
  const isDefendant = isDefendantRole(userRole);
  const pending = isDefendant ? (state.pending_question ?? null) : null;
  const invitation = isDefendant && pending === null ? chairInvitation(utterances, state.current_step) : null;
  const quoted = pending ?? invitation;
  const sendLabel = state.current_step === 6 || state.current_step === 7 || (isDefendant && state.current_step === 8)
    ? "Trình bày"
    : clerkReport !== null
      ? "Báo cáo"
      : isDefendant
        ? state.current_step === 9 ? "Nói lời sau cùng" : "Trả lời"
        : "Gửi";

  function decline(): void {
    if (window.confirm(DECLINE_CONFIRM_MESSAGE)) {
      onAction({ action: "decline" });
    }
  }

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
          {clerkReport !== null && clerkReport.attendance.length > 0 ? <AttendanceList entries={clerkReport.attendance} /> : null}
          {quoted !== null ? (
            <blockquote data-testid="trial-pending-question" className="rounded-lg border-l-4 border-primary/40 bg-muted/40 px-3 py-2 text-sm">
              <p className="mb-0.5 text-xs font-medium text-muted-foreground">
                {pending !== null ? "Câu hỏi đang chờ" : "Chủ tọa mời"} · {quoted.speaker_role}
                {quoted.speaker_name ? ` ${quoted.speaker_name}` : ""}
              </p>
              <p className="max-h-24 overflow-y-auto whitespace-pre-wrap break-words leading-relaxed text-foreground [@media(max-height:640px)]:max-h-12">{quoted.text}</p>
            </blockquote>
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
            {clerkReport !== null && draft !== clerkReport.prefill ? (
              <Button type="button" variant="outline" size="sm" data-testid="trial-clerk-refill" onClick={() => onDraftChange(clerkReport.prefill)}>
                <RotateCcw className="h-4 w-4" />
                Điền lại lời mẫu
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
                {endSlotLabel(state.current_step, userRole)}
              </Button>
            ) : null}
            {actions.canDecline ? (
              <Button type="button" variant="outline" size="sm" className="rounded-full" data-testid="trial-decline" onClick={decline}>
                <ShieldOff className="h-4 w-4" />
                Từ chối trả lời
              </Button>
            ) : null}
            <Button type="submit" size="sm" className="rounded-full" disabled={!canSend} data-testid="trial-send">
              <Send className="h-4 w-4" />
              {sendLabel}
            </Button>
          </div>
          {actions.canDecline && pending?.decline_note ? <DeclineNote note={pending.decline_note} /> : null}
          <p className="hidden text-right text-[0.7rem] text-muted-foreground md:block">Ctrl/⌘ + Enter để gửi</p>
        </form>
      ) : actions.canEndSlot ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-sm text-muted-foreground">Bạn đã dùng hết số lượt ở phần này.</p>
          <Button variant="outline" size="sm" className="rounded-full" data-testid="trial-end-slot" onClick={() => onAction({ action: "end_slot" })}>
            {endSlotLabel(state.current_step, userRole)}
          </Button>
        </div>
      ) : null}
    </Frame>
  );
}

// Why "Từ chối trả lời" exists (contract 5.3): the server's text and citations as sent, behind a
// small toggle so the dock stays short. A neutral explanation; no review badge.
function DeclineNote({ note }: { note: TrialDeclineNote }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <div className="flex flex-col items-end gap-1.5">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        data-testid="trial-decline-note-toggle"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-8 items-center gap-1 rounded-md px-1.5 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Info className="h-3.5 w-3.5" aria-hidden="true" />
        Quyền từ chối trả lời
      </button>
      {open ? (
        <div id={bodyId} data-testid="trial-decline-note" className="flex w-full flex-col gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2">
          <p className="max-h-28 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-foreground">{note.text}</p>
          {note.legal_basis.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Căn cứ:</span>
              {note.legal_basis.map((citation) => {
                const article = legalBasisArticle(citation);
                return article !== null ? (
                  <ArticlePill key={citation} dieu={article.dieu} lawVersion={article.lawVersion} label={citation} className="h-auto text-left" />
                ) : (
                  <span key={citation} className="text-xs text-foreground">
                    {citation}
                  </span>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// The summoned people per the case file, to check the report against (present: false = absent,
// with a request to be tried in absence).
function AttendanceList({ entries }: { entries: TrialAttendanceEntry[] }) {
  return (
    <div data-testid="trial-attendance" className="rounded-lg border border-border bg-muted/30 px-3 py-2">
      <p className="mb-1 text-xs font-medium text-foreground">Danh sách triệu tập theo hồ sơ</p>
      <ul className="grid max-h-28 grid-cols-1 gap-x-4 gap-y-0.5 overflow-y-auto text-xs sm:max-h-none sm:grid-cols-2 [@media(max-height:640px)]:max-h-16">
        {entries.map((entry) => (
          <li key={entry.speaker_id} className="flex min-w-0 items-baseline justify-between gap-2">
            <span className="min-w-0 break-words text-foreground">
              <span className="text-muted-foreground">{entry.role}:</span> {entry.name}
            </span>
            <span className={cn("shrink-0", entry.present ? "text-emerald-700" : "font-medium text-foreground")}>{entry.present ? "Có mặt" : "Vắng mặt"}</span>
          </li>
        ))}
      </ul>
    </div>
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
