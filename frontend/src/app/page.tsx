"use client";

import Link from "next/link";
import { type CSSProperties, useState } from "react";
import { BookOpenCheck, ListChecks, ScrollText } from "lucide-react";

import { Seal } from "@/components/brand/Seal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const appendixItems = [
  {
    numeral: "I",
    icon: ScrollText,
    title: "Trợ lý AI có trích dẫn",
    description: "Mọi câu trả lời đều kèm căn cứ điều luật cụ thể — không suy diễn, không bịa nguồn."
  },
  {
    numeral: "II",
    icon: ListChecks,
    title: "5 bộ đề trắc nghiệm",
    description: "MCQ và câu Nhận định Đúng/Sai theo từng bộ, chấm điểm và giải thích ngay sau khi nộp."
  },
  {
    numeral: "III",
    icon: BookOpenCheck,
    title: "Theo dõi tiến độ học tập",
    description: "Nhìn lại từ khoá đã hỏi, chủ đề cần ôn tập và kết quả trắc nghiệm ở một nơi."
  }
];

const headlineLines = [
  { text: "Không ai", delay: 0 },
  { text: "bị xem là", delay: 120 },
  { text: "có tội.", delay: 240, accent: true }
];

const proceedingStages = [
  { label: "Điều tra", delay: 520 },
  { label: "Truy tố", delay: 670 },
  { label: "Xét xử", delay: 820 }
];

function riseStyle(delayMs: number): CSSProperties {
  return { animationDelay: `${delayMs}ms`, animationFillMode: "both" };
}

export default function HomePage() {
  const [unlocked, setUnlocked] = useState(false);

  return (
    <main className="relative z-[2] flex min-h-screen flex-col overflow-x-clip">
      <div className="border-b border-border/70 bg-muted/30 py-2 text-center">
        <span className="text-[11px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
          Hồ sơ học tập · Số 13/TTHS-Buddy · Tài liệu tham khảo, không thay thế văn bản pháp lý
        </span>
      </div>

      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-8 md:px-10">
        <div className="flex items-baseline gap-2">
          <span className="font-serif text-lg font-semibold text-foreground">TTHS Buddy</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">Học tập · BLTTHS 2015</span>
        </div>
        {/* Always-reachable fallback: signing in/up never depends on discovering the seal. */}
        <nav className="flex items-center gap-4">
          <Link href="/login" className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
            Đăng nhập
          </Link>
          <Link href="/register" className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
            Đăng ký
          </Link>
        </nav>
      </header>

      <section className="mx-auto grid w-full max-w-6xl flex-1 gap-x-8 px-6 pb-24 pt-6 md:grid-cols-[1fr_auto] md:px-10 md:pt-10">
        <div className="min-w-0">
          <h1 className="font-serif text-6xl font-semibold leading-[0.98] tracking-tight text-foreground sm:text-7xl md:text-8xl">
            {headlineLines.map(({ text, delay, accent }) => (
              <span
                key={text}
                className={cn("block animate-rise-in", accent && "text-steel-blue-600")}
                style={riseStyle(delay)}
              >
                {text}
              </span>
            ))}
          </h1>

          <p className="mt-6 max-w-xl animate-rise-in text-base leading-7 text-muted-foreground md:text-lg" style={riseStyle(420)}>
            Trước một bản án có hiệu lực — đó là điểm khởi đầu của Tố tụng Hình sự, và cũng là điểm khởi đầu của TTHS Buddy: công cụ học luật cho sinh viên, hỏi đáp có căn cứ, luyện đề theo bộ.
          </p>
        </div>

        <div className="relative mt-10 flex shrink-0 flex-col items-start md:mt-2 md:w-56 md:items-end">
          <button
            type="button"
            onClick={() => setUnlocked(true)}
            aria-pressed={unlocked}
            aria-label={unlocked ? "Đã xác nhận" : "Chạm vào dấu để tiếp tục"}
            className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <Seal size={168} className="mr-2 max-md:h-24 max-md:w-24" delayMs={1000} />
          </button>

          {unlocked ? (
            <div className="mt-5 flex animate-rise-in flex-col items-start gap-3 md:items-end" style={riseStyle(0)}>
              <Button asChild size="lg">
                <Link href="/register">Bắt đầu học miễn phí</Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/login">Đăng nhập</Link>
              </Button>
            </div>
          ) : (
            <p
              className="mr-2 mt-4 animate-rise-in text-xs text-muted-foreground md:text-right"
              style={riseStyle(1900)}
            >
              Chạm vào dấu để tiếp tục
            </p>
          )}

          <div className="mt-10 flex flex-col items-start gap-2.5 border-l border-border pl-4 text-left md:items-end md:border-l-0 md:border-r md:pl-0 md:pr-4 md:text-right">
            {proceedingStages.map(({ label, delay }) => (
              <span
                key={label}
                className="animate-rise-in text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground"
                style={riseStyle(delay)}
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-20 md:px-10">
        <Badge variant="accent" className="mb-6 animate-rise-in" style={riseStyle(2000)}>
          <span className="text-steel-blue-700">#</span> Tinh thần Điều 13 · BLTTHS 2015
        </Badge>

        <p className="mb-2 animate-rise-in text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground" style={riseStyle(2050)}>
          Phụ lục đính kèm hồ sơ
        </p>

        <ol className="animate-rise-in border-y border-border" style={riseStyle(2100)}>
          {appendixItems.map(({ numeral, icon: Icon, title, description }, index) => (
            <li
              key={numeral}
              className={cn(
                "flex animate-rise-in items-start gap-4 py-5 transition-colors duration-200 hover:bg-muted/40",
                index > 0 && "border-t border-border"
              )}
              style={riseStyle(2150 + index * 90)}
            >
              <span className="w-8 shrink-0 font-serif text-base font-semibold text-steel-blue-600">{numeral}.</span>
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-steel-blue-600" strokeWidth={1.75} />
              <div>
                <p className="font-medium text-foreground">{title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <footer className="border-t border-border py-6 text-center">
        <span className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
          TTHS Buddy · Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
        </span>
      </footer>
    </main>
  );
}
