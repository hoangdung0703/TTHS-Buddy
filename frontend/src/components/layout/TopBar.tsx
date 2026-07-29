"use client";

import { useRouter } from "next/navigation";

import { getSupabaseClient } from "@/lib/supabaseClient";

interface TopBarProps {
  title: string;
  userLabel: string | null;
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

export function TopBar({ title, userLabel }: TopBarProps) {
  const router = useRouter();

  async function handleSignOut(): Promise<void> {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background px-6">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>

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
