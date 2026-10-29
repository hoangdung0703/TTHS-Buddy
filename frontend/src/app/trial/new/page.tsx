"use client";

import { AlertCircle, ArrowLeft, Check, Info } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ArticlePill } from "@/components/trial/ArticlePill";
import { TrialShell } from "@/components/trial/TrialShell";
import { Button } from "@/components/ui/button";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { createTrial, getTrials, TrialApiError } from "@/lib/api";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
import { caseCreationBlockedReason, isCaseLimitCode, LAW_VERSION_BLTTHS, messageForTrialError } from "@/lib/trialRules";
import type { TrialConfig, TrialUserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RoleCard {
  key: string;
  label: string;
  description: string;
  basis?: { dieu: string; label: string }[];
}

// The six roles of the design (THIET-KE Mục 7, màn 2A). Only the ones listed in config.user_roles
// are selectable; the rest are shown dimmed as "Sắp có". A role the server enables but this list
// does not know is not offered: the hearing screen would not know how to present it.
const ROLE_CARDS: RoleCard[] = [
  {
    key: "ksv",
    label: "Kiểm sát viên",
    description: "Công bố cáo trạng, xét hỏi, luận tội và đối đáp để bảo vệ quan điểm truy tố.",
    basis: [{ dieu: "42", label: "Điều 42 BLTTHS" }]
  },
  {
    key: "luat_su",
    label: "Luật sư bào chữa",
    description: "Xét hỏi, trình bày bài bào chữa và đối đáp để bảo vệ quyền lợi của bị cáo.",
    basis: [{ dieu: "73", label: "Điều 73 BLTTHS" }]
  },
  {
    key: "bi_cao",
    label: "Bị cáo",
    description: "Trả lời xét hỏi, tự bào chữa và nói lời sau cùng.",
    basis: [{ dieu: "61", label: "Điều 61 BLTTHS" }]
  },
  { key: "chu_toa", label: "Chủ tọa", description: "Điều khiển phiên tòa theo đúng trình tự tố tụng." },
  // Contract 3.1: "Điều 47, 258 BLTTHS", one pill per article so each opens its own text.
  {
    key: "thu_ky",
    label: "Thư ký phiên tòa",
    description: "Báo cáo sự có mặt, ghi chép và tự viết biên bản phiên tòa.",
    basis: [
      { dieu: "47", label: "Điều 47" },
      { dieu: "258", label: "Điều 258 BLTTHS" }
    ]
  },
  // Contract 3.1: no article pill on this card.
  { key: "nguoi_xem", label: "Người xem", description: "Theo dõi trọn một phiên tòa do hệ thống đóng mọi vai." }
];

type Phase = "form" | "creating" | "failed" | "cancelled";

function Toggle({
  id,
  checked,
  onChange,
  label,
  hint,
  disabled
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-background px-4 py-3">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium text-foreground">
          {label}
        </label>
        <p id={`${id}-hint`} className="mt-0.5 text-xs text-muted-foreground">
          {hint}
        </p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={`${id}-hint`}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50",
          checked ? "bg-primary" : "bg-muted"
        )}
      >
        <span className="sr-only">{checked ? "Có" : "Không"}</span>
        <span
          aria-hidden="true"
          className={cn("inline-block h-5 w-5 rounded-full bg-card shadow transition-transform", checked ? "translate-x-6" : "translate-x-1")}
        />
      </button>
    </div>
  );
}

