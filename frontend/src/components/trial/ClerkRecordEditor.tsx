"use client";

import { AlertCircle, ClipboardCopy, Info, Loader2, Lock, Save } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { ClerkNotesPanel } from "@/components/trial/ClerkNotesPanel";
import { Transcript } from "@/components/trial/Transcript";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useClerkNotes } from "@/hooks/useClerkNotes";
import { finalizeTrialRecord, getTrial, putTrialRecordDraft, TrialApiError } from "@/lib/api";
import {
  canFinalizeClerkDraft,
  CLERK_SECTION_DEFAULT_LIMITS,
  CLERK_SECTION_STEPS,
  CLERK_SECTION_TITLES,
  CLERK_SECTIONS,
  clerkNoticeHint,
  clerkSectionLength,
  formatSavedTime,
  messageForTrialError
} from "@/lib/trialRules";
import type { TrialClerkDraft, TrialClerkNotice, TrialClerkSection, TrialDetail, TrialRecord } from "@/lib/types";
import { cn } from "@/lib/utils";

export type ClerkDrafts = Record<TrialClerkSection, string>;

interface ClerkRecordEditorProps {
  sessionId: string;
  // Headings of the two sections as the record names them.
  headings: Record<TrialClerkSection, string>;
  clerk: TrialClerkDraft;
  drafts: ClerkDrafts;
  onDraftsChange: (drafts: ClerkDrafts) => void;
  onSaved: (clerk: TrialClerkDraft) => void;
  onFinalized: (record: TrialRecord) => void;
  // The server says the record is already final (another tab): re-read it and show it.
  onAlreadyFinalized: (message: string) => void;
}

