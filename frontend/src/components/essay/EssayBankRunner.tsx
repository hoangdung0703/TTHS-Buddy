"use client";

// 1 câu/lượt trong PHẠM VI 1 ngân hàng (category) - gọi POST /api/essay/question (kèm category)
// và POST /api/essay/submit thật (xem requirements.md "Phase 5a/5b v2" Buoc B).
import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { getEssayBankQuestionV2, submitEssay } from "@/lib/api";
import { ESSAY_BANK_TITLES } from "@/lib/essayBankPresentation";
import type { EssayBankCategory, EssayQuestionV2, EssaySubmitResponse } from "@/lib/types";

interface EssayBankRunnerProps {
  category: EssayBankCategory;
}

export function EssayBankRunner({ category }: EssayBankRunnerProps) {
  const [question, setQuestion] = useState<EssayQuestionV2 | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<EssaySubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    loadQuestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  function loadQuestion(): void {
    setLoadError(false);
    setQuestion(null);
    setAnswer("");
    setResult(null);
    getEssayBankQuestionV2(category)
      .then(setQuestion)
      .catch(() => setLoadError(true));
  }

  async function handleSubmit(): Promise<void> {
    if (answer.trim().length === 0 || question === null) return;
    setIsSubmitting(true);
    try {
      const response = await submitEssay({ question_id: question.question_id, user_answer: answer });
      setResult(response);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleNext(): void {
    loadQuestion();
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <Link href="/essay" className="text-sm text-muted-foreground hover:text-foreground">
          ← Chọn ngân hàng khác
        </Link>
        <Badge variant="outline">{ESSAY_BANK_TITLES[category]}</Badge>
      </div>

      {loadError ? (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>Không tải được câu hỏi cho ngân hàng này.</span>
          <Button variant="outline" size="sm" onClick={loadQuestion}>
            Thử lại
          </Button>
        </div>
      ) : null}

      {question === null && !loadError ? <div className="h-48 animate-pulse rounded-lg border border-border bg-muted/60" /> : null}

      {question !== null ? (
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

          <Button variant="secondary" className="w-full" onClick={handleNext}>
            Câu hỏi tiếp theo
          </Button>
        </div>
      ) : null}
    </div>
  );
}
