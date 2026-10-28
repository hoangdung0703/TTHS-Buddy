"use client";

import { ArrowLeft, Check, Copy, Printer } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { getTrialRecord, TrialApiError } from "@/lib/api";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
import { RecordDocument } from "@/components/trial/RecordDocument";
import { TrialText } from "@/components/trial/TrialText";
import { messageForTrialError } from "@/lib/trialRules";
import type { TrialRecordDocument } from "@/lib/types";

const COPY_FEEDBACK_MS = 2000;

// The record (contract 3.7): rendered from `record` (Mẫu 22-HS), both simulation lines kept,
// printable via the browser. "Sao chép văn bản" copies the server's plain `text`.
export function TrialRecordView({ sessionId }: { sessionId: string }) {
  const [text, setText] = useState<string | null>(null);
  // Structured Mẫu 22-HS record; null for an older backend, which only sends `text`.
  const [record, setRecord] = useState<TrialRecordDocument | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { isSlow, start, stop } = useSlowRequestNotice();

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    start();
    try {
      const result = await getTrialRecord(sessionId);
      setText(result.text);
      setRecord(result.record ?? null);
    } catch (loadError) {
      if (!(loadError instanceof TrialApiError && loadError.featureDisabled)) {
        setError(loadError instanceof TrialApiError ? messageForTrialError(loadError) : "Không tải được biên bản. Bạn thử lại nhé.");
      }
    } finally {
      stop();
    }
  }, [sessionId, start, stop]);

  useEffect(() => {
    void load();
  }, [load]);

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
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 print:max-w-none print:p-0">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Button asChild variant="ghost" size="sm">
          <Link href={`/trial/${sessionId}`}>
            <ArrowLeft className="h-4 w-4" />
            Quay lại phiên tòa
          </Link>
        </Button>
        {text !== null ? (
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

      <h1 className="mb-6 font-serif text-3xl font-light tracking-tight text-foreground print:hidden">Biên bản phiên tòa</h1>

      {error !== null ? (
        <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 print:hidden">
          <span>{error}</span>
          {text === null ? (
            <Button variant="outline" size="sm" onClick={() => void load()}>
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

      {text !== null ? (
        <article
          data-testid="trial-record"
          className="rounded-xl border border-border bg-white px-5 py-8 text-[0.95rem] leading-relaxed text-foreground shadow-sm sm:px-10 print:rounded-none print:border-0 print:p-0 print:text-[11.5pt] print:leading-normal print:text-black print:shadow-none"
        >
          {record !== null ? <RecordDocument record={record} /> : <TrialText text={text} />}
        </article>
      ) : null}
    </div>
  );
}
