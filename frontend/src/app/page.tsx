import Link from "next/link";
import { BarChart2, ListChecks, MessageSquareQuote, Scale } from "lucide-react";

import { BackgroundOrbs } from "@/components/brand/BackgroundOrbs";
import { Button } from "@/components/ui/button";

const features = [
  {
    icon: MessageSquareQuote,
    title: "Trợ lý AI có trích dẫn điều luật",
    description: "Mọi câu trả lời đều kèm căn cứ điều luật cụ thể, không suy diễn, không bịa nguồn."
  },
  {
    icon: ListChecks,
    title: "5 bộ đề trắc nghiệm",
    description:
      "Mỗi bộ trộn chung câu hỏi MCQ và Nhận định Đúng/Sai, chấm điểm và giải thích ngay sau khi nộp."
  },
  {
    icon: BarChart2,
    title: "Theo dõi tiến độ học tập",
    description: "Nhìn lại từ khoá đã hỏi, chủ đề cần ôn tập và kết quả trắc nghiệm ở một nơi."
  }
];

export default function HomePage() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background font-sans text-foreground">
      <BackgroundOrbs />

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-8 pb-4 pt-8">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Scale className="h-4 w-4" />
          </span>
          <span className="font-serif text-lg font-normal tracking-tight text-foreground">TTHS Buddy</span>
        </Link>
        <nav className="flex items-center gap-8">
          <Link href="/login" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
            Đăng nhập
          </Link>
          <Link
            href="/register"
            className="text-sm font-medium text-foreground transition-colors hover:text-primary"
          >
            Đăng ký
          </Link>
        </nav>
      </header>

      <main className="relative z-10">
        <section className="mx-auto grid max-w-6xl grid-cols-12 gap-8 px-8 pb-24 pt-20">
          <div className="col-span-12 md:col-span-8 md:col-start-2">
            <p className="mb-8 inline-flex items-center rounded-full bg-accent px-4 py-1.5 text-sm font-semibold uppercase tracking-[0.12em] text-accent-foreground">
              Tố tụng Hình sự · Trợ lý học tập AI
            </p>
            <h1 className="mb-8 font-serif text-[clamp(2.6rem,5vw,4.2rem)] font-light leading-[1.15] tracking-tight text-foreground">
              Mọi câu trả lời
              <br />
              đều có trích dẫn <span className="italic text-primary">điều luật</span>
              <br />
              cụ thể, không phỏng đoán.
            </h1>
            <p className="mb-12 max-w-xl text-[1.1rem] font-light leading-[1.75] text-muted-foreground">
              Trợ lý học tập chuyên về Luật Tố tụng Hình sự Việt Nam (BLTTHS 2015): giải thích điều khoản có
              căn cứ, luyện đề, và theo dõi tiến độ học tập của bạn.
            </p>
            <Button
              asChild
              className="h-auto rounded-full px-9 py-3.5 text-[0.95rem] font-medium tracking-[0.01em] shadow-[0_4px_24px_rgba(30,36,96,0.18)] transition-transform hover:-translate-y-px"
            >
              <Link href="/register">Bắt đầu học miễn phí</Link>
            </Button>
          </div>

          <div className="col-span-12 mt-12 flex items-center justify-center md:col-span-3 md:col-start-10 md:mt-0">
            <LawIllustration />
          </div>
        </section>

        <div className="mx-auto max-w-6xl px-8">
          <div className="border-t border-border" />
        </div>

        <section className="mx-auto max-w-6xl px-8 py-24">
          <p className="mb-16 text-sm uppercase tracking-[0.1em] text-muted-foreground">Tính năng</p>
          <div className="grid grid-cols-1 gap-16 md:grid-cols-3">
            {features.map(({ icon: Icon, title, description }) => (
              <div key={title} className="flex flex-col gap-4">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/[0.08] text-primary">
                  <Icon size={18} strokeWidth={1.5} />
                </div>
                <h3 className="font-serif text-[1.1rem] font-normal leading-snug tracking-tight text-foreground">
                  {title}
                </h3>
                <p className="text-[0.9rem] font-light leading-[1.75] text-muted-foreground">{description}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="relative z-10 mx-auto flex max-w-6xl flex-col gap-4 px-8 pb-10 pt-8 md:flex-row md:items-center md:justify-between">
        <span className="font-serif text-base font-normal text-muted-foreground">TTHS Buddy</span>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </p>
      </footer>
    </div>
  );
}

function LawIllustration() {
  return (
    <svg
      viewBox="0 0 160 200"
      fill="none"
      aria-label="Minh họa sách luật và cân công lý"
      className="w-full max-w-[220px] opacity-90"
    >
      <path d="M20 140 C20 140 78 130 80 130 C82 130 140 140 140 140" stroke="#1E2460" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M20 140 C18 115 22 90 28 72 C40 72 72 78 80 80" stroke="#1E2460" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M140 140 C142 115 138 90 132 72 C120 72 88 78 80 80" stroke="#1E2460" strokeWidth="1.2" strokeLinecap="round" />
      <line x1="80" y1="80" x2="80" y2="130" stroke="#1E2460" strokeWidth="1.1" strokeLinecap="round" />
      <line x1="34" y1="100" x2="74" y2="97" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.5" />
      <line x1="33" y1="108" x2="73" y2="105" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.4" />
      <line x1="33" y1="116" x2="72" y2="113" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.3" />
      <line x1="86" y1="97" x2="126" y2="100" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.5" />
      <line x1="87" y1="105" x2="127" y2="108" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.4" />
      <line x1="88" y1="113" x2="127" y2="116" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.3" />
      <line x1="80" y1="20" x2="80" y2="68" stroke="#1E2460" strokeWidth="1.1" strokeLinecap="round" />
      <circle cx="80" cy="18" r="2.2" fill="#1E2460" opacity="0.7" />
      <line x1="48" y1="36" x2="112" y2="36" stroke="#1E2460" strokeWidth="1.1" strokeLinecap="round" />
      <line x1="48" y1="36" x2="40" y2="52" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.75" />
      <line x1="48" y1="36" x2="56" y2="52" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.75" />
      <path d="M38 52 Q48 57 58 52" stroke="#1E2460" strokeWidth="1.1" strokeLinecap="round" />
      <line x1="112" y1="36" x2="104" y2="52" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.75" />
      <line x1="112" y1="36" x2="120" y2="52" stroke="#1E2460" strokeWidth="0.9" strokeLinecap="round" opacity="0.75" />
      <path d="M102 54 Q112 59 122 54" stroke="#1E2460" strokeWidth="1.1" strokeLinecap="round" />
      <circle cx="80" cy="36" r="1.8" fill="none" stroke="#1E2460" strokeWidth="1" opacity="0.6" />
    </svg>
  );
}
