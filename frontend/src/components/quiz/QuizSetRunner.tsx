"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getQuizV2, submitQuizV2 } from "@/lib/api";
import type { QuizQuestion, QuizSubmitResponse } from "@/lib/types";

interface QuizSetRunnerProps {
  quizSetId: number;
}

export function QuizSetRunner({ quizSetId }: QuizSetRunnerProps) {
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizSubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    loadQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quizSetId]);

  function loadQuestions(): void {
    setLoadError(false);
    setQuestions(null);
    setSelectedOptions({});
    setResult(null);
    getQuizV2(quizSetId)
      .then(setQuestions)
      .catch(() => setLoadError(true));
  }

  const allAnswered = questions !== null && questions.every((question) => selectedOptions[question.question_id] !== undefined);
  const label = `Bộ đề ${String(quizSetId).padStart(2, "0")}`;

  async function handleSubmit(): Promise<void> {
    if (questions === null) return;
    setIsSubmitting(true);
    const answers = questions.map((question) => ({
      question_id: question.question_id,
      selected_option: selectedOptions[question.question_id] ?? ""
    }));
    try {
      const response = await submitQuizV2(quizSetId, answers);
      setResult(response);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleRetry(): void {
    loadQuestions();
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <Link href="/quiz" className="text-sm text-muted-foreground hover:text-foreground">
          ← Chọn bộ đề khác
        </Link>
        <Badge variant="outline">{label}</Badge>
      </div>

      {loadError ? (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>Không tải được câu hỏi cho bộ đề này.</span>
          <Button variant="outline" size="sm" onClick={loadQuestions}>
            Thử lại
          </Button>
        </div>
      ) : null}

      {questions === null && !loadError ? (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-40 animate-pulse rounded-lg border border-border bg-muted/60" />
          ))}
        </div>
      ) : null}

      {questions !== null && result === null
        ? questions.map((question, index) => (
            <Card key={question.question_id}>
              <CardHeader>
                <CardTitle>Câu {index + 1}</CardTitle>
                <p className="pt-1 text-sm font-normal text-foreground">{question.question_text}</p>
              </CardHeader>
              <CardContent className="space-y-2">
                {question.mcq_options.map((option) => (
                  <label
                    key={option}
                    className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-border px-3 py-3 text-sm transition-colors hover:bg-accent/10"
                  >
                    <input
                      type="radio"
                      name={question.question_id}
                      checked={selectedOptions[question.question_id] === option}
                      onChange={() => setSelectedOptions((current) => ({ ...current, [question.question_id]: option }))}
                      className="mt-0.5"
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </CardContent>
            </Card>
          ))
        : null}

      {questions !== null && result === null ? (
        <Button className="w-full rounded-full" disabled={!allAnswered || isSubmitting} onClick={() => void handleSubmit()}>
          {isSubmitting ? "Đang chấm điểm..." : "Nộp bài"}
        </Button>
      ) : null}

      {questions !== null && result !== null ? (
        <div className="space-y-4">
          <Card className="border-accent/30 bg-accent/[0.06]">
            <CardHeader>
              <CardTitle>Kết quả</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="font-serif text-3xl font-normal text-foreground">
                {result.score}/{result.total}
              </p>
              <p className="text-sm text-muted-foreground">câu trả lời đúng</p>
            </CardContent>
          </Card>

          {questions.map((question, index) => {
            const questionResult = result.results.find((item) => item.question_id === question.question_id);

            const isCorrect = questionResult?.is_correct ?? false;

            return (
              <Card
                key={question.question_id}
                className={
                  isCorrect
                    ? "border-l-4 border-l-emerald-800 bg-emerald-50"
                    : "border-l-4 border-l-red-700 bg-red-50"
                }
              >
                <CardHeader>
                  <div className="flex items-center gap-2">
                    {isCorrect ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-800" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-700" />
                    )}
                    <CardTitle>Câu {index + 1}</CardTitle>
                  </div>
                  <p className="pt-1 text-sm font-normal text-foreground">{question.question_text}</p>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p className={isCorrect ? "text-muted-foreground" : "text-red-700"}>
                    Bạn chọn: <span className={isCorrect ? "text-foreground" : "font-medium text-red-700"}>{selectedOptions[question.question_id]}</span>
                  </p>
                  {!isCorrect ? (
                    <p className="font-medium text-emerald-800">Đáp án đúng: {questionResult?.mcq_correct}</p>
                  ) : null}
                  {questionResult?.explanation ? <p className="text-muted-foreground">{questionResult.explanation}</p> : null}
                </CardContent>
              </Card>
            );
          })}

          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={handleRetry}>
              Làm lại
            </Button>
            <Button variant="outline" className="flex-1" asChild>
              <Link href="/quiz">Chọn bộ khác</Link>
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
