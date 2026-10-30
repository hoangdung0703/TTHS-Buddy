"use client";

import { Info } from "lucide-react";
import { Fragment } from "react";

import { TrialText } from "@/components/trial/TrialText";
import { isLongTrialText } from "@/lib/trialText";
import type { TrialParticipant, TrialStepInfo, TrialUtterance } from "@/lib/types";
import { cn } from "@/lib/utils";

// The hearing transcript (contract Mục 4): one block per utterance exactly as the server sent it -
// never edited, truncated or animated as if being generated. `speech` is a bubble (the student's
// on the right, primary); `procedural` a small centred line; `notice` its own centred style and
// never part of the record.
export function Transcript({
  utterances,
  steps,
  participants,
  itemLabel
}: {
  utterances: TrialUtterance[];
  steps: TrialStepInfo[];
  participants: Record<string, TrialParticipant>;
  // Presiding judge sessions: the checklist label of an utterance's procedure_item.
  itemLabel?: (key: string) => string | null;
}) {
  const titleOf = (number: number) => steps.find((step) => step.number === number)?.title ?? "";

  return (
    <ol aria-label="Diễn biến phiên tòa" className="flex flex-col gap-4">
      {utterances.map((utterance, index) => {
        const startsStep = index === 0 || utterances[index - 1].step !== utterance.step;
        return (
          <Fragment key={utterance.seq}>
            {startsStep ? (
              <li aria-hidden="false" className="flex items-center gap-3 pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                <span className="text-center">
                  Bước {utterance.step} · {titleOf(utterance.step)}
                </span>
                <span className="h-px flex-1 bg-border" />
              </li>
            ) : null}
            <UtteranceItem utterance={utterance} participants={participants} itemLabel={itemLabel} />
          </Fragment>
        );
      })}
    </ol>
  );
}

function UtteranceItem({
  utterance,
  participants,
  itemLabel
}: {
  utterance: TrialUtterance;
  participants: Record<string, TrialParticipant>;
  itemLabel?: (key: string) => string | null;
}) {
  const speaker = `${utterance.speaker_role}${utterance.speaker_name ? ` · ${utterance.speaker_name}` : ""}`;
  // Presiding judge: which checklist item the student's line carried out (contract 4, procedure_item).
  const item = utterance.is_user && utterance.procedure_item && itemLabel ? itemLabel(utterance.procedure_item) : null;
  const itemTag = item ? (
    <span data-testid="trial-procedure-item" className="ml-1.5 rounded-full bg-muted px-1.5 py-px text-[0.65rem] font-normal text-muted-foreground">
      {item}
    </span>
  ) : null;

  if (utterance.kind === "notice") {
    return (
      <li data-testid="trial-notice" data-seq={utterance.seq} className="flex justify-center">
        <div role="note" className="flex max-w-[90%] items-start gap-2 rounded-lg border border-dashed border-primary/30 bg-primary/[0.04] px-4 py-2.5 text-sm text-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="min-w-0 whitespace-pre-wrap break-words">
            <span className="font-medium">{speaker}: </span>
            {utterance.text}
          </p>
        </div>
      </li>
    );
  }

  // A fixed sentence the student's own action produced (defendant: "Bị cáo không trả lời câu hỏi
  // này.", a skipped optional turn): on the student's side, but neutral rather than primary.
  if (utterance.kind === "procedural" && utterance.is_user) {
    return (
      <li data-testid="trial-user-procedural" data-seq={utterance.seq} className="flex flex-col items-end gap-1">
        <p className="text-xs font-medium text-muted-foreground">
          Bạn · {speaker}
          {itemTag}
        </p>
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm border border-border bg-muted/50 px-4 py-2.5 text-sm leading-relaxed text-foreground sm:max-w-[75%]">
          {utterance.text}
        </p>
      </li>
    );
  }

  if (utterance.kind === "procedural") {
    return (
      <li data-testid="trial-procedural" data-seq={utterance.seq} className="flex justify-center px-2">
        <p className="max-w-[90%] whitespace-pre-wrap break-words text-center text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground/80">{speaker}: </span>
          {utterance.text}
        </p>
      </li>
    );
  }

  const addressee = utterance.addressee ? participants[utterance.addressee] : undefined;
  // Long speeches get a reading layout: wider measure (~70 characters), calmer line height and
  // paragraph spacing. Short one-paragraph lines keep the compact bubble.
  const long = isLongTrialText(utterance.text);

  if (utterance.is_user) {
    return (
      <li data-testid="trial-user-utterance" data-seq={utterance.seq} className="flex flex-col items-end gap-1">
        <p className="text-xs font-medium text-muted-foreground">
          Bạn · {speaker}
          {addressee ? ` → ${utterance.procedure_item === "remark" ? "" : "hỏi "}${addressee.role} ${addressee.name}` : ""}
          {itemTag}
        </p>
        {/* The student's own words stay exactly as sent (pre-wrap), only the layout widens. */}
        <div
          data-long={long || undefined}
          className={cn(
            "whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-primary text-primary-foreground",
            long ? "w-full max-w-[44rem] px-5 py-4 text-[0.9375rem] leading-7 sm:w-auto sm:max-w-[min(85%,44rem)]" : "max-w-[85%] px-4 py-3 text-sm leading-relaxed sm:max-w-[75%]"
          )}
        >
          {utterance.text}
        </div>
      </li>
    );
  }

  return (
    <li data-testid="trial-ai-utterance" data-seq={utterance.seq} className="flex flex-col items-start gap-1">
      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span className="rounded-full bg-secondary px-2 py-0.5 font-medium text-secondary-foreground">{utterance.speaker_role}</span>
        {utterance.speaker_name ? <span className="font-medium text-foreground/80">{utterance.speaker_name}</span> : null}
      </p>
      <div
        data-long={long || undefined}
        className={cn(
          "rounded-2xl rounded-tl-sm border border-border bg-card text-foreground",
          long ? "w-full max-w-[44rem] px-5 py-4 text-[0.9375rem]" : "max-w-[90%] px-4 py-3 text-sm sm:max-w-[80%]"
        )}
      >
        <TrialText text={utterance.text} density={long ? "reading" : "compact"} />
      </div>
    </li>
  );
}
