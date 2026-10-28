"use client";

import { AlertCircle, ArrowDown, ArrowLeft, FileText, FolderOpen, Maximize2, MoreHorizontal, RefreshCw, Trash2, X, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CaseFilePanel, type CaseFileTab } from "@/components/trial/CaseFilePanel";
import { StepBar } from "@/components/trial/StepBar";
import { TrialComposer, type ComposerAction } from "@/components/trial/TrialComposer";
import { Transcript } from "@/components/trial/Transcript";
import { Button } from "@/components/ui/button";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { abandonTrial, deleteTrial, getTrial, sendTrialTurn, TrialApiError } from "@/lib/api";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
import { isResyncConflict, mergeUtterances, messageForTrialError, TRIAL_ROLE_LABELS } from "@/lib/trialRules";
import type { TrialDetail, TrialState, TrialUtterance } from "@/lib/types";

// Auto-follow only when the reader is this close to the bottom; further up they are re-reading.
const NEAR_BOTTOM_PX = 80;
// The last turn ends with "Đang lập biên bản..." (record summary, up to ~60s). The session is already
// stored as completed by then, so after this long the screen re-reads it and releases the student.
const RECORD_WAIT_RELEASE_MS = 15000;
const RECORD_STATUS_PREFIX = "Đang lập biên bản";