export default function NewTrialPage() {
  const router = useRouter();
  const [config, setConfig] = useState<TrialConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [role, setRole] = useState<TrialUserRole | null>(null);
  const [crimeKey, setCrimeKey] = useState<string | null>(null);
  const [victimPresent, setVictimPresent] = useState(true);
  const [witnessCount, setWitnessCount] = useState(1);
  const [hasRelatedParty, setHasRelatedParty] = useState(false);
  const [phase, setPhase] = useState<Phase>("form");
  const [statusLines, setStatusLines] = useState<string[]>([]);
  const [error, setError] = useState<{ message: string; code: string | null } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const slowRequest = useSlowRequestNotice();
  const { start: startSlow, stop: stopSlow } = slowRequest;

  const load = useCallback(async (): Promise<void> => {
    setLoadError(null);
    startSlow();
    try {
      const result = await getTrials();
      setConfig(result.config);
    } catch (loadFailure) {
      if (!(loadFailure instanceof TrialApiError && loadFailure.featureDisabled)) {
        setLoadError(loadFailure instanceof TrialApiError ? messageForTrialError(loadFailure) : "Không tải được cấu hình phiên tòa.");
      }
    } finally {
      stopSlow();
    }
  }, [startSlow, stopSlow]);

  useEffect(() => {
    void load();
  }, [load]);

  // Leaving the page mid-creation drops the stream. The server may still finish and store the case
  // (its write is shielded); the list page shows it if so.
  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (phase !== "creating") {
      return;
    }
    setElapsed(0);
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  const roleEnabled = (key: string) => config?.user_roles.includes(key) ?? false;
  const maxWitnesses = config?.limits.max_witnesses ?? 2;
  const blockedReason = config !== null ? caseCreationBlockedReason(config) : null;
  const blocked = blockedReason !== null;
  const canSubmit = config !== null && role !== null && crimeKey !== null && !blocked && phase !== "creating";

  async function handleCreate(): Promise<void> {
    if (!canSubmit || role === null || crimeKey === null) {
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase("creating");
    setError(null);
    setStatusLines([]);
    startSlow();

    // Filled from inside the stream callbacks (a plain `let` would be narrowed to null by TS).
    const outcome: { sessionId: string | null; streamError: string | null } = { sessionId: null, streamError: null };
    try {
      await createTrial(
        { crime_key: crimeKey, user_role: role, victim_present: victimPresent, witness_count: witnessCount, has_related_party: hasRelatedParty },
        {
          onStatus: (message) => {
            stopSlow();
            setStatusLines((lines) => (lines.includes(message) ? lines : [...lines, message]));
          },
          onSession: (event) => {
            outcome.sessionId = event.session_id;
          },
          onError: (message) => {
            outcome.streamError = message;
          }
        },
        controller.signal
      );
    } catch (createError) {
      if (controller.signal.aborted) {
        return;
      }
      stopSlow();
      setPhase("failed");
      setError(
        createError instanceof TrialApiError
          ? { message: messageForTrialError(createError), code: createError.code }
          : { message: "Mất kết nối tới máy chủ. Bạn thử lại nhé.", code: null }
      );
      return;
    } finally {
      stopSlow();
      abortRef.current = null;
    }

    if (outcome.sessionId !== null) {
      // The session exists even if a later event failed; the hearing page re-reads its state.
      router.replace(`/trial/${outcome.sessionId}`);
      return;
    }
    setPhase("failed");
    setError({ message: outcome.streamError ?? "Chưa dựng được hồ sơ vụ án. Bạn thử lại nhé.", code: null });
  }

  function handleCancel(): void {
    abortRef.current?.abort();
    abortRef.current = null;
    stopSlow();
    setPhase("cancelled");
  }

  const creating = phase === "creating";

  return (
    <TrialShell title="Phiên tòa giả định">
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <Link href="/trial" className="mb-4 inline-flex min-h-11 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Danh sách phiên tòa
        </Link>
        <h1 className="mb-1.5 font-serif text-3xl font-light tracking-tight text-foreground">Tạo phiên tòa mới</h1>
        <p className="mb-8 text-sm font-light text-muted-foreground">
          Chọn vai và các yếu tố của vụ án. Hệ thống dựng hồ sơ vụ án giả định trong khoảng 10–25 giây.
        </p>

        {loadError !== null ? (
          <div role="alert" className="mb-6 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{loadError}</span>
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {config === null && loadError === null ? (
          <div className="flex flex-col gap-3" aria-busy="true" aria-label="Đang tải cấu hình">
            {slowRequest.isSlow ? <p className="text-sm text-muted-foreground">{SLOW_REQUEST_NOTICE}</p> : null}
            <div className="h-40 animate-pulse rounded-xl border border-border bg-muted/60" />
            <div className="h-40 animate-pulse rounded-xl border border-border bg-muted/60" />
          </div>
        ) : null}

        {config !== null ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void handleCreate();
            }}
            className="flex flex-col gap-8"
          >
            {blocked ? (
              <p role="status" data-testid="trial-create-blocked" className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                {blockedReason}
              </p>
            ) : null}

            <fieldset disabled={creating} className="min-w-0">
              <legend className="mb-3 text-sm font-semibold text-foreground">1. Vai của bạn</legend>
              <div role="radiogroup" aria-label="Vai của bạn" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {ROLE_CARDS.map((card) => {
                  const enabled = roleEnabled(card.key);
                  const selected = role === card.key;
                  return (
                    <div
                      key={card.key}
                      data-testid={`role-${card.key}`}
                      className={cn(
                        "relative flex min-w-0 flex-col gap-2 rounded-xl border p-4 text-left transition-colors",
                        enabled ? "bg-card" : "border-dashed bg-muted/30 opacity-60",
                        selected ? "border-primary ring-2 ring-primary/30" : "border-border"
                      )}
                    >
                      <button
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        aria-disabled={!enabled}
                        disabled={!enabled}
                        onClick={() => enabled && setRole(card.key as TrialUserRole)}
                        className="absolute inset-0 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed"
                      >
                        <span className="sr-only">
                          {card.label}
                          {enabled ? "" : " (Sắp có)"}
                        </span>
                      </button>
                      <div className="pointer-events-none flex items-center justify-between gap-2">
                        <span className="font-medium text-foreground">{card.label}</span>
                        {selected ? (
                          <Check className="h-4 w-4 text-primary" aria-hidden="true" />
                        ) : !enabled ? (
                          <span className="rounded-full bg-muted px-2 py-0.5 text-[0.7rem] font-medium text-muted-foreground">Sắp có</span>
                        ) : null}
                      </div>
                      <p className="pointer-events-none text-xs leading-relaxed text-muted-foreground">{card.description}</p>
                      {enabled && card.basis ? (
                        <div className="relative z-10 flex flex-wrap gap-1.5 self-start">
                          {card.basis.map((basis) => (
                            <ArticlePill key={basis.dieu} dieu={basis.dieu} lawVersion={LAW_VERSION_BLTTHS} label={basis.label} />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </fieldset>

            <fieldset disabled={creating} className="min-w-0">
              <legend className="mb-3 text-sm font-semibold text-foreground">2. Tội danh</legend>
              <div role="radiogroup" aria-label="Tội danh" className="flex flex-wrap gap-2">
                {config.crimes.map((crime) => {
                  const selected = crimeKey === crime.crime_key;
                  return (
                    <button
                      key={crime.crime_key}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setCrimeKey(crime.crime_key)}
                      className={cn(
                        "inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-full border px-4 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        selected
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-secondary text-secondary-foreground hover:bg-accent/30"
                      )}
                    >
                      <span className="break-words">
                        {crime.crime_name} <span className="opacity-75">(Điều {crime.dieu} BLHS)</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <fieldset disabled={creating} className="flex min-w-0 flex-col gap-3">
              <legend className="mb-3 text-sm font-semibold text-foreground">3. Người tham gia tố tụng</legend>
              <Toggle
                id="trial-victim-present"
                checked={victimPresent}
                onChange={setVictimPresent}
                label="Bị hại có mặt tại phiên tòa"
                hint="Tắt: bị hại vắng mặt và có đơn xin xét xử vắng mặt; vụ án vẫn có bị hại nhưng không ai hỏi bị hại tại phiên."
              />
              <div className="rounded-lg border border-border bg-background px-4 py-3">
                <p id="trial-witness-label" className="text-sm font-medium text-foreground">
                  Số người làm chứng
                </p>
                <div role="radiogroup" aria-labelledby="trial-witness-label" className="mt-2 flex gap-2">
                  {Array.from({ length: maxWitnesses + 1 }, (_, count) => (
                    <button
                      key={count}
                      type="button"
                      role="radio"
                      aria-checked={witnessCount === count}
                      onClick={() => setWitnessCount(count)}
                      className={cn(
                        "flex h-11 w-14 items-center justify-center rounded-md border text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        witnessCount === count
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-card text-foreground hover:bg-accent/20"
                      )}
                    >
                      {count}
                    </button>
                  ))}
                </div>
              </div>
              <Toggle
                id="trial-related-party"
                checked={hasRelatedParty}
                onChange={setHasRelatedParty}
                label="Có người có quyền lợi, nghĩa vụ liên quan"
                hint="Ví dụ: người nhận cầm cố hoặc mua lại tài sản liên quan đến vụ án."
              />
            </fieldset>

            {phase === "creating" ? (
              <div role="status" aria-live="polite" data-testid="trial-create-progress" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5">
                <div className="flex items-center gap-2 text-sm text-foreground">
                  <span className="flex gap-1" aria-hidden="true">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
                  </span>
                  <span>{statusLines[statusLines.length - 1] ?? "Đang gửi yêu cầu..."}</span>
                  <span className="ml-auto text-xs tabular-nums text-muted-foreground">{elapsed}s</span>
                </div>
                {statusLines.length > 1 ? (
                  <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
                    {statusLines.slice(0, -1).map((line) => (
                      <li key={line} className="flex items-center gap-1.5">
                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {slowRequest.isSlow ? <p className="text-xs text-muted-foreground">{SLOW_REQUEST_NOTICE}</p> : null}
                <Button type="button" variant="outline" size="sm" className="self-start" onClick={handleCancel}>
                  Hủy tạo vụ án
                </Button>
              </div>
            ) : null}

            {phase === "failed" && error !== null ? (
              <div
                role="alert"
                data-testid="trial-create-error"
                data-code={error.code ?? ""}
                className={cn(
                  "flex items-start gap-2 rounded-lg border px-4 py-3 text-sm",
                  isCaseLimitCode(error.code) ? "border-border bg-muted/40 text-foreground" : "border-red-200 bg-red-50 text-red-700"
                )}
              >
                {isCaseLimitCode(error.code) ? (
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                ) : (
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                )}
                <span>{error.message}</span>
              </div>
            ) : null}

            {phase === "cancelled" ? (
              <p role="status" className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                Đã hủy. Nếu máy chủ đã kịp dựng xong hồ sơ, phiên tòa vẫn sẽ có trong{" "}
                <Link href="/trial" className="font-medium text-primary underline-offset-2 hover:underline">
                  danh sách
                </Link>
                .
              </p>
            ) : null}

            {phase !== "creating" ? (
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" className="rounded-full" disabled={!canSubmit}>
                  {phase === "failed" ? "Thử tạo lại" : "Tạo vụ án"}
                </Button>
                {role === null || crimeKey === null ? (
                  <p className="text-xs text-muted-foreground">Chọn vai và tội danh để tạo vụ án.</p>
                ) : null}
              </div>
            ) : null}
          </form>
        ) : null}
      </div>
    </TrialShell>
  );
}
