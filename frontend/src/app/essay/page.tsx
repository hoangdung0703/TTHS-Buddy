"use client";

import { AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, getEssayQuestion, submitEssay } from "@/lib/api";
import type { EssayQuestion, EssaySubmitResponse } from "@/lib/types";

type LoadState = "loading" | "ready" | "error";

export default function EssayPage() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [question, setQuestion] = useState<EssayQuestion | null>(null);
  const [answer, setAnswer] = useState<string>("");
  const [result, setResult] = useState<EssaySubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadQuestion();
  }, []);

  function loadQuestion(excludeQuestionId?: string): void {
    setLoadState("loading");
    setResult(null);
    setAnswer("");
    setError(null);

    getEssayQuestion(excludeQuestionId)
      .then((response) => {
        setQuestion(response);
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
  }

  async function handleSubmit(): Promise<void> {
    if (question === null || answer.trim().length === 0) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await submitEssay({ question_id: question.question_id, user_answer: answer });
      setResult(response);
    } catch (submitError) {
      const message = submitError instanceof ApiError ? submitError.message : "Không thể chấm bài, vui lòng thử lại.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthenticatedLayout title="Tự luận">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        {loadState === "loading" ? <div className="h-40 animate-pulse rounded-lg border border-border bg-muted/60" /> : null}

        {loadState === "error" ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              Không tải được câu hỏi tự luận.
            </span>
            <Button variant="outline" size="sm" onClick={() => loadQuestion()}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {loadState === "ready" && question !== null ? (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Câu hỏi tự luận</CardTitle>
                <Badge variant="outline">Điều {question.dieu_number}</Badge>
              </div>
              <p className="pt-1 text-sm font-normal text-foreground">{question.question_text}</p>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="Nhập câu trả lời của bạn..."
                disabled={result !== null}
              />

              {error !== null ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
              ) : null}

              {result === null ? (
                <Button
                  className="w-full rounded-full"
                  disabled={answer.trim().length === 0 || isSubmitting}
                  onClick={() => void handleSubmit()}
                >
                  {isSubmitting ? "Đang chấm bài..." : "Nộp bài"}
                </Button>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

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
                    {result.missing_points.map((point) => (
                      <li key={point} className="flex items-start gap-2">
                        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
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

            <Button variant="secondary" className="w-full" onClick={() => loadQuestion(question?.question_id)}>
              Câu hỏi tiếp theo
            </Button>
          </div>
        ) : null}
      </div>
    </AuthenticatedLayout>
  );
}
