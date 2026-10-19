"use client";

import { Info } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { useTrialFeature } from "@/hooks/useTrialFeature";

export const TRIAL_DISCLAIMER = "Đây là mô phỏng phục vụ học tập, không phải phán quyết thật.";

// The simulation banner every trial screen carries (contract Mục 8): muted, never a functional
// amber/red. Sticky at the top of the scrolling content area; hidden when printing the record.
export function TrialBanner() {
  return (
    <div
      role="note"
      data-testid="trial-banner"
      className="sticky top-0 z-20 flex items-center justify-center gap-2 border-b border-border bg-secondary/95 px-4 py-2 text-center text-xs text-secondary-foreground backdrop-blur print:hidden"
    >
      <Info className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span>{TRIAL_DISCLAIMER}</span>
    </div>
  );
}

// Layout for every /trial* page: the authenticated shell, the banner, and the feature gate. When
// the backend says the feature is off (404 probe), the page is left for the dashboard.
export function TrialShell({ title, children }: { title: string; children: ReactNode }) {
  const feature = useTrialFeature();
  const router = useRouter();

  useEffect(() => {
    if (feature === "disabled") {
      router.replace("/dashboard");
    }
  }, [feature, router]);

  return (
    <AuthenticatedLayout title={title}>
      <TrialBanner />
      {feature === "disabled" ? (
        <p className="px-6 py-16 text-center text-sm text-muted-foreground">Tính năng này chưa được bật. Đang chuyển về trang chính...</p>
      ) : (
        children
      )}
    </AuthenticatedLayout>
  );
}
