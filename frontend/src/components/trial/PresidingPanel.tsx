"use client";

import { ArrowRight, CheckCircle2, Circle, CircleDashed, Gavel, ListChecks, MessageSquareText, PenLine, RotateCcw, Send, Sparkles } from "lucide-react";
import { forwardRef, useEffect, useId, useRef, useState } from "react";

import { ArticlePill } from "@/components/trial/ArticlePill";
import type { ComposerAction } from "@/components/trial/TrialComposer";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  askAddresseesForItem,
  CHAIR_RETURN_CONFIRM_MESSAGE,
  chairItemActionable,
  chairItemLabel,
  chairOneClickTemplate,
  chairStepHint,
  chairTargetItem,
  chairTargetOptions,
  chairTextLimits,
  LAW_VERSION_BLTTHS,
  parseChairActions,
  resolveChairTarget,
  validateChairText,
  type ChairActions,
  type ChairTarget
} from "@/lib/trialRules";
import type { TrialParticipant, TrialPresiding, TrialPresidingItem, TrialState, TrialStepInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

// Templates up to this length are shown in full in the checklist; longer ones are clamped with a toggle.
const TEMPLATE_PREVIEW_CHARS = 220;
const FLASH_MS = 2600;

// A request to point at missing required items: `nonce` changes on every press so the same keys
// flash again.
export interface ChairMissingFlash {
  keys: string[];
  nonce: number;
}

const participantLabel = (participants: Record<string, TrialParticipant>, id: string) =>
  participants[id] ? `${participants[id].role} · ${participants[id].name}` : id;

// --- Checklist ("Điều hành") -----------------------------------------------------------------------

interface PresidingChecklistProps {
  presiding: TrialPresiding;
  allowedActions: readonly string[];
  busy: boolean;
  flash: ChairMissingFlash | null;
  onAction: (action: ComposerAction) => void;
  // "Tự soạn": put this item in the composer (template prefilled for editing).
  onCompose: (item: TrialPresidingItem) => void;
}

// The step's checklist (contract 5.4), read from state.presiding only: what is done, required or
// available is never worked out here. "Dùng lời mẫu" sends in one click; the template is previewed.
export function PresidingChecklist({ presiding, allowedActions, busy, flash, onAction, onCompose }: PresidingChecklistProps) {
  const actions = parseChairActions(allowedActions);
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const [flashing, setFlashing] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(() => {
    if (flash === null || flash.keys.length === 0) {
      return;
    }
    setFlashing(new Set(flash.keys));
    const first = flash.keys.map((key) => rowRefs.current.get(key)).find((row) => row !== undefined && row.offsetParent !== null);
    first?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const timer = setTimeout(() => setFlashing(new Set()), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flash]);

  const requiredTotal = presiding.items.filter((item) => item.required).length;
  const requiredDone = presiding.items.filter((item) => item.required && item.done).length;
  const { questions_left: questionsLeft, remarks_left: remarksLeft } = presiding.counters;
  const questioning = presiding.step === 4 || presiding.in_return;

  return (
    <div data-testid="chair-checklist" className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-xs text-muted-foreground" data-testid="chair-progress">
          Bắt buộc: {requiredDone}/{requiredTotal} mục
        </p>
        <p className="text-xs text-muted-foreground" data-testid="chair-counters">
          {questioning ? `Còn ${questionsLeft} câu hỏi · ` : ""}Còn {remarksLeft} lần phát biểu khác
        </p>
      </div>
      {presiding.in_return ? (
        <p data-testid="chair-in-return" className="rounded-lg border border-primary/20 bg-primary/[0.04] px-3 py-2 text-xs text-foreground">
          Đang trở lại xét hỏi (Điều 323 BLTTHS). Kết thúc xét hỏi để về lại bước 8 và đối đáp lại ít nhất một vòng.
        </p>
      ) : null}
      {presiding.step === 8 && presiding.returned && !presiding.in_return ? (
        <p data-testid="chair-return-used" className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          Phiên này đã dùng lượt trở lại xét hỏi duy nhất (Điều 323 BLTTHS).
        </p>
      ) : null}
      <ol className="-mr-1 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {presiding.items.map((item) => (
          <ChecklistRow
            key={`${item.kind}:${item.key}`}
            ref={(row) => {
              if (row) {
                rowRefs.current.set(item.key, row);
              } else {
                rowRefs.current.delete(item.key);
              }
            }}
            item={item}
            actions={actions}
            busy={busy}
            flashing={flashing.has(item.key)}
            onAction={onAction}
            onCompose={onCompose}
          />
        ))}
      </ol>
    </div>
  );
}

