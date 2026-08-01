"use client";

import { LayoutGrid, MessageSquare, MessageSquareQuote, ListChecks, PenLine, Plus, Scale, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getConversations } from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";
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

// Coarse "Hom nay"/"Hom qua"/dd-mm label, computed client-side from the browser's local
// timezone - good enough for a Sidebar history list, no need for the VN-timezone precision
// dashboard_service.py uses for the "keywords yesterday" metric.
function formatConversationTime(updatedAt: string): string {
  const date = new Date(updatedAt);
  const now = new Date();
  const isSameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

  if (isSameDay(date, now)) {
    return "Hôm nay";
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (isSameDay(date, yesterday)) {
    return "Hôm qua";
  }

  return date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

interface SidebarProps {
  userLabel: string | null;
}

export function Sidebar({ userLabel }: SidebarProps) {
  const pathname = usePathname();
  const [historyQuery, setHistoryQuery] = useState<string>("");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  // Re-fetched on every pathname change (not just once on mount) so sending a first message on
  // the bare /chat route - which creates a brand new conversation server-side - makes it appear
  // in this list without requiring a full page reload.
  useEffect(() => {
    void getConversations().then(setConversations);
  }, [pathname]);

  const filteredHistory = useMemo(
    () =>
      conversations.filter((conversation) => conversation.title.toLowerCase().includes(historyQuery.toLowerCase())),
    [conversations, historyQuery]
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

        {/* TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md
            "Phase 5a/5b v2") - entry point riêng cho minigame vì nó không phải 1 trang cùng
            cấp với Trắc nghiệm/Tự luận mà là 1 chế độ luyện tập bên trong Tự luận. */}
        <Link
          href="/essay/practice"
          className={cn(
            "ml-6 flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
            pathname === "/essay/practice"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          )}
        >
          <MessageSquareQuote className="h-3.5 w-3.5" />
          Tôi hỏi · Bạn trả lời
        </Link>
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
          {filteredHistory.map((conversation) => {
            const href = `/chat/${conversation.conversation_id}`;
            const isActive = pathname === href;

            return (
              <li key={conversation.conversation_id}>
                <Link
                  href={href}
                  className={cn(
                    "block w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                    isActive ? "bg-accent" : "hover:bg-accent"
                  )}
                >
                  <p className="truncate font-medium text-foreground">{conversation.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{formatConversationTime(conversation.updated_at)}</p>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="border-t border-border px-5 py-4">
        <p className="truncate text-sm font-medium text-foreground">{userLabel ?? "Sinh viên"}</p>
        <p className="text-xs text-muted-foreground">Sinh viên · Luật Tố tụng Hình sự</p>
      </div>
    </aside>
  );
}
