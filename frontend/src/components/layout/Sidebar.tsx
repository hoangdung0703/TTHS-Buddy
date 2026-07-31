"use client";

import { LayoutGrid, MessageSquare, ListChecks, PenLine, Plus, Scale, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutGrid;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Tổng quan", icon: LayoutGrid },
  { href: "/chat", label: "Trợ lý AI", icon: MessageSquare },
  { href: "/quiz", label: "Trắc nghiệm", icon: ListChecks },
  { href: "/essay", label: "Tự luận", icon: PenLine }
];

// Cosmetic-only placeholder to match the sidebar layout in frontend.md - conversation
// history persistence is not part of the Phase 8 mock contract, so this list is static.
const MOCK_CONVERSATION_HISTORY = [
  { id: "conv-1", title: "Điều 23 - Suy đoán vô tội", tag: "Nguyên tắc", time: "Hôm nay" },
  { id: "conv-2", title: "Điều kiện và thủ tục tạm giam", tag: "Biện pháp ngăn chặn", time: "Hôm qua" },
  { id: "conv-3", title: "Quy trình khởi tố vụ án hình sự", tag: "Khởi tố", time: "25/07" }
];

interface SidebarProps {
  userLabel: string | null;
}

export function Sidebar({ userLabel }: SidebarProps) {
  const pathname = usePathname();
  const [historyQuery, setHistoryQuery] = useState<string>("");

  const filteredHistory = useMemo(
    () =>
      MOCK_CONVERSATION_HISTORY.filter((item) =>
        item.title.toLowerCase().includes(historyQuery.toLowerCase())
      ),
    [historyQuery]
  );

  return (
    <aside className="flex h-screen w-72 shrink-0 flex-col border-r border-border bg-card">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Scale className="h-5 w-5" />
        </div>
        <div>
          <p className="font-serif text-base font-light tracking-tight text-foreground">TTHS Buddy</p>
          <p className="text-xs text-muted-foreground">Học tập · BLTTHS 2015</p>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 pt-4">
        <Link
          href="/chat"
          className="flex w-full items-center justify-center gap-2 rounded-full border border-border bg-background px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <Plus className="h-4 w-4" />
          Hội thoại mới
        </Link>
      </div>

      <div className="px-3 pt-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={historyQuery}
            onChange={(event) => setHistoryQuery(event.target.value)}
            placeholder="Tìm hội thoại..."
            className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm text-foreground outline-none focus:border-ring"
          />
        </div>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto px-3">
        <p className="px-1 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Lịch sử</p>
        <ul className="space-y-1">
          {filteredHistory.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
              >
                <p className="truncate font-medium text-foreground">{item.title}</p>
                <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                  <span className="truncate">{item.tag}</span>
                  <span>{item.time}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-border px-5 py-4">
        <p className="truncate text-sm font-medium text-foreground">{userLabel ?? "Sinh viên"}</p>
        <p className="text-xs text-muted-foreground">Sinh viên · Luật Tố tụng Hình sự</p>
      </div>
    </aside>
  );
}
