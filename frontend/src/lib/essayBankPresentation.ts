import { BookOpen, Briefcase, ToggleLeft, Wrench } from "lucide-react";

import type { EssayBankCategory } from "@/lib/types";

// Shared icon/accent/title lookups for EssayBankCategory - used by /essay's bank-selection
// cards, the dashboard's Khối 2 mini trackers, and EssayBankRunner, so the 4 banks look
// consistent everywhere instead of each place re-declaring its own copy.
export const ESSAY_BANK_ICON: Record<EssayBankCategory, typeof BookOpen> = {
  ly_thuyet: BookOpen,
  van_dung: Wrench,
  ban_trac_nghiem: ToggleLeft,
  tinh_huong: Briefcase
};

// Xen kẽ navy/gold cho các card, giống bố cục Figma gốc (mục đích trang trí, không mang ý nghĩa dữ liệu).
export const ESSAY_BANK_ACCENT: Record<EssayBankCategory, "navy" | "gold"> = {
  ly_thuyet: "navy",
  van_dung: "gold",
  ban_trac_nghiem: "navy",
  tinh_huong: "gold"
};

export const ESSAY_BANK_TITLES: Record<EssayBankCategory, string> = {
  ly_thuyet: "Lý thuyết",
  van_dung: "Vận dụng",
  ban_trac_nghiem: "Bán trắc nghiệm",
  tinh_huong: "Tình huống"
};