// "Soạn" mode of a clerk record (contract 3.9-3.10, THIET-KE 11.3.5): the student writes IV.2 and
// IV.3; every other part is built by the server. Saving returns the cleaned text and the "Lưu ý"
// (feedback only, never a refusal or a score). "Chốt biên bản" saves first, then finalises the
// saved draft; it is locked while either section is empty.
export function ClerkRecordEditor({ sessionId, headings, clerk, drafts, onDraftsChange, onSaved, onFinalized, onAlreadyFinalized }: ClerkRecordEditorProps) {
  const limits = clerk.limits ?? CLERK_SECTION_DEFAULT_LIMITS;
  const [saving, setSaving] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sideTab, setSideTab] = useState<"notes" | "transcript">("notes");
  const [transcriptSection, setTranscriptSection] = useState<TrialClerkSection>("iv2");
  const [detail, setDetail] = useState<TrialDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const notes = useClerkNotes(sessionId, true, false);
  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;

  const dirty = CLERK_SECTIONS.some((key) => drafts[key] !== clerk[key]);
  const anyOver = CLERK_SECTIONS.some((key) => drafts[key].length > limits.hard_max);
  const canFinalize = canFinalizeClerkDraft(drafts, limits);
  const working = saving || finalizing;

  const loadDetail = useCallback(async (): Promise<void> => {
    setDetailError(null);
    try {
      setDetail(await getTrial(sessionId));
    } catch (loadError) {
      if (!(loadError instanceof TrialApiError && loadError.featureDisabled)) {
        setDetailError("Không tải được diễn biến phiên tòa. Bạn thử lại nhé.");
      }
    }
  }, [sessionId]);

  useEffect(() => {
    if (sideTab === "transcript" && detail === null && detailError === null) {
      void loadDetail();
    }
  }, [sideTab, detail, detailError, loadDetail]);

  // Unsaved IV.2/IV.3 text: a reload or tab close asks first.
  useEffect(() => {
    if (!dirty) {
      return;
    }
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  function describe(failure: unknown): string {
    if (failure instanceof TrialApiError) {
      if (failure.status === 422) {
        return `Mỗi mục tối đa ${limits.hard_max.toLocaleString("vi-VN")} ký tự. Bạn rút gọn mục dài quá rồi lưu lại nhé.`;
      }
      return messageForTrialError(failure);
    }
    return "Mất kết nối tới máy chủ nên chưa lưu được. Nội dung vẫn còn trên màn hình; bạn thử lại nhé.";
  }

  // Saves both sections. Returns false when nothing was saved (the error is on screen).
  async function save(): Promise<boolean> {
    const sending = { iv2: draftsRef.current.iv2, iv3: draftsRef.current.iv3 };
    setSaving(true);
    setError(null);
    try {
      const result = await putTrialRecordDraft(sessionId, sending);
      onSaved(result);
      // The server returns the cleaned text; take it unless the student typed on meanwhile.
      const current = draftsRef.current;
      if (current.iv2 === sending.iv2 && current.iv3 === sending.iv3) {
        onDraftsChange({ iv2: result.iv2, iv3: result.iv3 });
      }
      return true;
    } catch (failure) {
      if (failure instanceof TrialApiError && failure.featureDisabled) {
        return false;
      }
      if (failure instanceof TrialApiError && failure.code === "trial_record_finalized") {
        onAlreadyFinalized(messageForTrialError(failure));
        return false;
      }
      setError(describe(failure));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function finalize(): Promise<void> {
    if (!canFinalize || working) {
      return;
    }
    if (!window.confirm("Chốt biên bản? Sau khi chốt, mục 2 và mục 3 của phần IV không sửa được nữa. Ghi chép vẫn sửa được.")) {
      return;
    }
    setFinalizing(true);
    try {
      if (!(await save())) {
        return;
      }
      setError(null);
      const result = await finalizeTrialRecord(sessionId);
      onFinalized(result);
    } catch (failure) {
      if (!(failure instanceof TrialApiError && failure.featureDisabled)) {
        setError(describe(failure));
      }
    } finally {
      setFinalizing(false);
    }
  }

  const noticesFor = (key: TrialClerkSection): TrialClerkNotice[] => clerk.notices.filter((notice) => notice.section === key);
  const notesText = notes.loaded ? notes.text.trim() : "";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <div className="flex min-w-0 flex-col gap-5">
        <p className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          Bạn là Thư ký: viết tóm tắt mục 2 (hỏi và trả lời) và mục 3 (tranh luận) của phần IV. Các mục khác do hệ thống dựng từ diễn biến phiên tòa. Xem lại ở
          thẻ “Xem bản nháp”, rồi bấm “Chốt biên bản”.
        </p>

        {CLERK_SECTIONS.map((key) => (
          <SectionEditor
            key={key}
            sectionKey={key}
            heading={headings[key]}
            value={drafts[key]}
            limits={limits}
            disabled={working}
            notices={noticesFor(key)}
            noticesStale={drafts[key] !== clerk[key]}
            canCopyNotes={drafts[key].trim().length === 0 && notesText.length > 0}
            onChange={(value) => onDraftsChange({ ...draftsRef.current, [key]: value })}
            onCopyNotes={() => onDraftsChange({ ...draftsRef.current, [key]: notes.text.slice(0, limits.hard_max) })}
          />
        ))}

        <div data-testid="clerk-actions" className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t border-border bg-background/95 px-4 pb-4 pt-3 backdrop-blur sm:-mx-6 sm:px-6">
          {error !== null ? (
            <div role="alert" data-testid="clerk-error" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="min-w-0">{error}</span>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <p data-testid="clerk-save-status" className="min-w-0 basis-full text-xs text-muted-foreground sm:flex-1 sm:basis-0">
              {saving ? "Đang lưu..." : dirty ? "Có thay đổi chưa lưu." : clerk.updated_at ? `Đã lưu lúc ${formatSavedTime(clerk.updated_at)}.` : "Chưa lưu bản nháp nào."}
              {!canFinalize ? <span className="block">Viết đủ mục 2 và mục 3 để chốt biên bản.</span> : null}
            </p>
            <Button variant="outline" size="sm" className="ml-auto rounded-full sm:ml-0" data-testid="clerk-save" disabled={working || anyOver || !dirty} onClick={() => void save()}>
              {saving && !finalizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Lưu và kiểm tra
            </Button>
            <Button size="sm" className="rounded-full" data-testid="clerk-finalize" disabled={working || !canFinalize} onClick={() => void finalize()}>
              {finalizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
              Chốt biên bản
            </Button>
          </div>
        </div>
      </div>

      <aside aria-label="Ghi chép và diễn biến" className="min-w-0 lg:sticky lg:top-12 lg:self-start">
        <div className="flex flex-col rounded-xl border border-primary/[0.08] bg-card p-4 shadow-[0_2px_20px_rgba(30,36,96,0.05)] lg:h-[calc(100vh-8rem)]">
          <div role="tablist" aria-label="Khung tham khảo" className="mb-3 flex gap-1 self-start rounded-full bg-muted p-0.5">
            {(["notes", "transcript"] as const).map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={sideTab === key}
                data-testid={`clerk-side-${key}`}
                onClick={() => setSideTab(key)}
                className={cn(
                  "min-h-9 rounded-full px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  sideTab === key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {key === "notes" ? "Ghi chép" : "Diễn biến"}
              </button>
            ))}
          </div>
          {sideTab === "notes" ? (
            <ClerkNotesPanel notes={notes} fill className="lg:min-h-0" />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              <div role="radiogroup" aria-label="Diễn biến của mục" className="flex flex-wrap gap-1.5">
                {CLERK_SECTIONS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    role="radio"
                    aria-checked={transcriptSection === key}
                    onClick={() => setTranscriptSection(key)}
                    className={cn(
                      "min-h-9 rounded-full border px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      transcriptSection === key ? "border-primary bg-primary text-primary-foreground" : "border-border bg-secondary text-secondary-foreground hover:bg-accent/30"
                    )}
                  >
                    Mục {key === "iv2" ? "2" : "3"} · bước {CLERK_SECTION_STEPS[key].join(", ")}
                  </button>
                ))}
              </div>
              <div data-testid="clerk-transcript" className="max-h-[60vh] min-h-0 flex-1 overflow-y-auto pr-1 lg:max-h-none">
                {detailError !== null ? (
                  <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-red-700">
                    <span>{detailError}</span>
                    <Button variant="outline" size="sm" onClick={() => void loadDetail()}>
                      Thử lại
                    </Button>
                  </div>
                ) : detail === null ? (
                  <div className="h-40 animate-pulse rounded-lg bg-muted/60" aria-busy="true" aria-label="Đang tải diễn biến" />
                ) : (
                  <Transcript
                    utterances={detail.utterances.filter((u) => u.kind !== "notice" && CLERK_SECTION_STEPS[transcriptSection].includes(u.step))}
                    steps={detail.steps}
                    participants={detail.participants}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function SectionEditor({
  sectionKey,
  heading,
  value,
  limits,
  disabled,
  notices,
  noticesStale,
  canCopyNotes,
  onChange,
  onCopyNotes
}: {
  sectionKey: TrialClerkSection;
  heading: string;
  value: string;
  limits: { min: number; max: number; hard_max: number };
  disabled: boolean;
  notices: TrialClerkNotice[];
  noticesStale: boolean;
  canCopyNotes: boolean;
  onChange: (value: string) => void;
  onCopyNotes: () => void;
}) {
  const textareaId = useId();
  const counterId = useId();
  const length = clerkSectionLength(value, limits);
  const shownHints = new Set<string>();

  return (
    <section data-testid={`clerk-section-${sectionKey}`} aria-labelledby={`${textareaId}-heading`} className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={`${textareaId}-heading`} className="text-sm font-semibold text-foreground">
          <label htmlFor={textareaId}>{heading || CLERK_SECTION_TITLES[sectionKey]}</label>
        </h2>
        <span className="text-xs text-muted-foreground">Phần IV · bước {CLERK_SECTION_STEPS[sectionKey].join(", ")}</span>
      </div>
      <Textarea
        id={textareaId}
        data-testid={`clerk-input-${sectionKey}`}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={counterId}
        aria-invalid={length === "over"}
        placeholder={sectionKey === "iv2" ? "Ai hỏi, hỏi ai, nội dung chính của câu hỏi và câu trả lời..." : "Ý kiến chính của Kiểm sát viên, luật sư và phần đối đáp..."}
        className="min-h-[160px] resize-y text-sm leading-relaxed sm:min-h-[200px] [@media(max-height:640px)]:min-h-[120px]"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p
          id={counterId}
          data-testid={`clerk-counter-${sectionKey}`}
          data-length={length}
          className={cn(
            "text-xs tabular-nums",
            length === "over" ? "font-medium text-red-600" : length === "long" ? "font-medium text-amber-700" : length === "ok" ? "text-emerald-700" : "text-muted-foreground"
          )}
        >
          {value.length.toLocaleString("vi-VN")} ký tự · gợi ý {limits.min.toLocaleString("vi-VN")}–{limits.max.toLocaleString("vi-VN")}
          {length === "long" ? " · dài hơn gợi ý, vẫn lưu được" : ""}
          {length === "over" ? ` · vượt trần ${limits.hard_max.toLocaleString("vi-VN")} ký tự, rút gọn để lưu` : ""}
        </p>
        {canCopyNotes ? (
          <Button type="button" variant="outline" size="sm" data-testid={`clerk-copy-notes-${sectionKey}`} disabled={disabled} onClick={onCopyNotes}>
            <ClipboardCopy className="h-4 w-4" />
            Chép từ ghi chép
          </Button>
        ) : null}
      </div>
      {notices.length > 0 ? (
        <div data-testid={`clerk-notices-${sectionKey}`} role="note" aria-label={`Lưu ý cho ${heading}`} className="flex flex-col gap-1.5 rounded-lg border border-border bg-muted/40 px-3 py-2">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <Info className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            Lưu ý
            {noticesStale ? <span className="font-normal text-muted-foreground">· theo bản đã lưu; lưu lại để cập nhật</span> : null}
          </p>
          <ul className="flex flex-col gap-1.5 text-xs leading-relaxed">
            {notices.map((notice, index) => {
              const hint = clerkNoticeHint(notice.code);
              const showHint = hint !== null && !shownHints.has(notice.code);
              shownHints.add(notice.code);
              return (
                <li key={index} data-code={notice.code} className="break-words text-foreground">
                  {notice.message}
                  {showHint ? <span className="block text-muted-foreground">{hint}</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
