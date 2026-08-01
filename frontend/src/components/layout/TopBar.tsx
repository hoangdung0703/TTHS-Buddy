"use client";

import { Menu } from "lucide-react";
import { useRouter } from "next/navigation";

import { getSupabaseClient } from "@/lib/supabaseClient";

interface TopBarProps {
  title: string;
  userLabel: string | null;
  // Opens the Sidebar drawer (see AuthenticatedLayout). The button itself is hidden above the
  // "md" breakpoint via CSS - desktop always shows the Sidebar directly, so there's nothing to
  // open there - rather than branching the render tree per viewport.
  onMenuClick?: () => void;
}

function getInitials(label: string | null): string {
  if (label === null || label.trim().length === 0) {
    return "SV";
  }

  return label.slice(0, 2).toUpperCase();
}

function formatVietnameseDateTime(date: Date): string {
  return new Intl.DateTimeFormat("vi-VN", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric"
  }).format(date);
}

export function TopBar({ title, userLabel, onMenuClick }: TopBarProps) {
  const router = useRouter();

  async function handleSignOut(): Promise<void> {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Mở menu điều hướng"
          className="-ml-1 flex h-9 w-9 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-accent md:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <h1 className="font-serif text-lg font-normal tracking-tight text-foreground">{title}</h1>
      </div>

      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground">{formatVietnameseDateTime(new Date())}</span>
        <button
          type="button"
          onClick={handleSignOut}
          title="Đăng xuất"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          {getInitials(userLabel)}
        </button>
      </div>
    </header>
  );
}
