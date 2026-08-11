"use client";

// Vào ngân hàng hiện NGAY lưới toàn bộ câu hỏi (EssayQuestionGrid), user tự chọn câu muốn làm -
// thay cho cơ chế cũ "vào ngân hàng -> nhận ngẫu nhiên 1 câu" (xem requirements.md "Feature - Doi
// luong Tu luan"). Trong màn làm bài: KHÔNG hiển thị Điều/căn cứ pháp lý trước khi nộp bài (đó là
// đáp án - dieu_number là "Căn cứ pháp lý" của essay_key_points, xem ingestion/question_bank.json),
// KHÔNG dùng eyebrow/nút "Câu khác" của minigame /essay/practice (hành vi ngẫu nhiên chỉ hợp lý ở
// đó - ở đây user đã chủ động chọn đúng câu từ lưới).
import { CheckCircle2, ChevronLeft, ChevronRight, LayoutGrid, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { EssayQuestionGrid } from "@/components/essay/EssayQuestionGrid";
import { getEssayBankQuestionListV2, submitEssay } from "@/lib/api";
import { ESSAY_BANK_TITLES } from "@/lib/essayBankPresentation";
import type { EssayBankCategory, EssayBankQuestionListItem, EssaySubmitResponse } from "@/lib/types";

interface EssayBankRunnerProps {
  category: EssayBankCategory;
}

type View = "grid" | "detail";

export function EssayBankRunner({ category }: EssayBankRunnerProps) {
  const [questions, setQuestions] = useState<EssayBankQuestionListItem[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [view, setView] = useState<View>("grid");
  const [selectedOrder, setSelectedOrder] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<EssaySubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    loadQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  function loadQuestions(): void {
    setLoadError(false);
    setQuestions(null);
    getEssayBankQuestionListV2(category)
      .then(setQuestions)
      .catch(() => setLoadError(true));
  }

  function openQuestion(order: number): void {
    setSelectedOrder(order);
    setAnswer("");
    setResult(null);
    setView("detail");
  }

  function backToGrid(): void {
    setView("grid");
    setSelectedOrder(null);
  }

  const current =
    questions !== null && selectedOrder !== null ? questions.find((q) => q.order === selectedOrder) ?? null : null;

  function goToOrder(order: number): void {
    if (questions === null) return;
    if (!questions.some((q) => q.order === order)) return;
    setSelectedOrder(order);
    setAnswer("");
    setResult(null);
  }

  async function handleSubmit(): Promise<void> {
    if (answer.trim().length === 0 || current === null) return;
    setIsSubmitting(true);
    try {
      const response = await submitEssay({ question_id: current.question_id, user_answer: answer });
      setResult(response);
      // Cập nhật trạng thái ô lưới ngay tại chỗ (không chờ reload) - phản ánh đúng lần làm gần
      // nhất vừa nộp, khớp logic phân loại status ở backend (missing_points rỗng -> done).
      setQuestions((previous) =>
        previous === null
          ? previous
          : previous.map((q) =>
              q.question_id === current.question_id
                ? { ...q, status: response.missing_points.length === 0 ? "done" : "needs_review" }
                : q
            )
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  if (view === "grid" || current === null) {
    return (
      <div className="mx-auto max-w-4xl space-y-6 px-6 py-8">
        <div className="flex items-center justify-between">
          <Link href="/essay" className="text-sm text-muted-foreground hover:text-foreground">
            ← Chọn ngân hàng khác
          </Link>
          <Badge variant="outline">{ESSAY_BANK_TITLES[category]}</Badge>
        </div>

        {loadError ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Không tải được danh sách câu hỏi cho ngân hàng này.</span>
            <Button variant="outline" size="sm" onClick={loadQuestions}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {questions === null && !loadError ? (
          <div className="h-48 animate-pulse rounded-lg border border-border bg-muted/60" />
        ) : null}

        {questions !== null ? <EssayQuestionGrid questions={questions} onSelect={openQuestion} /> : null}
      </div>
    );
  }

  const total = questions?.length ?? 0;
  const hasPrev = current.order > 1;
  const hasNext = current.order < total;

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <Link href="/essay" className="text-sm text-muted-foreground hover:text-foreground">
          ← {ESSAY_BANK_TITLES[category]}
        </Link>
        <div className="flex flex-col items-center gap-1">
          <span className="text-sm font-medium text-foreground">
            Câu {current.order} / {total}
          </span>
          <button
            type="button"
            onClick={backToGrid}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <LayoutGrid size={12} strokeWidth={1.8} />
            Xem danh sách
          </button>
        </div>
        <div className="w-[92px]" />
      </div>

      <div className="flex items-center justify-between text-sm">
        <button
          type="button"
          disabled={!hasPrev}
          onClick={() => goToOrder(current.order - 1)}
          className="flex min-h-11 items-center gap-1 rounded-full px-3 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30"
        >
          <ChevronLeft size={16} strokeWidth={1.8} />
          Câu trước
        </button>
        <button
          type="button"
          disabled={!hasNext}
          onClick={() => goToOrder(current.order + 1)}
          className="flex min-h-11 items-center gap-1 rounded-full px-3 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30"
        >
          Câu sau
          <ChevronRight size={16} strokeWidth={1.8} />
        </button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Câu hỏi tự luận</CardTitle>
          {/* Không hiển thị badge Điều/căn cứ pháp lý ở đây trước khi nộp bài - dieu_number là
              căn cứ của đáp án, chỉ lộ ra sau khi chấm (xem khối "Nhận xét" bên dưới). */}
          <p className="pt-1 text-sm font-normal text-foreground">{current.question_text}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Nhập câu trả lời của bạn..."
            disabled={result !== null}
          />

          {result === null ? (
            <Button
              className="w-full rounded-full"
              disabled={answer.trim().length === 0 || isSubmitting}
              onClick={() => void handleSubmit()}
            >
              {isSubmitting ? "Đang chấm bài..." : "Nộp câu trả lời"}
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {result !== null ? (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Ý đã trả lời đúng</CardTitle>
            </CardHeader>
            <CardContent>
              {result.matched_points.length === 0 ? (
                <p className="text-sm text-muted-foreground">Chưa có ý nào khớp với rubric.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {result.matched_points.map((point) => (
                    <li key={point} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                      {point}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Ý còn thiếu / sai</CardTitle>
            </CardHeader>
            <CardContent>
              {result.missing_points.length === 0 ? (
                <p className="text-sm text-muted-foreground">Không thiếu ý nào.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {(result.missing_points_display ?? result.missing_points).map((point) => (
                    <li key={point} className="flex items-start gap-2">
                      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                      {point}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Nhận xét</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-foreground">{result.feedback}</p>
              {result.suggested_dieu.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Nên ôn lại:</span>
                  {result.suggested_dieu.map((dieu) => (
                    <Badge key={dieu} variant="accent">
                      Điều {dieu}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1 rounded-full" onClick={backToGrid}>
              Xem danh sách
            </Button>
            {hasNext ? (
              <Button variant="secondary" className="flex-1 rounded-full" onClick={() => goToOrder(current.order + 1)}>
                Câu tiếp theo
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
