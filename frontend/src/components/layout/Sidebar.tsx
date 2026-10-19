"use client";

import {
  Gavel,
  LayoutGrid,
  MessageSquare,
  ListChecks,
  NotebookPen,
  Pencil,
  Plus,
  Scale,
  Search,
  Trash2
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { deleteConversation, getConversations, renameConversation } from "@/lib/api";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { useTrialFeature } from "@/hooks/useTrialFeature";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
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
  { href: "/notes", label: "Vở ghi", icon: NotebookPen }
];

// Shown only once GET /api/trials has answered 200 (the backend TRIAL_ENABLED flag); see
// useTrialFeature. Active on every /trial/* sub-page, not just the list.
const TRIAL_NAV_ITEM: NavItem = { href: "/trial", label: "Phiên tòa giả định", icon: Gavel };

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
  // Called after a nav/history selection - used by the mobile drawer (AuthenticatedLayout) to
  // close itself once the user has picked a destination. Undefined on desktop, where the
  // sidebar is always visible and there's nothing to close.
  onNavigate?: () => void;
}

export function Sidebar({ userLabel, onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [historyQuery, setHistoryQuery] = useState<string>("");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  // "ready" only once the server has actually answered. An empty list is shown as "Chưa có hội
  // thoại nào" ONLY in that state; a failed load is its own state with a retry, so a read outage
  // can no longer look exactly like a brand-new account (which is what the old swallowed .catch
  // made it look like).
  const [historyStatus, setHistoryStatus] = useState<"loading" | "ready" | "error">("loading");
  const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState<string>("");
  const { isSlow: isHistorySlow, start: startSlowNotice, stop: stopSlowNotice } = useSlowRequestNotice();
  const trialFeature = useTrialFeature();
  const navItems = trialFeature === "enabled" ? [...NAV_ITEMS, TRIAL_NAV_ITEM] : NAV_ITEMS;

  // Re-fetched on every pathname change (not just once on mount) so sending a first message on
  // the bare /chat route - which creates a brand new conversation server-side - makes it appear
  // in this list without requiring a full page reload.
  // The single way this component reads the list - every refresh goes through it, so none of them
  // can leave an unhandled rejection behind. On failure the list already on screen is KEPT (it is
  // real data, at worst slightly stale) and the error state says the refresh failed. A 503 lands
  // here like any other failure: signing out is driven only by the Supabase session
  // (useAuthSession), never by an HTTP status.
  const loadHistory = useCallback(async (): Promise<void> => {
    try {
      setConversations(await getConversations());
      setHistoryStatus("ready");
    } catch {
      setHistoryStatus("error");
    }
  }, []);

  const retryHistory = useCallback((): void => {
    setHistoryStatus("loading");
    startSlowNotice();
    void loadHistory().finally(() => stopSlowNotice());
  }, [loadHistory, startSlowNotice, stopSlowNotice]);

  useEffect(() => {
    startSlowNotice();
    void loadHistory().finally(() => stopSlowNotice());
    // Depends on the stable callbacks, NOT on the object useSlowRequestNotice returns - that object
    // is a fresh literal every render, and depending on it turned this into an infinite fetch loop
    // (fetch -> setState -> render -> new object -> fetch). Keeps the original "re-fetch on
    // pathname change" trigger and nothing else.
  }, [pathname, loadHistory, startSlowNotice, stopSlowNotice]);

  const filteredHistory = useMemo(
    () =>
      conversations.filter((conversation) => conversation.title.toLowerCase().includes(historyQuery.toLowerCase())),
    [conversations, historyQuery]
  );

  function startEditing(conversation: ConversationSummary): void {
    setEditingConversationId(conversation.conversation_id);
    setEditingTitle(conversation.title);
  }

  function cancelEditing(): void {
    setEditingConversationId(null);
    setEditingTitle("");
  }

  // Feature nhỏ - đổi tên hội thoại. Saves on Enter (via input blur) or on losing focus; an
  // unchanged/empty submission is a no-op rather than clearing the title, since the rename UI
  // has no separate "clear" affordance - PATCH-ing an empty title (which the backend treats as
  // "revert to auto-generated title") is a distinct feature not exposed here.
  async function commitEditing(conversationId: string): Promise<void> {
    const trimmed = editingTitle.trim();
    setEditingConversationId(null);

    const original = conversations.find((conversation) => conversation.conversation_id === conversationId)?.title;
    if (trimmed.length === 0 || trimmed === original) {
      return;
    }

    setConversations((current) =>
      current.map((conversation) =>
        conversation.conversation_id === conversationId ? { ...conversation, title: trimmed } : conversation
      )
    );

    try {
      await renameConversation(conversationId, trimmed);
    } catch {
      // Reported by the re-fetch below, which reverts the optimistic title to what the server has.
    } finally {
      // Re-fetch regardless of success/failure - on success this picks up the server-resolved
      // title (identical to the optimistic one here, but keeps a single source of truth); on
      // failure it reverts the optimistic update back to what the server actually has.
      void loadHistory();
    }
  }

  // Feature nhỏ - xóa hội thoại. window.confirm is a deliberately blocking, no-styling-needed
  // confirmation - "không xóa ngay khi bấm 1 lần" only requires an explicit extra step, not a
  // custom dialog component (none exists in this design system yet).
  async function handleDelete(conversation: ConversationSummary): Promise<void> {
    const confirmed = window.confirm(`Xóa hội thoại "${conversation.title}"? Hành động này không thể hoàn tác.`);
    if (!confirmed) {
      return;
    }

    setConversations((current) =>
      current.filter((item) => item.conversation_id !== conversation.conversation_id)
    );

    try {
      await deleteConversation(conversation.conversation_id);
    } catch {
      // Deletion failed server-side - restore the real list instead of leaving a conversation
      // permanently hidden by the optimistic removal above.
      void loadHistory();
      return;
    }

    // If the conversation just deleted is the one currently open, its route is now dead -
    // send the user back to the bare "new conversation" route.
    if (pathname === `/chat/${conversation.conversation_id}`) {
      onNavigate?.();
      router.replace("/chat");
    }
  }

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
        {navItems.map((item) => {
          const isActive = item === TRIAL_NAV_ITEM ? pathname.startsWith("/trial") : pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex min-h-11 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
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
          onClick={onNavigate}
          className="flex min-h-11 w-full items-center justify-center gap-2 rounded-full border border-border bg-background px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
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
        {isHistorySlow && conversations.length === 0 ? (
          <p className="px-1 pb-2 text-xs leading-relaxed text-muted-foreground">{SLOW_REQUEST_NOTICE}</p>
        ) : null}
        {historyStatus === "error" ? (
          <div
            role="alert"
            data-testid="history-error"
            className="mb-2 flex items-center justify-between gap-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-red-700"
          >
            <span>Không tải được lịch sử hội thoại.</span>
            <button
              type="button"
              onClick={retryHistory}
              className="shrink-0 rounded border border-red-300 bg-white px-2 py-0.5 font-medium hover:bg-red-100"
            >
              Thử lại
            </button>
          </div>
        ) : null}
        {historyStatus === "ready" && conversations.length === 0 ? (
          <p data-testid="history-empty" className="px-1 pb-2 text-xs text-muted-foreground">
            Chưa có hội thoại nào
          </p>
        ) : null}
        <ul className="space-y-1">
          {filteredHistory.map((conversation) => {
            const href = `/chat/${conversation.conversation_id}`;
            const isActive = pathname === href;
            const isEditing = editingConversationId === conversation.conversation_id;

            return (
              <li key={conversation.conversation_id} className="group relative">
                {isEditing ? (
                  <div className={cn("rounded-md px-3 py-2", isActive ? "bg-accent" : "bg-background")}>
                    <input
                      autoFocus
                      value={editingTitle}
                      onChange={(event) => setEditingTitle(event.target.value)}
                      onBlur={() => void commitEditing(conversation.conversation_id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.currentTarget.blur();
                        } else if (event.key === "Escape") {
                          cancelEditing();
                        }
                      }}
                      className="w-full bg-transparent text-sm font-medium text-foreground outline-none"
                    />
                    <p className="mt-1 text-xs text-muted-foreground">{formatConversationTime(conversation.updated_at)}</p>
                  </div>
                ) : (
                  <Link
                    href={href}
                    onClick={onNavigate}
                    onDoubleClick={(event) => {
                      event.preventDefault();
                      startEditing(conversation);
                    }}
                    className={cn(
                      "block w-full rounded-md py-2 pl-3 pr-24 text-left text-sm transition-colors",
                      isActive ? "bg-accent" : "hover:bg-accent"
                    )}
                  >
                    <p className="truncate font-medium text-foreground">{conversation.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatConversationTime(conversation.updated_at)}</p>
                  </Link>
                )}

                {!isEditing ? (
                  <div
                    className={cn(
                      "absolute right-0 top-1/2 flex -translate-y-1/2 items-center",
                      "opacity-0 transition-opacity max-md:opacity-100 group-hover:opacity-100"
                    )}
                  >
                    <button
                      type="button"
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        startEditing(conversation);
                      }}
                      aria-label="Đổi tên hội thoại"
                      className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-card hover:text-foreground"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        void handleDelete(conversation);
                      }}
                      aria-label="Xóa hội thoại"
                      className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-red-100 hover:text-red-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ) : null}
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
