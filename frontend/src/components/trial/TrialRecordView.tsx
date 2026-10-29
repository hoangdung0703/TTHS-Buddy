"use client";

import { ArrowLeft, Check, Copy, Info, Printer } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ClerkRecordEditor, type ClerkDrafts } from "@/components/trial/ClerkRecordEditor";
import { Button } from "@/components/ui/button";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { getTrialRecord, TrialApiError } from "@/lib/api";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
import { RecordDocument } from "@/components/trial/RecordDocument";
import { TrialText } from "@/components/trial/TrialText";
import { applyClerkDraft, CLERK_SECTION_TITLES, clerkSubsection, messageForTrialError } from "@/lib/trialRules";
import type { TrialClerkDraft, TrialRecord, TrialRecordDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

const COPY_FEEDBACK_MS = 2000;

// The record (contract 3.7): rendered from `record` (Mẫu 22-HS), both simulation lines kept,
// printable via the browser. "Sao chép văn bản" copies the server's plain `text`.
//
// Clerk sessions (contract 3.9-3.10) carry `clerk`: until it is finalised the screen opens in
// "Soạn" (ClerkRecordEditor) with a "Xem bản nháp" preview; once finalised it only shows the record.
export function TrialRecordView({ sessionId }: { sessionId: string }) {
  const [text, setText] = useState<string | null>(null);
  // Structured Mẫu 22-HS record; null for an older backend, which only sends `text`.
  const [record, setRecord] = useState<TrialRecordDocument | null>(null);
  const [clerk, setClerk] = useState<TrialClerkDraft | null>(null);
  // The clerk's IV.2/IV.3 as typed; kept here so switching Soạn/Xem never loses an edit.
  const [drafts, setDrafts] = useState<ClerkDrafts>({ iv2: "", iv3: "" });
  const [clerkMode, setClerkMode] = useState<"compose" | "preview">("compose");
  // Saved since the record was read: the preview and the copy text need a fresh GET.
  const [stale, setStale] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { isSlow, start, stop } = useSlowRequestNotice();

  const adopt = useCallback((result: TrialRecord, keepDrafts: boolean): void => {
    setText(result.text);
    setRecord(result.record ?? null);
    setClerk(result.clerk ?? null);
    setStale(false);
    if (!keepDrafts && result.clerk) {
      setDrafts({ iv2: result.clerk.iv2, iv3: result.clerk.iv3 });
    }
  }, []);

  const load = useCallback(async (keepDrafts = false): Promise<void> => {
    setError(null);
    start();
    try {
      adopt(await getTrialRecord(sessionId), keepDrafts);
    } catch (loadError) {
      if (!(loadError instanceof TrialApiError && loadError.featureDisabled)) {
        setError(loadError instanceof TrialApiError ? messageForTrialError(loadError) : "Không tải được biên bản. Bạn thử lại nhé.");
      }
    } finally {
      stop();
    }
  }, [adopt, sessionId, start, stop]);

  useEffect(() => {
    void load();
  }, [load]);

  const isClerk = clerk !== null;
  const composing = isClerk && !clerk.finalized && clerkMode === "compose";
  // Preview of an unfinalised draft: the record with the last saved IV.2/IV.3.
  const shownRecord = record !== null && isClerk && !clerk.finalized ? applyClerkDraft(record, clerk) : record;

  function showPreview(): void {
    setClerkMode("preview");
    if (stale) {
      // Refresh `text` (copy) without touching what is being typed.
      void load(true);
    }
  }

  async function handleCopy(): Promise<void> {
    if (text === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
    } catch {
      setError("Trình duyệt không cho sao chép. Bạn bôi đen văn bản rồi sao chép thủ công nhé.");
    }
  }

  return (
    <div className={cn("mx-auto px-4 py-8 sm:px-6 print:max-w-none print:p-0", composing ? "max-w-7xl" : "max-w-3xl")}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Button asChild variant="ghost" size="sm">
          <Link href={`/trial/${sessionId}`}>
            <ArrowLeft className="h-4 w-4" />
            Quay lại phiên tòa
          </Link>
        </Button>
        {text !== null && !composing ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" className="rounded-full" onClick={() => void handleCopy()}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? "Đã sao chép" : "Sao chép văn bản"}
            </Button>
            <Button size="sm" className="rounded-full" onClick={() => window.print()}>
              <Printer className="h-4 w-4" />
              In / lưu PDF
            </Button>
          </div>
        ) : null}
      </div>

      <div className="mb-6 flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div className="min-w-0">
          <h1 className="font-serif text-3xl font-light tracking-tight text-foreground">Biên bản phiên tòa</h1>
          {isClerk ? (
            <p data-testid="clerk-record-status" className="mt-1 text-xs text-muted-foreground">
              {clerk.finalized ? "Đã chốt. Mục 2 và mục 3 của phần IV do bạn soạn." : "Bản nháp: bạn soạn mục 2 và mục 3 của phần IV, rồi chốt biên bản."}
            </p>
          ) : null}
        </div>
        {isClerk && !clerk.finalized ? (
          <div role="tablist" aria-label="Chế độ biên bản" className="flex gap-1 rounded-full bg-muted p-0.5">
            {(["compose", "preview"] as const).map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={clerkMode === key}
                data-testid={`clerk-mode-${key}`}
                onClick={() => (key === "preview" ? showPreview() : setClerkMode("compose"))}
                className={cn(
                  "min-h-9 rounded-full px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  clerkMode === key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {key === "compose" ? "Soạn" : "Xem bản nháp"}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {notice !== null ? (
        <p role="status" data-testid="clerk-record-notice" className="mb-6 flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-foreground print:hidden">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          {notice}
        </p>
      ) : null}

      {error !== null ? (
        <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 print:hidden">
          <span>{error}</span>
          {text === null ? (
            <Button variant="outline" size="sm" onClick={() => void load(false)}>
              Thử lại
            </Button>
          ) : null}
        </div>
      ) : null}

      {text === null && error === null ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Đang tải biên bản">
          {isSlow ? <p className="text-sm text-muted-foreground">{SLOW_REQUEST_NOTICE}</p> : null}
          <div className="h-96 animate-pulse rounded-xl border border-border bg-muted/60" />
        </div>
      ) : null}

      {composing && clerk !== null && record !== null ? (
        <ClerkRecordEditor
          sessionId={sessionId}
          headings={{
            iv2: clerkSubsection(record, "iv2")?.heading ?? CLERK_SECTION_TITLES.iv2,
            iv3: clerkSubsection(record, "iv3")?.heading ?? CLERK_SECTION_TITLES.iv3
          }}
          clerk={clerk}
          drafts={drafts}
          onDraftsChange={setDrafts}
          onSaved={(saved) => {
            setClerk(saved);
            setStale(true);
          }}
          onFinalized={(result) => {
            adopt(result, false);
            setNotice("Đã chốt biên bản. Mục 2 và mục 3 không sửa được nữa; ghi chép vẫn sửa được ở màn phiên tòa.");
          }}
          onAlreadyFinalized={(message) => {
            setNotice(message);
            void load(false);
          }}
        />
      ) : text !== null ? (
        <article
          data-testid="trial-record"
          className="rounded-xl border border-border bg-white px-5 py-8 text-[0.95rem] leading-relaxed text-foreground shadow-sm sm:px-10 print:rounded-none print:border-0 print:p-0 print:text-[11.5pt] print:leading-normal print:text-black print:shadow-none"
        >
          {shownRecord !== null ? <RecordDocument record={shownRecord} /> : <TrialText text={text} />}
        </article>
      ) : null}
    </div>
  );
}
