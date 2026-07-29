"use client";

import { AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, getQuiz, submitQuiz } from "@/lib/api";
import type { QuizQuestion, QuizSubmitResponse } from "@/lib/types";

type LoadState = "loading" | "ready" | "error";

export default function QuizPage() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizSubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadQuiz();
  }, []);

  function loadQuiz(): void {
    setLoadState("loading");
    setResult(null);
    setSelectedOptions({});
    setError(null);

    getQuiz()
      .then((response) => {
        setQuestions(response.questions);
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
  }

  async function handleSubmit(): Promise<void> {
    setIsSubmitting(true);
    setError(null);

    try {
      const response = await submitQuiz({
        answers: questions.map((question) => ({
          question_id: question.question_id,
          selected_option: selectedOptions[question.question_id] ?? ""
        }))
      });
      setResult(response);
    } catch (submitError) {
      const message = submitError instanceof ApiError ? submitError.message : "Không thể nộp bài, vui lòng thử lại.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  const allAnswered = questions.length > 0 && questions.every((question) => selectedOptions[question.question_id] !== undefined);

  return (
    <AuthenticatedLayout title="Trắc nghiệm">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        {loadState === "loading" ? (
          <div className="space-y-4">
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-32 animate-pulse rounded-lg border border-border bg-muted/60" />
            ))}
          </div>
        ) : null}

        {loadState === "error" ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              Không tải được bộ câu hỏi.
            </span>
            <Button variant="outline" size="sm" onClick={loadQuiz}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {loadState === "ready" && result === null
          ? questions.map((question, index) => (
              <Card key={question.question_id}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Câu {index + 1}</CardTitle>
                    <Badge variant="outline">Điều {question.dieu_number}</Badge>
                  </div>
                  <p className="pt-1 text-sm font-normal text-foreground">{question.question_text}</p>
                </CardHeader>
                <CardContent className="space-y-2">
                  {question.mcq_options.map((option) => (
                    <label
                      key={option}
                      className="flex cursor-pointer items-start gap-3 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-accent"
                    >
                      <input
                        type="radio"
                        name={question.question_id}
                        checked={selectedOptions[question.question_id] === option}
                        onChange={() =>
                          setSelectedOptions((current) => ({ ...current, [question.question_id]: option }))
                        }
                        className="mt-0.5"
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </CardContent>
              </Card>
            ))
          : null}

        {loadState === "ready" && result === null ? (
          <div className="space-y-3">
            {error !== null ? (
              <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
            ) : null}
            <Button className="w-full" disabled={!allAnswered || isSubmitting} onClick={() => void handleSubmit()}>
              {isSubmitting ? "Đang chấm điểm..." : "Nộp bài"}
            </Button>
          </div>
        ) : null}

        {result !== null ? (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Kết quả</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-semibold text-foreground">
                  {result.score}/{result.total}
                </p>
                <p className="text-sm text-muted-foreground">câu trả lời đúng</p>
              </CardContent>
            </Card>

            {questions.map((question, index) => {
              const questionResult = result.results.find((item) => item.question_id === question.question_id);

              return (
                <Card key={question.question_id}>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      {questionResult?.is_correct ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                      <CardTitle>Câu {index + 1}</CardTitle>
                    </div>
                    <p className="pt-1 text-sm font-normal text-foreground">{question.question_text}</p>
                  </CardHeader>
                  <CardContent className="space-y-1 text-sm">
                    <p className="text-muted-foreground">
                      Bạn chọn: <span className="text-foreground">{selectedOptions[question.question_id]}</span>
                    </p>
                    {!questionResult?.is_correct ? (
                      <p className="text-emerald-700">Đáp án đúng: {questionResult?.mcq_correct}</p>
                    ) : null}
                  </CardContent>
                </Card>
              );
            })}

            <Button variant="secondary" className="w-full" onClick={loadQuiz}>
              Làm bài mới
            </Button>
          </div>
        ) : null}
      </div>
    </AuthenticatedLayout>
  );
}
