"use client";

import { FileText, Gavel, Play, Plus, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { TrialShell } from "@/components/trial/TrialShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { abandonTrial, deleteTrial, getTrials, TrialApiError } from "@/lib/api";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
import { messageForTrialError, TRIAL_ROLE_LABELS, TRIAL_STATUS_LABELS, TRIAL_TOTAL_STEPS } from "@/lib/trialRules";
import type { TrialConfig, TrialSummary } from "@/lib/types";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function statusBadgeClass(status: string): string {
  if (status === "active") {
    return "bg-primary/10 text-primary";
  }
  if (status === "completed") {
    return "bg-accent/20 text-accent-foreground";
  }
  return "bg-muted text-muted-foreground";
}

// Why "Tạo phiên mới" is locked, or null when it is not.
function createBlockedReason(config: TrialConfig): string | null {
  if (config.remaining.cases_today <= 0) {
    return `Hôm nay bạn đã tạo đủ ${config.limits.max_cases_per_day} vụ án. Bạn quay lại vào ngày mai nhé.`;
  }
  if (config.remaining.active_sessions <= 0) {
    return `Bạn đang có ${config.limits.max_active_sessions} phiên dở dang. Hãy hoàn thành, bỏ hoặc xóa bớt một phiên để tạo phiên mới.`;
  }
  return null;
}

export default function TrialListPage() {
  const [sessions, setSessions] = useState<TrialSummary[] | null>(null);
  const [config, setConfig] = useState<TrialConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const { isSlow, start: startSlow, stop: stopSlow } = useSlowRequestNotice();

  const load = useCallback(async (): Promise<void> => {
    setLoadError(null);
    startSlow();
    try {
      const result = await getTrials();
      setSessions(result.sessions);
      setConfig(result.config);
    } catch (error) {
      // The feature-off 404 is handled by TrialShell (redirect); anything else is a load error.
      if (!(error instanceof TrialApiError && error.featureDisabled)) {
        setLoadError(error instanceof TrialApiError ? messageForTrialError(error) : "Không tải được danh sách phiên tòa.");
      }
    } finally {
      stopSlow();
    }
  }, [startSlow, stopSlow]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAbandon(session: TrialSummary): Promise<void> {
    if (!window.confirm(`Bỏ phiên "${session.title}"? Phiên sẽ dừng lại và không thể tiếp tục, nhưng vẫn còn trong danh sách.`)) {
      return;
    }
    setBusyId(session.session_id);
    setActionError(null);
    try {
      await abandonTrial(session.session_id);
    } catch (error) {
      setActionError(error instanceof TrialApiError ? messageForTrialError(error) : "Không bỏ được phiên. Bạn thử lại nhé.");
    } finally {
      setBusyId(null);
      void load();
    }
  }

  async function handleDelete(session: TrialSummary): Promise<void> {
    if (!window.confirm(`Xóa phiên "${session.title}"? Hồ sơ vụ án và toàn bộ diễn biến sẽ bị xóa vĩnh viễn, không thể hoàn tác.`)) {
      return;
    }
    setBusyId(session.session_id);
    setActionError(null);
    try {
      await deleteTrial(session.session_id);
    } catch (error) {
      setActionError(error instanceof TrialApiError ? messageForTrialError(error) : "Không xóa được phiên. Bạn thử lại nhé.");
    } finally {
      setBusyId(null);
      void load();
    }
  }

  const blockedReason = config !== null ? createBlockedReason(config) : null;

  return (
    <TrialShell title="Phiên tòa giả định">
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="mb-1.5 font-serif text-3xl font-light tracking-tight text-foreground">Phiên tòa giả định</h1>
            <p className="max-w-xl text-sm font-light text-muted-foreground">
              Thực hành một phiên tòa hình sự sơ thẩm theo đúng trình tự BLTTHS. Bạn đóng một vai, AI đóng các vai còn lại.
            </p>
          </div>
          {blockedReason === null && config !== null ? (
            <Button asChild className="rounded-full">
              <Link href="/trial/new">
                <Plus className="h-4 w-4" />
                Tạo phiên mới
              </Link>
            </Button>
          ) : (
            <Button className="rounded-full" disabled aria-describedby={blockedReason ? "trial-create-blocked" : undefined}>
              <Plus className="h-4 w-4" />
              Tạo phiên mới
            </Button>
          )}
        </div>

        {config !== null ? (
          <div data-testid="trial-quota" className="mb-6 flex flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:gap-6">
            <span>
              Vụ án còn tạo được hôm nay:{" "}
              <strong className="font-medium text-foreground">
                {config.remaining.cases_today}/{config.limits.max_cases_per_day}
              </strong>
            </span>
            <span>
              Phiên dở dang còn mở thêm được:{" "}
              <strong className="font-medium text-foreground">
                {config.remaining.active_sessions}/{config.limits.max_active_sessions}
              </strong>
            </span>
          </div>
        ) : null}

        {blockedReason !== null ? (
          <p id="trial-create-blocked" className="mb-6 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            {blockedReason}
          </p>
        ) : null}

        {loadError !== null ? (
          <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{loadError}</span>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {actionError !== null ? (
          <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {actionError}
          </p>
        ) : null}

        {sessions === null && loadError === null ? (
          <div className="flex flex-col gap-3" aria-busy="true" aria-label="Đang tải danh sách phiên tòa">
            {isSlow ? <p className="text-sm text-muted-foreground">{SLOW_REQUEST_NOTICE}</p> : null}
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-28 animate-pulse rounded-xl border border-border bg-muted/60" />
            ))}
          </div>
        ) : null}

        {sessions !== null && sessions.length === 0 ? (
          <div data-testid="trial-empty" className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-6 py-16 text-center">
            <Gavel className="h-8 w-8 text-muted-foreground" strokeWidth={1.4} aria-hidden="true" />
            <p className="font-serif text-lg font-light text-foreground">Bạn chưa có phiên tòa nào</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Chọn vai (Kiểm sát viên hoặc Luật sư bào chữa) và tội danh, hệ thống sẽ dựng một hồ sơ vụ án giả định để bạn
              thực hành đủ 11 bước của phiên tòa sơ thẩm, từ khai mạc tới tuyên án. Khi xong, bạn có biên bản phiên tòa để xem lại.
            </p>
          </div>
        ) : null}

        {sessions !== null && sessions.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {sessions.map((session) => {
              const busy = busyId === session.session_id;
              return (
                <li
                  key={session.session_id}
                  data-testid="trial-session"
                  className="flex min-w-0 flex-col gap-3 rounded-xl border border-primary/[0.08] bg-card p-5 shadow-[0_2px_20px_rgba(30,36,96,0.05)]"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h2 className="break-words font-serif text-lg font-light tracking-tight text-foreground">{session.title}</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {config?.crimes.find((crime) => crime.crime_key === session.crime_key)?.crime_name ?? session.crime_key}
                        {" · "}Vai: {TRIAL_ROLE_LABELS[session.user_role] ?? session.user_role}
                      </p>
                    </div>
                    <Badge className={statusBadgeClass(session.status)}>{TRIAL_STATUS_LABELS[session.status] ?? session.status}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Bước {session.current_step}/{TRIAL_TOTAL_STEPS} · Cập nhật {formatDate(session.updated_at)}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {session.status === "active" ? (
                      <Button asChild size="sm" className="rounded-full">
                        <Link href={`/trial/${session.session_id}`}>
                          <Play className="h-4 w-4" />
                          Tiếp tục
                        </Link>
                      </Button>
                    ) : (
                      <Button asChild size="sm" variant="outline" className="rounded-full">
                        <Link href={`/trial/${session.session_id}`}>Xem diễn biến</Link>
                      </Button>
                    )}
                    {session.status === "completed" ? (
                      <Button asChild size="sm" variant="outline" className="rounded-full">
                        <Link href={`/trial/${session.session_id}/record`}>
                          <FileText className="h-4 w-4" />
                          Xem biên bản
                        </Link>
                      </Button>
                    ) : null}
                    {session.status === "active" ? (
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => void handleAbandon(session)}>
                        <XCircle className="h-4 w-4" />
                        Bỏ phiên
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void handleDelete(session)}
                      className="hover:bg-red-100 hover:text-red-700"
                    >
                      <Trash2 className="h-4 w-4" />
                      Xóa
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </TrialShell>
  );
}
