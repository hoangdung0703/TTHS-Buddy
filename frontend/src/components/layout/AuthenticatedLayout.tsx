"use client";

import type { ReactNode } from "react";

import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useAuthSession } from "@/hooks/useAuthSession";

interface AuthenticatedLayoutProps {
  title: string;
  children: ReactNode;
}

// Shared shell for every page behind login (chat, quiz, essay, dashboard):
// verifies the Supabase session, then renders the sidebar + top bar around the page content.
export function AuthenticatedLayout({ title, children }: AuthenticatedLayoutProps) {
  const { loading, email } = useAuthSession();

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Đang kiểm tra phiên đăng nhập...</p>
      </main>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar userLabel={email} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar title={title} userLabel={email} />
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