// The hearing screen (THIET-KE Mục 7, màn 3). Server state is the only authority: every request
// carries expected_step/expected_version from the latest state, a 409 replaces the state and
// re-reads the transcript, and nothing is ever retried automatically.
export function TrialHearing({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<TrialDetail | null>(null);
  const [state, setState] = useState<TrialState | null>(null);
  const [utterances, setUtterances] = useState<TrialUtterance[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [turnError, setTurnError] = useState<string | null>(null);
  const [softNotice, setSoftNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [expandedOpen, setExpandedOpen] = useState(false);
  const [caseTab, setCaseTab] = useState<CaseFileTab>("summary");
  // New utterances arrived while the reader was scrolled up: show "Có lời mới".
  const [newBelow, setNewBelow] = useState(false);
  // The final turn released the screen while the record summary is still being written.
  const [recordPending, setRecordPending] = useState(false);
  const atBottomRef = useRef(true);
  const scrollContainerRef = useRef<HTMLElement | null>(null);
  const expandButtonRef = useRef<HTMLButtonElement>(null);
  const expandedCloseRef = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const drawerCloseRef = useRef<HTMLButtonElement>(null);
  const slowRequest = useSlowRequestNotice();
  const { start: startSlow, stop: stopSlow } = slowRequest;

  const reload = useCallback(async (): Promise<boolean> => {
    try {
      const result = await getTrial(sessionId);
      setDetail(result);
      setState(result.state);
      setUtterances(result.utterances);
      setLoadError(null);
      return true;
    } catch (error) {
      if (error instanceof TrialApiError && error.featureDisabled) {
        return false; // TrialShell redirects
      }
      if (error instanceof TrialApiError && error.status === 404) {
        setNotFound(true);
        return false;
      }
      setLoadError(error instanceof TrialApiError ? messageForTrialError(error) : "Không tải được phiên tòa. Kiểm tra kết nối rồi thử lại.");
      return false;
    }
  }, [sessionId]);

  useEffect(() => {
    startSlow();
    void reload().finally(() => stopSlow());
  }, [reload, startSlow, stopSlow]);

  useEffect(() => () => abortRef.current?.abort(), []);

  // The page's scroll container (AuthenticatedLayout's overflow-y-auto column).
  const getScrollContainer = useCallback((): HTMLElement | null => {
    if (scrollContainerRef.current?.isConnected) {
      return scrollContainerRef.current;
    }
    let container = endRef.current?.parentElement ?? null;
    while (container !== null && !/(auto|scroll)/.test(getComputedStyle(container).overflowY)) {
      container = container.parentElement;
    }
    scrollContainerRef.current = container;
    return container;
  }, []);

  // The composer dock is sticky but sits in normal flow right after the transcript, so scrolling
  // the container to its end puts the newest utterance directly above the dock, never under it.
  // Instant, not smooth: a smooth animation would read as "scrolled up" if a line lands mid-way.
  const scrollToLatest = useCallback((): void => {
    const container = getScrollContainer();
    container?.scrollTo({ top: container.scrollHeight, behavior: "auto" });
    atBottomRef.current = true;
    setNewBelow(false);
  }, [getScrollContainer]);

  // Track whether the reader is at the bottom.
  const hasDetail = detail !== null;
  useEffect(() => {
    const container = getScrollContainer();
    if (container === null) {
      return;
    }
    function onScroll(): void {
      if (container === null) {
        return;
      }
      const distance = container.scrollHeight - container.scrollTop - container.clientHeight;
      atBottomRef.current = distance <= NEAR_BOTTOM_PX;
      if (atBottomRef.current) {
        setNewBelow(false);
      }
    }
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, [getScrollContainer, hasDetail]);

  // Follow the newest utterance: always on first paint and after the student's own line; otherwise
  // only when the reader was already near the bottom (decided before the new line rendered).
  const lastUtteranceItem = utterances.length > 0 ? utterances[utterances.length - 1] : null;
  const lastSeq = lastUtteranceItem?.seq ?? -1;
  const lastIsUser = lastUtteranceItem?.is_user ?? false;
  const hasScrolledRef = useRef(false);
  useEffect(() => {
    if (lastSeq < 0) {
      return;
    }
    const follow = !hasScrolledRef.current || lastIsUser || atBottomRef.current;
    hasScrolledRef.current = true;
    if (!follow) {
      setNewBelow(true);
      return;
    }
    const frame = requestAnimationFrame(() => scrollToLatest());
    return () => cancelAnimationFrame(frame);
  }, [lastSeq, lastIsUser, scrollToLatest]);

  // An on-screen keyboard shrinks the (visual) viewport; keep the newest utterance in view while
  // the student is typing.
  useEffect(() => {
    const viewport = window.visualViewport;
    function onResize(): void {
      if (composerRef.current?.contains(document.activeElement) && atBottomRef.current) {
        scrollToLatest();
      }
    }
    viewport?.addEventListener("resize", onResize);
    window.addEventListener("resize", onResize);
    return () => {
      viewport?.removeEventListener("resize", onResize);
      window.removeEventListener("resize", onResize);
    };
  }, [scrollToLatest]);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    drawerCloseRef.current?.focus();
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setDrawerOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  useEffect(() => {
    if (!expandedOpen) {
      return;
    }
    const opener = expandButtonRef.current;
    expandedCloseRef.current?.focus();
    function onKey(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setExpandedOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [expandedOpen]);

  async function runAction(action: ComposerAction): Promise<void> {
    if (busyRef.current || state === null) {
      return;
    }
    busyRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setTurnError(null);
    setSoftNotice(null);
    setStatusMessage(null);
    startSlow();

    // httpFailed: the request was refused before streaming (handled in catch). released: the
    // record-summary wait was cut short and the screen already shows the completed session.
    const outcome = { gotState: false, streamError: null as string | null, httpFailed: false, released: false };
    let recordTimer: ReturnType<typeof setTimeout> | null = null;
    const releaseIfCompleted = async (): Promise<void> => {
      try {
        const fresh = await getTrial(sessionId);
        if (fresh.state.status !== "completed" || controller.signal.aborted) {
          return;
        }
        outcome.released = true;
        setState(fresh.state);
        setUtterances((current) => mergeUtterances(current, fresh.utterances));
        setRecordPending(true);
        busyRef.current = false;
        setBusy(false);
        setStatusMessage(null);
      } catch {
        // Keep waiting on the stream; it ends on its own.
      }
    };
    try {
      await sendTrialTurn(
        sessionId,
        { expected_step: state.current_step, expected_version: state.version, ...action },
        {
          onStatus: (message) => {
            stopSlow();
            if (outcome.released) {
              return;
            }
            setStatusMessage(message);
            if (message.startsWith(RECORD_STATUS_PREFIX) && recordTimer === null) {
              recordTimer = setTimeout(() => void releaseIfCompleted(), RECORD_WAIT_RELEASE_MS);
            }
          },
          onUtterance: (utterance) => {
            stopSlow();
            if (utterance.is_user) {
              setDraft("");
            }
            setUtterances((current) => mergeUtterances(current, [utterance]));
          },
          onState: (next) => {
            outcome.gotState = true;
            setState(next);
            setRecordPending(false);
          },
          onError: (message) => {
            outcome.streamError = message;
          }
        },
        controller.signal
      );
    } catch (error) {
      outcome.httpFailed = true;
      if (controller.signal.aborted) {
        return;
      }
      if (error instanceof TrialApiError && error.state !== null) {
        // 409: adopt the server's state, then re-read the transcript.
        setState(error.state);
        if (isResyncConflict(error.code)) {
          setSoftNotice(messageForTrialError(error));
          if (error.code === "trial_busy") {
            await new Promise((resolve) => setTimeout(resolve, 3000));
          }
          await reload();
        } else if (error.code !== "trial_guard_exhausted") {
          setSoftNotice(messageForTrialError(error));
        }
      } else if (error instanceof TrialApiError) {
        if (!error.featureDisabled) {
          setTurnError(messageForTrialError(error));
        }
      } else {
        setTurnError("Mất kết nối tới máy chủ. Đã tải lại trạng thái phiên tòa; nếu cần, bấm “Tiếp tục”.");
        await reload();
      }
    } finally {
      if (recordTimer !== null) {
        clearTimeout(recordTimer);
      }
      stopSlow();
      abortRef.current = null;
      busyRef.current = false;
      setBusy(false);
      setStatusMessage(null);
      setRecordPending(false);
    }

    if (controller.signal.aborted || outcome.httpFailed) {
      return;
    }
    if (outcome.released) {
      // The completed state is on screen; a late failure of the summary stream changes nothing
      // (the record falls back to verbatim on the server).
      if (!outcome.gotState) {
        await reload();
      }
      return;
    }
    // Contract 3.4: an `error` event closes the stream without a state - re-read the real one.
    if (outcome.streamError !== null) {
      setTurnError(outcome.streamError);
      await reload();
    } else if (!outcome.gotState) {
      // The stream ended with neither state nor error: the connection dropped mid-way.
      setTurnError("Kết nối bị ngắt giữa chừng. Đã tải lại trạng thái phiên tòa; nếu cần, bấm “Tiếp tục”.");
      await reload();
    }
  }

  async function handleAbandon(): Promise<void> {
    setMenuOpen(false);
    if (!window.confirm("Bỏ phiên tòa này? Phiên sẽ dừng lại và không thể tiếp tục; diễn biến vẫn được giữ để xem lại.")) {
      return;
    }
    try {
      const next = await abandonTrial(sessionId);
      setState(next);
      setTurnError(null);
    } catch (error) {
      setTurnError(error instanceof TrialApiError ? messageForTrialError(error) : "Không bỏ được phiên. Bạn thử lại nhé.");
    }
  }

  async function handleDelete(): Promise<void> {
    setMenuOpen(false);
    if (!window.confirm("Xóa phiên tòa này? Hồ sơ vụ án và toàn bộ diễn biến sẽ bị xóa vĩnh viễn, không thể hoàn tác.")) {
      return;
    }
    try {
      await deleteTrial(sessionId);
      router.replace("/trial");
    } catch (error) {
      setTurnError(error instanceof TrialApiError ? messageForTrialError(error) : "Không xóa được phiên. Bạn thử lại nhé.");
    }
  }

  if (notFound) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-3 px-6 py-16 text-center">
        <p className="font-serif text-xl font-light text-foreground">Không tìm thấy phiên tòa</p>
        <p className="text-sm text-muted-foreground">Phiên này không tồn tại hoặc đã bị xóa.</p>
        <Button asChild variant="outline" className="rounded-full">
          <Link href="/trial">Về danh sách phiên tòa</Link>
        </Button>
      </div>
    );
  }

  if (detail === null || state === null) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {loadError !== null ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{loadError}</span>
            <Button variant="outline" size="sm" onClick={() => void reload()}>
              Thử lại
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3" aria-busy="true" aria-label="Đang tải phiên tòa">
            {slowRequest.isSlow ? <p className="text-sm text-muted-foreground">{SLOW_REQUEST_NOTICE}</p> : null}
            <div className="h-12 animate-pulse rounded-xl border border-border bg-muted/60" />
            <div className="h-64 animate-pulse rounded-xl border border-border bg-muted/60" />
          </div>
        )}
      </div>
    );
  }

  const lastUtterance = utterances[utterances.length - 1];
  const lastWasPause = lastUtterance !== undefined && lastUtterance.kind === "notice";
  const isInjuryCase = detail.case_file.charge?.dieu === "134";
  const caseFilePanel = <CaseFilePanel caseFile={detail.case_file} isInjuryCase={isInjuryCase} tab={caseTab} onTabChange={setCaseTab} />;

  return (
    <div className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] 2xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
      <div className="flex min-w-0 flex-col gap-5">
        <header className="flex flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <Link href="/trial" className="mb-1 inline-flex min-h-9 items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-3.5 w-3.5" />
                Danh sách phiên tòa
              </Link>
              <h1 className="break-words font-serif text-2xl font-light leading-tight tracking-tight text-foreground">{detail.title}</h1>
              <p className="mt-1 text-xs text-muted-foreground">
                {detail.court.name} · {detail.court.hearing_date} · Vai của bạn: {TRIAL_ROLE_LABELS[detail.user_role] ?? detail.user_role}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button variant="outline" size="sm" className="lg:hidden" onClick={() => setDrawerOpen(true)} aria-haspopup="dialog">
                <FolderOpen className="h-4 w-4" />
                <span className="hidden sm:inline">Hồ sơ vụ án</span>
                <span className="sr-only sm:hidden">Hồ sơ vụ án</span>
              </Button>
              <div className="relative">
                <button
                  type="button"
                  aria-label="Tùy chọn phiên tòa"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((value) => !value)}
                  className="flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  <MoreHorizontal className="h-5 w-5" />
                </button>
                {menuOpen ? (
                  <div role="menu" className="absolute right-0 top-12 z-30 flex w-52 flex-col rounded-lg border border-border bg-popover p-1 shadow-lg">
                    {state.status === "completed" ? (
                      <Link role="menuitem" href={`/trial/${sessionId}/record`} className="flex min-h-11 items-center gap-2 rounded-md px-3 text-sm hover:bg-accent/20">
                        <FileText className="h-4 w-4" />
                        Xem biên bản
                      </Link>
                    ) : null}
                    {state.status === "active" ? (
                      <button role="menuitem" type="button" onClick={() => void handleAbandon()} disabled={busy} className="flex min-h-11 items-center gap-2 rounded-md px-3 text-left text-sm hover:bg-accent/20 disabled:opacity-50">
                        <XCircle className="h-4 w-4" />
                        Bỏ phiên
                      </button>
                    ) : null}
                    <button role="menuitem" type="button" onClick={() => void handleDelete()} disabled={busy} className="flex min-h-11 items-center gap-2 rounded-md px-3 text-left text-sm text-red-700 hover:bg-red-50 disabled:opacity-50">
                      <Trash2 className="h-4 w-4" />
                      Xóa phiên
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
          <StepBar steps={detail.steps} currentStep={state.current_step} completed={state.status === "completed"} />
        </header>

        <div className="min-w-0" aria-live="polite" aria-relevant="additions">
          {utterances.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">Phiên tòa chưa có diễn biến nào.</p>
          ) : (
            <Transcript utterances={utterances} steps={detail.steps} participants={detail.participants} />
          )}
          {busy ? (
            <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground" data-testid="trial-status">
              <span className="flex gap-1" aria-hidden="true">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
              </span>
              {statusMessage ?? "Đang xử lý..."}
            </div>
          ) : null}
          {busy && slowRequest.isSlow ? <p className="mt-2 text-xs text-muted-foreground">{SLOW_REQUEST_NOTICE}</p> : null}
          <div ref={endRef} />
        </div>

        <div ref={composerRef} data-testid="trial-composer-dock" className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t border-border bg-background/95 px-4 pb-4 pt-3 backdrop-blur sm:-mx-6 sm:px-6">
          {newBelow ? (
            <button
              type="button"
              data-testid="trial-new-below"
              onClick={() => scrollToLatest()}
              className="absolute -top-14 left-1/2 flex min-h-10 -translate-x-1/2 items-center gap-1.5 rounded-full border border-primary/20 bg-card px-4 text-sm font-medium text-foreground shadow-md transition-colors hover:bg-accent/20"
            >
              Có lời mới
              <ArrowDown className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : null}
          {softNotice !== null ? (
            <p role="status" data-testid="trial-soft-notice" className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              {softNotice}
            </p>
          ) : null}
          {turnError !== null ? (
            <div role="alert" data-testid="trial-error" className="flex flex-wrap items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1">{turnError}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => {
                  setTurnError(null);
                  void reload();
                }}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Tải lại trạng thái
              </Button>
            </div>
          ) : null}
          <TrialComposer
            recordPending={recordPending}
            sessionId={sessionId}
            state={state}
            userRole={detail.user_role}
            steps={detail.steps}
            participants={detail.participants}
            busy={busy}
            statusMessage={statusMessage}
            lastWasPause={lastWasPause}
            indictmentText={detail.case_file.indictment_text ?? null}
            draft={draft}
            onDraftChange={setDraft}
            onAction={(action) => void runAction(action)}
            onAbandon={() => void handleAbandon()}
            onDelete={() => void handleDelete()}
          />
        </div>
      </div>

      <aside aria-label="Hồ sơ vụ án" className="hidden min-w-0 lg:sticky lg:top-12 lg:block lg:max-h-[calc(100vh-8rem)] lg:self-start lg:overflow-hidden">
        <div className="flex max-h-[calc(100vh-8rem)] flex-col rounded-xl border border-primary/[0.08] bg-card p-4 shadow-[0_2px_20px_rgba(30,36,96,0.05)]">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-foreground">Hồ sơ vụ án</h2>
            <button
              ref={expandButtonRef}
              type="button"
              aria-label="Mở rộng hồ sơ vụ án"
              aria-haspopup="dialog"
              onClick={() => setExpandedOpen(true)}
              className="flex min-h-9 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/15 hover:text-foreground"
            >
              <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
              Mở rộng
            </button>
          </div>
          {caseFilePanel}
        </div>
      </aside>

      {expandedOpen ? (
        <div className="fixed inset-0 z-50 hidden items-center justify-center px-6 py-8 lg:flex" role="dialog" aria-modal="true" aria-label="Hồ sơ vụ án (mở rộng)">
          <button type="button" aria-label="Đóng hồ sơ mở rộng (nhấn ra ngoài)" tabIndex={-1} onClick={() => setExpandedOpen(false)} className="absolute inset-0 bg-black/40" />
          <div data-testid="trial-casefile-expanded" className="relative flex h-full max-h-[88vh] w-full max-w-[720px] flex-col rounded-xl bg-card p-6 shadow-2xl">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="font-serif text-xl font-light tracking-tight text-foreground">Hồ sơ vụ án</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">{detail.title}</p>
              </div>
              <button
                ref={expandedCloseRef}
                type="button"
                aria-label="Đóng hồ sơ mở rộng"
                onClick={() => setExpandedOpen(false)}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-accent/20 hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <CaseFilePanel caseFile={detail.case_file} isInjuryCase={isInjuryCase} tab={caseTab} onTabChange={setCaseTab} wide />
            </div>
          </div>
        </div>
      ) : null}

      {drawerOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Hồ sơ vụ án">
          <button type="button" aria-label="Đóng hồ sơ (nhấn ra ngoài)" onClick={() => setDrawerOpen(false)} className="absolute inset-0 bg-black/40" />
          <div className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-card p-4 shadow-xl">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">Hồ sơ vụ án</h2>
              <button
                ref={drawerCloseRef}
                type="button"
                aria-label="Đóng hồ sơ vụ án"
                onClick={() => setDrawerOpen(false)}
                className="flex h-11 w-11 items-center justify-center rounded-full text-muted-foreground hover:bg-accent/20 hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{caseFilePanel}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
