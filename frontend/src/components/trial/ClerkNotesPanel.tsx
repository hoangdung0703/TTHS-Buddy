"use client";

import { AlertCircle, Check, Lightbulb, Loader2, RefreshCw } from "lucide-react";
import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ClerkNotes } from "@/hooks/useClerkNotes";
import { formatSavedTime } from "@/lib/trialRules";
import type { TrialClerkPrompt } from "@/lib/types";
import { cn } from "@/lib/utils";

// The clerk's notes (contract 3.8): a controlled view of useClerkNotes, which alone loads and
// saves. Several of these may be mounted at once (side panel, phone drawer) without conflict.
// The step's note-taking prompt is static text; it carries a neutral label, not a review badge.
export function ClerkNotesPanel({
  notes,
  prompt,
  fill = false,
  className
}: {
  notes: ClerkNotes;
  prompt?: TrialClerkPrompt | null;
  // Stretch the textarea to the panel's height (side panel, drawer).
  fill?: boolean;
  className?: string;
}) {
  const textareaId = useId();
  const statusId = useId();
  const overMax = notes.text.length > notes.maxChars;

  return (
    <div data-testid="trial-notes" className={cn("flex min-h-0 flex-col gap-3", fill && "flex-1", className)}>
      {prompt ? (
        <section data-testid="trial-clerk-prompt" aria-label="Gợi ý ghi chép" className="rounded-lg border border-primary/15 bg-secondary/40 px-3 py-2">
          <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
            <Lightbulb className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
            Gợi ý ghi chép
            <span className="font-normal text-muted-foreground">· Bước {prompt.step}</span>
          </p>
          <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-foreground">{prompt.text}</p>
        </section>
      ) : null}

      {notes.loadError !== null ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1">{notes.loadError}</span>
          <Button variant="outline" size="sm" onClick={notes.retryLoad}>
            Thử lại
          </Button>
        </div>
      ) : null}

      <label htmlFor={textareaId} className="sr-only">
        Ghi chép của Thư ký
      </label>
      <Textarea
        id={textareaId}
        data-testid="trial-notes-input"
        value={notes.text}
        onChange={(event) => notes.setText(event.target.value)}
        readOnly={notes.readOnly}
        disabled={!notes.loaded}
        aria-describedby={statusId}
        placeholder={notes.loaded ? "Ghi lại ai nói, nói gì, nội dung chính..." : "Đang tải ghi chép..."}
        className={cn("resize-y text-sm leading-relaxed", fill ? "min-h-[200px] flex-1" : "min-h-[160px]", notes.readOnly && "bg-muted/40")}
      />

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <p className={cn("text-xs tabular-nums", overMax ? "font-medium text-red-600" : "text-muted-foreground")}>
          {notes.text.length.toLocaleString("vi-VN")}/{notes.maxChars.toLocaleString("vi-VN")} ký tự
        </p>
        <NotesStatus notes={notes} id={statusId} />
      </div>
      <p className="text-[0.7rem] leading-snug text-muted-foreground">Ghi chép chỉ mình bạn xem, không đưa vào phiên tòa hay biên bản.</p>
    </div>
  );
}

function NotesStatus({ notes, id }: { notes: ClerkNotes; id: string }) {
  let content: React.ReactNode;
  if (notes.readOnly) {
    content = notes.saveError ?? "Chỉ xem: phiên tòa đã bị bỏ.";
  } else if (!notes.loaded) {
    content = notes.loadError === null ? "Đang tải..." : "Chưa tải được";
  } else if (notes.status === "pending" || notes.status === "saving") {
    content = (
      <>
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        Đang lưu...
      </>
    );
  } else if (notes.status === "error") {
    return (
      <span id={id} role="alert" data-testid="trial-notes-status" data-status="error" className="flex flex-wrap items-center gap-2 text-xs text-red-700">
        <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="min-w-0">Lỗi lưu. {notes.saveError}</span>
        <Button variant="outline" size="sm" className="h-8" onClick={notes.saveNow} data-testid="trial-notes-retry">
          <RefreshCw className="h-3.5 w-3.5" />
          Thử lại
        </Button>
      </span>
    );
  } else if (notes.status === "saved") {
    const time = formatSavedTime(notes.updatedAt);
    content = (
      <>
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
        {time ? `Đã lưu lúc ${time}` : "Đã lưu"}
      </>
    );
  } else {
    content = "Tự lưu sau 2 giây ngừng gõ";
  }
  return (
    <span id={id} role="status" data-testid="trial-notes-status" data-status={notes.readOnly ? "readonly" : notes.status} className="flex items-center gap-1 text-xs text-muted-foreground">
      {content}
    </span>
  );
}
