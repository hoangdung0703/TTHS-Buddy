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

// Cùng 1 tông navy cho cả 4 category (đồng bộ hoá sau audit design-taste - luân phiên navy/gold
// trước đây chỉ trang trí, không mang ý nghĩa dữ liệu, nhưng đọc như 2 nhóm tách biệt không chủ
// đích). Gold vẫn giữ nguyên ở nơi khác đã có ý nghĩa riêng (badge "Hoàn thành" = trạng thái, không
// phải phân loại category) - không đụng tới đây.
export const ESSAY_BANK_ACCENT: Record<EssayBankCategory, "navy" | "gold"> = {
  ly_thuyet: "navy",
  van_dung: "navy",
  ban_trac_nghiem: "navy",
  tinh_huong: "navy"
};

export const ESSAY_BANK_TITLES: Record<EssayBankCategory, string> = {
  ly_thuyet: "Lý thuyết",
  van_dung: "Vận dụng",
  ban_trac_nghiem: "Bán trắc nghiệm",
  tinh_huong: "Tình huống"
};

export const ESSAY_BANK_SUBTITLES: Record<EssayBankCategory, string> = {
  ly_thuyet: "Khái niệm & Nguyên tắc",
  van_dung: "Áp dụng thực tiễn",
  ban_trac_nghiem: "Nhận định Đúng / Sai",
  tinh_huong: "Phân tích vụ án"
};

export const ESSAY_BANK_DESCRIPTIONS: Record<EssayBankCategory, string> = {
  ly_thuyet: "Câu hỏi về khái niệm, nguyên tắc cơ bản của Bộ luật Tố tụng hình sự.",
  van_dung: "Câu hỏi vận dụng quy định pháp luật vào các tình huống cụ thể.",
  ban_trac_nghiem: "Nhận định đúng hay sai kèm giải thích, trả lời bằng lập luận tự do.",
  tinh_huong: "Phân tích tình huống thực tế dựa trên điều luật, quy trình tố tụng."
};