interface ChecklistRowProps {
  item: TrialPresidingItem;
  actions: ChairActions;
  busy: boolean;
  flashing: boolean;
  onAction: (action: ComposerAction) => void;
  onCompose: (item: TrialPresidingItem) => void;
}

const ChecklistRow = forwardRef<HTMLLIElement, ChecklistRowProps>(function ChecklistRow({ item, actions, busy, flashing, onAction, onCompose }, ref) {
  const actionable = chairItemActionable(item, actions);
  const oneClick = chairOneClickTemplate(item, actions);
  const enabled = actionable && !busy;
  const isAsk = item.kind === "ask";

  function sendTemplate(): void {
    if (!oneClick || item.template === null) {
      return;
    }
    if (item.kind === "ask") {
      onAction({ action: "ask", addressee: askAddresseesForItem(item.key, actions.askTo)[0], text: item.template });
    } else if (item.kind === "item" || item.kind === "invite") {
      onAction({ action: item.kind, item: item.key });
    }
  }

  function returnToQuestioning(): void {
    if (window.confirm(CHAIR_RETURN_CONFIRM_MESSAGE)) {
      onAction({ action: "return_to_questioning" });
    }
  }

  const StatusIcon = item.done ? CheckCircle2 : item.required ? Circle : CircleDashed;
  const status = item.done ? (isAsk ? "Đã hỏi" : "Đã làm") : actionable ? "" : "Chưa làm được lúc này";

  return (
    <li
      ref={ref}
      data-testid={`chair-item-${item.key}`}
      data-done={item.done || undefined}
      data-required={item.required || undefined}
      data-flash={flashing || undefined}
      className={cn(
        "rounded-lg border px-3 py-2.5 transition-colors",
        item.done ? "border-border bg-muted/30" : "border-border bg-card",
        flashing && "animate-pulse border-primary ring-2 ring-primary/50"
      )}
    >
      <div className="flex items-start gap-2">
        <StatusIcon className={cn("mt-0.5 h-4 w-4 shrink-0", item.done ? "text-primary" : item.required ? "text-foreground" : "text-muted-foreground")} aria-hidden="true" />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <p className={cn("min-w-0 break-words text-sm", item.done ? "text-muted-foreground" : "font-medium text-foreground")}>{item.label}</p>
            <span className={cn("shrink-0 rounded-full px-1.5 py-px text-[0.65rem] font-medium", item.required ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
              {item.required ? "Bắt buộc" : "Tùy chọn"}
            </span>
            {status ? <span className="shrink-0 text-[0.7rem] text-muted-foreground">{status}</span> : null}
          </div>
          {item.template && !item.done && item.kind !== "return" ? <TemplatePreview text={item.template} /> : null}
          {item.kind === "return" ? (
            <p className="text-xs leading-relaxed text-muted-foreground">
              Một lần mỗi phiên{actionable ? " · còn lượt" : ""}. Phiên về bước 5 thu gọn (hỏi tối đa 3 câu), kết thúc xét hỏi rồi về lại bước 8 và đối đáp lại.
            </p>
          ) : null}
          {item.note ? (
            <p data-testid="chair-item-note" className="text-[0.7rem] italic leading-relaxed text-muted-foreground">
              {item.note}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-1.5">
            {item.basis.map((dieu) => (
              <ArticlePill key={dieu} dieu={dieu} lawVersion={LAW_VERSION_BLTTHS} label={`Điều ${dieu}`} className="min-h-7 px-2 text-[0.7rem] font-normal" />
            ))}
            {actionable ? (
              <span className="ml-auto flex flex-wrap justify-end gap-1.5">
                {item.kind === "return" ? (
                  <Button size="sm" variant="outline" className="h-8 rounded-full" disabled={!enabled} data-testid="chair-return" onClick={returnToQuestioning}>
                    <RotateCcw className="h-3.5 w-3.5" />
                    Trở lại xét hỏi
                  </Button>
                ) : (
                  <>
                    <Button size="sm" variant="ghost" className="h-8 rounded-full px-2.5" disabled={!enabled} data-testid="chair-compose" onClick={() => onCompose(item)}>
                      <PenLine className="h-3.5 w-3.5" />
                      {isAsk ? "Soạn câu hỏi" : "Tự soạn"}
                    </Button>
                    {oneClick ? (
                      <Button size="sm" className="h-8 rounded-full" disabled={!enabled} data-testid="chair-use-template" onClick={sendTemplate}>
                        <Sparkles className="h-3.5 w-3.5" />
                        Dùng lời mẫu
                      </Button>
                    ) : null}
                  </>
                )}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </li>
  );
});

// "Lời mẫu gợi ý": neutral wording, no review badge (contract 5.4, templates_reviewed).
function TemplatePreview({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > TEMPLATE_PREVIEW_CHARS;
  return (
    <div data-testid="chair-template" className="rounded-md bg-muted/40 px-2.5 py-1.5 text-xs leading-relaxed text-foreground/90">
      <span className="font-medium text-muted-foreground">Lời mẫu gợi ý: </span>
      <span className={cn("whitespace-pre-wrap break-words", long && !open && "line-clamp-2")}>{text}</span>
      {long ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="mt-0.5 block text-[0.7rem] font-medium text-primary underline-offset-2 hover:underline"
        >
          {open ? "Thu gọn" : "Xem đủ"}
        </button>
      ) : null}
    </div>
  );
}

// --- Composer dock ---------------------------------------------------------------------------------

interface PresidingComposerProps {
  state: TrialState;
  presiding: TrialPresiding;
  steps: TrialStepInfo[];
  participants: Record<string, TrialParticipant>;
  busy: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  target: ChairTarget;
  onTargetChange: (target: ChairTarget) => void;
  // Addressee picked for a question or a remark ("" = nobody in particular, remark only).
  addressee: string;
  onAddresseeChange: (id: string) => void;
  missing: string[] | null;
  onAction: (action: ComposerAction) => void;
  // Phones: open the checklist drawer.
  onOpenChecklist: () => void;
  // "Sang bước tiếp theo" while required items remain: point at them (no request is sent).
  onShowMissing: () => void;
}

// The presiding judge's dock: one composer for the chosen action (an item in their own words, a
// question, a "phát biểu khác", the Điều 323 return) and the step button. The server decides
// everything; an action that is not in allowed_actions is not offered.
export const PresidingComposer = forwardRef<HTMLTextAreaElement, PresidingComposerProps>(function PresidingComposer(
  { state, presiding, steps, participants, busy, draft, onDraftChange, target, onTargetChange, addressee, onAddresseeChange, missing, onAction, onOpenChecklist, onShowMissing },
  textareaRef
) {
  const actions = parseChairActions(state.allowed_actions);
  const options = chairTargetOptions(presiding, actions);
  const chosen = resolveChairTarget(target, presiding, options);
  const [touched, setTouched] = useState(false);
  const selectId = useId();
  const textareaId = useId();
  const counterId = useId();
  const hintId = useId();

  useEffect(() => {
    setTouched(false);
  }, [state.current_step, chosen]);

  const requiredLeft = presiding.missing_required.length;
  const hint = chairStepHint(state.current_step, presiding);
  const nextTitle = actions.advanceTo !== null ? steps.find((step) => step.number === actions.advanceTo)?.title : undefined;
  const advanceLabel = presiding.in_return ? "Về lại bước 8" : "Sang bước tiếp theo";

  const limits = chosen !== null ? chairTextLimits(chosen, presiding) : null;
  const item = chosen !== null ? chairTargetItem(chosen, presiding) : null;
  const askTo = chosen === "ask" ? actions.askTo : [];
  const remarkTo = chosen === "remark" ? presiding.remark_addressees : [];
  const chosenAsk = askTo.includes(addressee) ? addressee : (askTo[0] ?? "");
  const chosenRemark = remarkTo.includes(addressee) ? addressee : "";
  const validation = limits !== null ? validateChairText(draft, limits) : null;
  const canSend = !busy && chosen !== null && validation === null && (chosen !== "ask" || chosenAsk !== "");
  const length = draft.length;
  const overMax = limits !== null && length > limits.max;
  const template = chosen === "return" ? (presiding.items.find((i) => i.kind === "return")?.template ?? null) : (item?.template ?? null);

  const sendLabel = chosen === "ask" ? "Hỏi" : chosen === "remark" ? "Phát biểu" : chosen === "return" ? "Trở lại xét hỏi" : item?.kind === "invite" ? "Mời" : "Thực hiện";
  const placeholder = chosen === "ask"
    ? "Nhập câu hỏi..."
    : chosen === "remark"
      ? "Nhập lời phát biểu..."
      : limits?.optional
        ? "Để trống để dùng lời mẫu, hoặc nhập lời của bạn..."
        : "Nhập lời của bạn...";

  function submit(): void {
    setTouched(true);
    if (!canSend || chosen === null) {
      return;
    }
    const text = draft.trim().length > 0 ? draft : undefined;
    if (chosen === "ask") {
      onAction({ action: "ask", addressee: chosenAsk, text: draft });
    } else if (chosen === "remark") {
      onAction(chosenRemark ? { action: "remark", text: draft, addressee: chosenRemark } : { action: "remark", text: draft });
    } else if (chosen === "return") {
      if (window.confirm(CHAIR_RETURN_CONFIRM_MESSAGE)) {
        onAction(text !== undefined ? { action: "return_to_questioning", text } : { action: "return_to_questioning" });
      }
    } else if (item !== null && (item.kind === "item" || item.kind === "invite")) {
      onAction(text !== undefined ? { action: item.kind, item: item.key, text } : { action: item.kind, item: item.key });
    }
  }

  return (
    <div data-testid="chair-composer" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p id={hintId} data-testid="trial-step-hint" className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground [@media(max-height:640px)]:sr-only">
          {hint}
        </p>
        <Button type="button" variant="outline" size="sm" className="h-9 rounded-full lg:hidden" onClick={onOpenChecklist} aria-haspopup="dialog" data-testid="chair-open-checklist">
          <ListChecks className="h-4 w-4" />
          Điều hành
          <span className="text-xs text-muted-foreground">{requiredLeft > 0 ? `· còn ${requiredLeft} mục` : "· đủ mục"}</span>
        </Button>
      </div>

      {options.length > 0 && chosen !== null && limits !== null ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
          className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={selectId} className="sr-only">
              Hành động
            </label>
            <select
              id={selectId}
              data-testid="chair-target"
              value={chosen}
              onChange={(event) => onTargetChange(event.target.value)}
              className="min-h-10 min-w-0 max-w-full flex-1 rounded-md border border-border bg-background px-2 text-sm text-foreground focus:border-ring focus:outline-none sm:flex-none"
            >
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {chosen === "ask" ? (
              <AddresseeSelect id={`${selectId}-ask`} label="Hỏi" ids={askTo} value={chosenAsk} onChange={onAddresseeChange} participants={participants} testId="chair-ask-addressee" />
            ) : null}
            {chosen === "remark" && remarkTo.length > 0 ? (
              <AddresseeSelect
                id={`${selectId}-remark`}
                label="Gửi tới"
                ids={remarkTo}
                value={chosenRemark}
                onChange={onAddresseeChange}
                participants={participants}
                testId="chair-remark-addressee"
                emptyLabel="Không gửi riêng ai"
              />
            ) : null}
          </div>
          <label htmlFor={textareaId} className="sr-only">
            {limits.label}
          </label>
          <Textarea
            ref={textareaRef}
            id={textareaId}
            data-testid="chair-input"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
            aria-describedby={`${counterId} ${hintId}`}
            aria-invalid={touched && validation !== null}
            placeholder={placeholder}
            className="min-h-[64px] resize-y text-sm leading-relaxed sm:min-h-[76px] [@media(max-height:640px)]:min-h-[56px]"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p id={counterId} data-testid="chair-counter" className={cn("text-xs tabular-nums", overMax ? "font-medium text-red-600" : "text-muted-foreground")}>
              {length.toLocaleString("vi-VN")}/{limits.max.toLocaleString("vi-VN")} ký tự
              {chosen === "ask" ? ` · còn ${presiding.counters.questions_left} câu hỏi` : ""}
              {chosen === "remark" ? ` · còn ${presiding.counters.remarks_left} lần` : ""}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {template !== null && draft !== template ? (
                <Button type="button" variant="ghost" size="sm" className="h-9 rounded-full" data-testid="chair-fill-template" onClick={() => onDraftChange(template)}>
                  <MessageSquareText className="h-4 w-4" />
                  Điền lời mẫu
                </Button>
              ) : null}
              <Button type="submit" size="sm" className="h-9 rounded-full" disabled={!canSend} data-testid="chair-send">
                {chosen === "return" ? <RotateCcw className="h-4 w-4" /> : <Send className="h-4 w-4" />}
                {sendLabel}
              </Button>
            </div>
          </div>
          {((touched && length > 0) || overMax) && validation !== null ? (
            <p role="alert" data-testid="chair-validation" className="text-xs text-red-600">
              {validation}
            </p>
          ) : null}
        </form>
      ) : null}

      {missing !== null && missing.length > 0 ? (
        <p role="status" data-testid="chair-missing" className="rounded-lg border border-primary/20 bg-primary/[0.04] px-3 py-2 text-xs text-foreground">
          Chưa chuyển bước được, còn thiếu: {missing.map((key) => chairItemLabel(key, presiding) ?? key).join("; ")}.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">
          {actions.advanceTo !== null ? `Đủ mục bắt buộc.${nextTitle ? ` Tiếp theo: ${nextTitle}.` : ""}` : `Còn ${requiredLeft} mục bắt buộc chưa làm.`}
        </p>
        <Button
          type="button"
          variant={actions.advanceTo !== null ? "default" : "outline"}
          className="rounded-full"
          disabled={busy}
          data-testid="trial-advance"
          data-ready={actions.advanceTo !== null || undefined}
          onClick={() => (actions.advanceTo !== null ? onAction({ action: "advance", target_step: actions.advanceTo }) : onShowMissing())}
        >
          {advanceLabel}
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
});

function AddresseeSelect({
  id,
  label,
  ids,
  value,
  onChange,
  participants,
  testId,
  emptyLabel
}: {
  id: string;
  label: string;
  ids: readonly string[];
  value: string;
  onChange: (id: string) => void;
  participants: Record<string, TrialParticipant>;
  testId: string;
  emptyLabel?: string;
}) {
  return (
    <span className="flex min-w-0 max-w-full flex-1 items-center gap-2 sm:flex-none">
      <label htmlFor={id} className="shrink-0 text-sm text-foreground">
        {label}:
      </label>
      <select
        id={id}
        data-testid={testId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-10 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-sm text-foreground focus:border-ring focus:outline-none"
      >
        {emptyLabel !== undefined ? <option value="">{emptyLabel}</option> : null}
        {ids.map((participant) => (
          <option key={participant} value={participant}>
            {participantLabel(participants, participant)}
          </option>
        ))}
      </select>
    </span>
  );
}

// F1 stops before deliberation: steps 10-11 (decision form, assessors, pronouncement) come in F2.
export function ChairComingSoon() {
  return (
    <div data-testid="chair-coming-soon" role="status" className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3">
      <Gavel className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <p className="min-w-0 text-sm text-foreground">
        <span className="font-medium">Nghị án và tuyên án: sắp có.</span>
        <span className="block text-xs text-muted-foreground">
          Phần quyết định của Chủ tọa chưa có trên giao diện. Phiên tòa đã được lưu ở bước này; bạn quay lại sau khi tính năng được mở.
        </span>
      </p>
    </div>
  );
}
