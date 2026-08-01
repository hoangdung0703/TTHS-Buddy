"use client";

// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
// Làm bài + chấm điểm hoàn toàn cục bộ (getMockQuizQuestionsV2/gradeMockQuizV2), không gọi
// POST /api/quiz/generate hay POST /api/quiz/submit thật.
import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getMockQuizQuestionsV2, gradeMockQuizV2, withMockDelayV2 } from "@/lib/mockDataV2";
import type { QuizSubmitResponse } from "@/lib/types";

interface QuizSetRunnerProps {
  quizSetId: number;
}

export function QuizSetRunner({ quizSetId }: QuizSetRunnerProps) {
  const [questions] = useState(() => getMockQuizQuestionsV2(quizSetId));
  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizSubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const allAnswered = questions.every((question) => selectedOptions[question.question_id] !== undefined);
  const label = `Bộ đề ${String(quizSetId).padStart(2, "0")}`;

  async function handleSubmit(): Promise<void> {
    setIsSubmitting(true);
    const answers = questions.map((question) => ({
      question_id: question.question_id,
      selected_option: selectedOptions[question.question_id] ?? ""
    }));
    const response = await withMockDelayV2(gradeMockQuizV2(quizSetId, answers));
    setResult(response);
    setIsSubmitting(false);
  }

  function handleRetry(): void {
    setSelectedOptions({});
    setResult(null);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <Link href="/quiz" className="text-sm text-muted-foreground hover:text-foreground">
          ← Chọn bộ đề khác
        </Link>
        <Badge variant="outline">{label}</Badge>
      </div>

      {result === null
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
                    className="flex cursor-pointer items-start gap-3 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-accent/10"
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

      {result === null ? (
        <Button className="w-full rounded-full" disabled={!allAnswered || isSubmitting} onClick={() => void handleSubmit()}>
          {isSubmitting ? "Đang chấm điểm..." : "Nộp bài"}
        </Button>
      ) : (
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
                  {!questionResult?.is_correct ? <p className="text-emerald-700">Đáp án đúng: {questionResult?.mcq_correct}</p> : null}
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
      )}
    </div>
  );
}
