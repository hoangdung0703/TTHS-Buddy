"use client";

// Minigame "Tôi hỏi bạn trả lời" - lấy ngẫu nhiên từ toàn bộ pool tự luận (POST /api/essay/question
// không kèm category), chấm bằng POST /api/essay/submit thật. Nút "Câu khác" (skip) chỉ đổi câu
// (exclude_question_id = câu hiện tại), KHÔNG chấm điểm và KHÔNG tính vào lịch sử/thống kê -
// quyết định đã chốt trong requirements.md ("Phase 5a/5b v2": nghiêng về hoàn toàn bỏ qua).
import { Check, ChevronRight, Minus, RefreshCw, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getPracticeQuestionV2, submitEssay } from "@/lib/api";
import type { EssaySubmitResponse, PracticeQuestionV2 } from "@/lib/types";
import { cn } from "@/lib/utils";

type Phase = "answering" | "reviewing";

// Chỉ đếm số câu đã thực sự làm trong phiên hiện tại (không tính "Câu khác") - dùng cho
// progress pip bar phía trên, tương tự Figma export (current/total của useRotatingQuestion).
const PIP_TRACK_LENGTH = 5;

export default function EssayPracticePage() {
  const [question, setQuestion] = useState<PracticeQuestionV2 | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [answer, setAnswer] = useState("");
  const [phase, setPhase] = useState<Phase>("answering");
  const [result, setResult] = useState<EssaySubmitResponse | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    loadQuestion();
  }, []);

  useEffect(() => {
    if (phase === "answering") textareaRef.current?.focus();
  }, [phase]);

  function loadQuestion(excludeQuestionId?: string): void {
    setLoadError(false);
    getPracticeQuestionV2(excludeQuestionId)
      .then((next) => {
        setQuestion(next);
        setAnswer("");
        setResult(null);
        setPhase("answering");
      })
      .catch(() => setLoadError(true));
  }

  async function handleSubmit(): Promise<void> {
    if (answer.trim().length === 0 || question === null) return;
    setIsSubmitting(true);
    try {
      const response = await submitEssay({ question_id: question.question_id, user_answer: answer });
      setResult(response);
      setPhase("reviewing");
      setAnsweredCount((count) => count + 1);
    } finally {
      setIsSubmitting(false);
    }
  }

  // "Câu khác": bỏ qua hoàn toàn, không chấm điểm, không tăng answeredCount.
  function handleSkip(): void {
    loadQuestion(question?.question_id);
  }

  function handleNextQuestion(): void {
    loadQuestion(question?.question_id);
  }

  const pipCurrent = (answeredCount % PIP_TRACK_LENGTH) + 1;

  return (
    <AuthenticatedLayout title="Tôi hỏi · Bạn trả lời">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <Link href="/essay" className="text-sm text-muted-foreground hover:text-foreground">
            ← Tự luận
          </Link>
          <span className="text-xs text-muted-foreground">Đã làm trong phiên này: {answeredCount}</span>
        </div>

        <div className="mb-8 flex items-center justify-between">
          <div className="flex gap-1.5">
            {Array.from({ length: PIP_TRACK_LENGTH }).map((_, dotIndex) => (
              <div
                key={dotIndex}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-200",
                  dotIndex === pipCurrent - 1 ? "w-6 bg-primary" : "w-2",
                  dotIndex < pipCurrent ? "bg-primary" : "bg-primary/15"
                )}
              />
            ))}
          </div>
          <span className="text-xs text-muted-foreground">
            {pipCurrent} / {PIP_TRACK_LENGTH}
          </span>
        </div>

        {loadError ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Không tải được câu hỏi.</span>
            <Button variant="outline" size="sm" onClick={() => loadQuestion()}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {question === null && !loadError ? <div className="h-64 animate-pulse rounded-2xl border border-border bg-muted/60" /> : null}

        {question !== null && phase === "answering" && (
          <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_4px_24px_rgba(30,36,96,0.07)]">
            <div className="border-b border-border/70 p-6 sm:p-8">
              <div className="mb-5 flex items-center justify-between">
                <span className="text-[0.68rem] font-bold uppercase tracking-[0.14em] text-accent">Tôi hỏi · Bạn trả lời</span>
                <Badge variant="outline">{question.bank_label}</Badge>
              </div>

              <p className="mb-3 font-serif text-xl font-light leading-snug tracking-tight text-foreground sm:text-2xl">
                {question.question_text}
              </p>

              <span className="inline-flex items-center gap-1 rounded-md border border-primary/10 bg-primary/[0.06] px-2 py-0.5 text-xs text-primary/80">
                {question.legal_ref}
              </span>
            </div>

            <div className="p-5 sm:p-7">
              <div className="relative">
                <textarea
                  ref={textareaRef}
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  placeholder="Viết câu trả lời của bạn ở đây…"
                  rows={7}
                  className="w-full resize-y rounded-xl border border-primary/[0.12] bg-primary/[0.025] p-4 pb-10 text-sm leading-relaxed text-foreground outline-none transition-colors focus:border-primary/40"
                />
                <span className="pointer-events-none absolute bottom-2.5 right-3.5 text-xs text-muted-foreground/50">
                  {answer.length} ký tự
                </span>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  disabled={answer.trim().length === 0 || isSubmitting}
                  className={cn(
                    "flex min-h-11 items-center gap-2 rounded-full px-6 py-2.5 text-sm font-medium text-primary-foreground shadow-[0_3px_14px_rgba(30,36,96,0.22)] transition-colors",
                    answer.trim().length === 0 || isSubmitting ? "cursor-not-allowed bg-primary/20" : "bg-primary hover:opacity-90"
                  )}
                >
                  <Send size={14} strokeWidth={1.8} />
                  {isSubmitting ? "Đang chấm..." : "Nộp câu trả lời"}
                </button>

                <button
                  type="button"
                  onClick={handleSkip}
                  className="flex min-h-11 items-center gap-2 rounded-full border border-primary/15 px-5 py-2.5 text-sm text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
                >
                  <RefreshCw size={13} strokeWidth={1.8} />
                  Câu khác
                </button>
              </div>

              <p className="mt-3 text-xs text-muted-foreground/60">Hãy tự viết trước khi xem đáp án — đó là cách học hiệu quả nhất.</p>
            </div>
          </div>
        )}

        {question !== null && phase === "reviewing" && result !== null && (
          <div className="flex flex-col gap-5">
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-4">
                <p className="flex-1 font-serif text-base italic leading-relaxed text-foreground/80">{question.question_text}</p>
                <span className="whitespace-nowrap pt-0.5 text-[0.68rem] font-semibold uppercase tracking-wider text-accent">
                  Câu hỏi
                </span>
              </div>
            </div>

            <div className="rounded-2xl border border-primary/[0.09] bg-primary/[0.03] p-5">
              <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Câu trả lời của bạn</p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{answer}</p>
            </div>

            <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_4px_24px_rgba(30,36,96,0.07)]">
              <div className="flex items-center justify-between border-b border-border/70 bg-primary/[0.02] px-6 py-4">
                <div className="flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/[0.08] text-primary">
                    <Check size={13} strokeWidth={1.8} />
                  </span>
                  <span className="text-sm font-semibold text-foreground">Nhận xét từ trợ lý AI</span>
                </div>
                <Badge variant="outline">{question.legal_ref}</Badge>
              </div>

              <div className="space-y-4 p-6">
                <p className="text-sm leading-loose text-foreground/85">{result.feedback}</p>

                <div>
                  <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Các điểm cần có</p>
                  <ul className="flex flex-col gap-1.5">
                    {result.matched_points.map((point) => (
                      <li key={point} className="flex items-start gap-2.5 rounded-md border border-primary/[0.08] bg-primary/[0.04] p-2.5">
                        <Check size={13} strokeWidth={2.5} className="mt-0.5 shrink-0 text-primary" />
                        <span className="text-sm text-foreground">{point}</span>
                      </li>
                    ))}
                    {result.missing_points.map((point) => (
                      <li key={point} className="flex items-start gap-2.5 rounded-md border border-accent/20 bg-accent/[0.08] p-2.5">
                        <Minus size={13} strokeWidth={2.5} className="mt-0.5 shrink-0 text-accent" />
                        <span className="text-sm font-medium text-accent">{point}</span>
                      </li>
                    ))}
                    {result.matched_points.length === 0 && result.missing_points.length === 0 && (
                      <li className="flex items-start gap-2.5 p-2.5">
                        <ChevronRight size={13} className="mt-0.5 shrink-0 text-muted-foreground" />
                        <span className="text-sm text-muted-foreground">Không có điểm rubric nào cho câu này.</span>
                      </li>
                    )}
                  </ul>
                </div>

                <div className="flex gap-5 border-t border-border/70 pt-3">
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Check size={11} strokeWidth={2.5} className="text-primary" /> Đã đề cập
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Minus size={11} strokeWidth={2.5} className="text-accent" /> Cần bổ sung
                  </span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-3 pt-1">
              <button
                type="button"
                onClick={handleNextQuestion}
                className="flex min-h-11 items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground shadow-[0_3px_14px_rgba(30,36,96,0.22)] transition-opacity hover:opacity-90"
              >
                <RefreshCw size={14} strokeWidth={1.8} />
                Câu tiếp theo
              </button>

              <Link
                href="/essay"
                className="flex min-h-11 items-center gap-2 rounded-full border border-primary/15 px-5 py-2.5 text-sm text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
              >
                Chọn ngân hàng khác
              </Link>
            </div>
          </div>
        )}

        <p className="mt-10 text-center text-xs text-muted-foreground/45">
          Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </p>
      </div>
    </AuthenticatedLayout>
  );
}
