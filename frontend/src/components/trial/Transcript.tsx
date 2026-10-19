"use client";

import { Info } from "lucide-react";
import { Fragment } from "react";

import type { TrialParticipant, TrialStepInfo, TrialUtterance } from "@/lib/types";

// The hearing transcript (contract Mục 4): one block per utterance exactly as the server sent it -
// never edited, truncated or animated as if being generated. `speech` is a bubble (the student's
// on the right, primary); `procedural` a small centred line; `notice` its own centred style and
// never part of the record.
export function Transcript({
  utterances,
  steps,
  participants
}: {
  utterances: TrialUtterance[];
  steps: TrialStepInfo[];
  participants: Record<string, TrialParticipant>;
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
            <UtteranceItem utterance={utterance} participants={participants} />
          </Fragment>
        );
      })}
    </ol>
  );
}

function UtteranceItem({ utterance, participants }: { utterance: TrialUtterance; participants: Record<string, TrialParticipant> }) {
  const speaker = `${utterance.speaker_role}${utterance.speaker_name ? ` · ${utterance.speaker_name}` : ""}`;

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

  if (utterance.is_user) {
    return (
      <li data-testid="trial-user-utterance" data-seq={utterance.seq} className="flex flex-col items-end gap-1">
        <p className="text-xs font-medium text-muted-foreground">
          Bạn · {speaker}
          {addressee ? ` → hỏi ${addressee.role} ${addressee.name}` : ""}
        </p>
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-primary px-4 py-3 text-sm leading-relaxed text-primary-foreground sm:max-w-[75%]">
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
      <div className="max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 text-sm leading-relaxed text-foreground sm:max-w-[80%]">
        {utterance.text}
      </div>
    </li>
  );
}
