"use client";

// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
// Route này TẠM THỜI thay thế luồng Tự luận Phase 5b gốc (pool phẳng, backend thật đã chạy)
// bằng UI mock mới (4 ngân hàng theo category) theo thiết kế Figma mới của nhóm luật. Việc route
// khỏi backend thật là có chủ đích - PHẢI hoàn thành Bước 2 (backend thật) trước khi nhóm luật
// UAT, không được để UAT trên bản mock này.
import { BookOpen, Briefcase, Check, MessageSquareQuote, ToggleLeft, Wrench } from "lucide-react";
import Link from "next/link";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { MOCK_ESSAY_BANKS_V2 } from "@/lib/mockDataV2";
import type { EssayBankV2 } from "@/lib/types";
import { cn } from "@/lib/utils";

const BANK_ICON: Record<EssayBankV2["category"], typeof BookOpen> = {
  ly_thuyet: BookOpen,
  van_dung: Wrench,
  ban_trac_nghiem: ToggleLeft,
  tinh_huong: Briefcase
};

// Xen kẽ navy/gold cho các card, giống bố cục Figma gốc (mục đích trang trí, không mang ý nghĩa dữ liệu).
const BANK_ACCENT: Record<EssayBankV2["category"], "navy" | "gold"> = {
  ly_thuyet: "navy",
  van_dung: "gold",
  ban_trac_nghiem: "navy",
  tinh_huong: "gold"
};

function EssayBankCard({ bank }: { bank: EssayBankV2 }) {
  const Icon = BANK_ICON[bank.category];
  const accent = BANK_ACCENT[bank.category];
  const isComplete = bank.progress.kind === "complete";
  const isStarted = bank.progress.kind === "started";
  const pct = bank.progress.kind !== "untouched" ? bank.progress.attempted_count / bank.total_questions : 0;

  return (
    <Link
      href={`/essay/${bank.category}`}
      className={cn(
        "group flex flex-col gap-5 rounded-2xl border p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md",
        isComplete ? "border-accent/30 bg-accent/[0.05]" : "border-border bg-card"
      )}
    >
      <div className="flex items-start justify-between">
        <div
          className={cn(
            "flex h-12 w-12 items-center justify-center rounded-xl border",
            accent === "gold" ? "border-accent/35 bg-accent/10 text-accent" : "border-primary/15 bg-primary/[0.07] text-primary"
          )}
        >
          <Icon size={22} strokeWidth={1.4} />
        </div>
        {isComplete && (
          <span className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent/[0.12] px-2.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-accent">
            <Check size={10} strokeWidth={2.5} />
            Hoàn thành
          </span>
        )}
        {isStarted && (
          <span className="inline-flex items-center rounded-full border border-primary/10 bg-primary/[0.07] px-2.5 py-0.5 text-[0.7rem] font-medium text-primary">
            Đang học
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <p className={cn("text-xs font-semibold uppercase tracking-wide opacity-80", accent === "gold" ? "text-accent" : "text-primary")}>
          {bank.subtitle}
        </p>
        <h2 className="font-serif text-xl font-light tracking-tight text-foreground">{bank.title}</h2>
        <p className="mt-1 text-sm font-light leading-relaxed text-muted-foreground">{bank.description}</p>
      </div>

      <div className="mt-auto flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="font-serif text-sm text-foreground">{bank.total_questions} câu</span>
          {bank.progress.kind !== "untouched" ? (
            <span className={cn("text-xs", isComplete ? "text-accent" : "text-muted-foreground")}>
              {bank.progress.attempted_count} / {bank.total_questions} đã làm
            </span>
          ) : (
            <span className="text-xs text-muted-foreground/50">Chưa bắt đầu</span>
          )}
        </div>
        <div className="h-[3px] overflow-hidden rounded-full bg-primary/[0.08]">
          {pct > 0 && (
            <div
              className={cn("h-full rounded-full transition-all", isComplete ? "bg-accent" : "bg-primary")}
              style={{ width: `${pct * 100}%` }}
            />
          )}
        </div>
      </div>

      <span
        className={cn(
          "w-full rounded-full border border-primary/25 py-2.5 text-center text-sm font-medium transition-colors",
          "text-primary group-hover:bg-primary group-hover:text-primary-foreground"
        )}
      >
        {isComplete ? "Ôn lại" : isStarted ? "Tiếp tục" : "Bắt đầu luyện tập"}
      </span>
    </Link>
  );
}

export default function EssayPage() {
  const banks = MOCK_ESSAY_BANKS_V2;
  const totalAttempted = banks.reduce((acc, bank) => acc + (bank.progress.kind !== "untouched" ? bank.progress.attempted_count : 0), 0);
  const totalQuestions = banks.reduce((acc, bank) => acc + bank.total_questions, 0);
  const completedBanks = banks.filter((bank) => bank.progress.kind === "complete").length;

  return (
    <AuthenticatedLayout title="Tự luận">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="mb-1.5 font-serif text-3xl font-light tracking-tight text-foreground">Tự luận</h1>
            <p className="text-sm font-light text-muted-foreground">Chọn ngân hàng câu hỏi để luyện tập — mỗi lượt 1 câu</p>
          </div>

          <div className="flex shrink-0 gap-6 rounded-xl border border-border bg-primary/[0.04] px-5 py-3.5">
            <div className="flex flex-col gap-0.5">
              <span className="text-[0.7rem] uppercase tracking-wide text-muted-foreground">Ngân hàng hoàn thành</span>
              <span className="font-serif text-base text-foreground">
                {completedBanks} / {banks.length}
              </span>
            </div>
            <div className="w-px self-stretch bg-border" />
            <div className="flex flex-col gap-0.5">
              <span className="text-[0.7rem] uppercase tracking-wide text-muted-foreground">Câu đã luyện</span>
              <span className="font-serif text-base text-foreground">
                {totalAttempted} / {totalQuestions}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {banks.map((bank) => (
            <EssayBankCard key={bank.category} bank={bank} />
          ))}
        </div>

        <Link
          href="/essay/practice"
          className="mt-10 flex items-center gap-3 rounded-xl border border-accent/25 bg-accent/[0.06] px-5 py-4 transition-colors hover:bg-accent/[0.1]"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
            <MessageSquareQuote size={16} strokeWidth={1.6} />
          </span>
          <span className="flex flex-col">
            <span className="font-serif text-base text-foreground">Tôi hỏi · Bạn trả lời</span>
            <span className="text-xs text-muted-foreground">
              Minigame luyện tập nhanh — lấy ngẫu nhiên 1 câu từ toàn bộ ngân hàng tự luận
            </span>
          </span>
        </Link>

        <p className="mt-10 text-center text-xs text-muted-foreground/55">
          Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </p>
      </div>
    </AuthenticatedLayout>
  );
}
