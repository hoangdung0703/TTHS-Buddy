"use client";

// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
// 1 câu/lượt trong PHẠM VI 1 ngân hàng (category) - hoàn toàn cục bộ, không gọi
// POST /api/essay/question / POST /api/essay/submit thật.
import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { getMockEssayBankQuestionsV2, gradeMockEssayBankV2, withMockDelayV2 } from "@/lib/mockDataV2";
import type { EssayBankCategory, EssaySubmitResponse } from "@/lib/types";

const BANK_TITLES: Record<EssayBankCategory, string> = {
  ly_thuyet: "Lý thuyết",
  van_dung: "Vận dụng",
  ban_trac_nghiem: "Bán trắc nghiệm",
  tinh_huong: "Tình huống"
};

interface EssayBankRunnerProps {
  category: EssayBankCategory;
}

export function EssayBankRunner({ category }: EssayBankRunnerProps) {
  const questions = getMockEssayBankQuestionsV2(category);
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<EssaySubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const question = questions[index % questions.length];

  async function handleSubmit(): Promise<void> {
    if (answer.trim().length === 0) return;
    setIsSubmitting(true);
    const response = await withMockDelayV2(gradeMockEssayBankV2(question.question_id, answer));
    setResult(response);
    setIsSubmitting(false);
  }

  function handleNext(): void {
    setIndex((current) => current + 1);
    setAnswer("");
    setResult(null);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <Link href="/essay" className="text-sm text-muted-foreground hover:text-foreground">
          ← Chọn ngân hàng khác
        </Link>
        <Badge variant="outline">{BANK_TITLES[category]}</Badge>
      </div>

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

          <Button variant="secondary" className="w-full" onClick={handleNext}>
            Câu hỏi tiếp theo
          </Button>
        </div>
      ) : null}
    </div>
  );
}
