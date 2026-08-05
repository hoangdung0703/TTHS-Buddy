import { notFound } from "next/navigation";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { EssayBankRunner } from "@/components/essay/EssayBankRunner";
import { ESSAY_BANK_TITLES } from "@/lib/essayBankPresentation";
import type { EssayBankCategory } from "@/lib/types";

interface EssayBankPageProps {
  params: Promise<{ category: string }>;
}

const VALID_CATEGORIES = new Set<string>(["ly_thuyet", "van_dung", "ban_trac_nghiem", "tinh_huong"]);

export default async function EssayBankPage({ params }: EssayBankPageProps) {
  const { category } = await params;

  if (!VALID_CATEGORIES.has(category)) {
    notFound();
  }

  const bankCategory = category as EssayBankCategory;

  return (
    <AuthenticatedLayout title={`Tự luận · ${ESSAY_BANK_TITLES[bankCategory]}`}>
      <EssayBankRunner category={bankCategory} />
    </AuthenticatedLayout>
  );
}
