import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { QuizSetRunner } from "@/components/quiz/QuizSetRunner";

interface QuizSetPageProps {
  params: Promise<{ setId: string }>;
}

// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
export default async function QuizSetPage({ params }: QuizSetPageProps) {
  const { setId } = await params;
  const quizSetId = Number.parseInt(setId, 10);

  return (
    <AuthenticatedLayout title="Trắc nghiệm">
      <QuizSetRunner quizSetId={quizSetId} />
    </AuthenticatedLayout>
  );
}
