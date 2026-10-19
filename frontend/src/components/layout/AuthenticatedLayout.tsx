"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useAuthSession } from "@/hooks/useAuthSession";
import { warmUpBackend } from "@/lib/serverWakeup";

interface AuthenticatedLayoutProps {
  title: string;
  children: ReactNode;
}

// Shared shell for every page behind login (chat, quiz, dashboard):
// verifies the Supabase session, then renders the sidebar + top bar around the page content.
//
// Below the "md" breakpoint the fixed-width Sidebar (see requirements.md "Sidebar mobile
// responsive") is replaced by a hamburger-triggered drawer: same Sidebar component/content,
// rendered as a fixed overlay instead of a permanent flex column, closing on backdrop click,
// the X button, or picking a nav/history item (Sidebar's onNavigate callback). Desktop (md+)
// keeps rendering the exact same always-visible Sidebar as before.
export function AuthenticatedLayout({ title, children }: AuthenticatedLayoutProps) {
  const { loading, email } = useAuthSession();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  // Runs before the early `loading` return below, so the ping goes out while the session check is
  // still in flight rather than waiting for it. warmUpBackend rate-limits itself to once per 10
  // minutes per session, so remounting across pages behind login costs at most one ping.
  useEffect(() => {
    warmUpBackend();
  }, []);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Đang kiểm tra phiên đăng nhập...</p>
      </main>
    );
  }

  return (
    // print:* lets a page (the trial record) print as a plain document: no sidebar or top bar, and
    // no fixed-height scroll container clipping it to one screen.
    <div className="flex h-screen overflow-hidden bg-background print:block print:h-auto print:overflow-visible print:bg-white">
      <div className="hidden md:flex print:hidden">
        <Sidebar userLabel={email} />
      </div>

      {isMobileNavOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Đóng menu điều hướng (nhấn ra ngoài)"
            onClick={() => setIsMobileNavOpen(false)}
            className="absolute inset-0 bg-black/40"
          />
          <div className="relative z-10 h-full w-72 max-w-[85vw] shadow-xl">
            <Sidebar userLabel={email} onNavigate={() => setIsMobileNavOpen(false)} />
            <button
              type="button"
              aria-label="Đóng menu điều hướng"
              onClick={() => setIsMobileNavOpen(false)}
              className="absolute -right-14 top-4 flex h-11 w-11 items-center justify-center rounded-full bg-card text-foreground shadow-md"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-1 flex-col overflow-hidden print:block print:overflow-visible">
        <div className="contents print:hidden">
          <TopBar title={title} userLabel={email} onMenuClick={() => setIsMobileNavOpen(true)} />
        </div>
        <div className="flex-1 overflow-y-auto print:overflow-visible">{children}</div>
      </div>
    </div>
  );
}
