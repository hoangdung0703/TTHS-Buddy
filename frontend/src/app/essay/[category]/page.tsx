import { notFound } from "next/navigation";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { EssayBankRunner } from "@/components/essay/EssayBankRunner";
import { MOCK_ESSAY_BANKS_V2 } from "@/lib/mockDataV2";
import type { EssayBankCategory } from "@/lib/types";

interface EssayBankPageProps {
  params: Promise<{ category: string }>;
}

const VALID_CATEGORIES = new Set(MOCK_ESSAY_BANKS_V2.map((bank) => bank.category));

// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
export default async function EssayBankPage({ params }: EssayBankPageProps) {
  const { category } = await params;

  if (!VALID_CATEGORIES.has(category as EssayBankCategory)) {
    notFound();
  }

  const bank = MOCK_ESSAY_BANKS_V2.find((item) => item.category === category);

  return (
    <AuthenticatedLayout title={`Tự luận · ${bank?.title ?? ""}`}>
      <EssayBankRunner category={category as EssayBankCategory} />
    </AuthenticatedLayout>
  );
}
