"use client";

import { useState } from "react";

import { ArticleModal } from "@/components/chat/ArticleModal";
import { cn } from "@/lib/utils";

// "Điều N <luật>" pill that opens the shared full-text ArticleModal.
export function ArticlePill({
  dieu,
  lawVersion,
  label,
  className
}: {
  dieu: string;
  lawVersion: string;
  label: string;
  className?: string;
}) {
  // The clicked pill itself (event.currentTarget): focus returns there when the dialog closes.
  const [opener, setOpener] = useState<HTMLElement | null>(null);

  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpener(event.currentTarget);
        }}
        className={cn(
          "inline-flex min-h-8 items-center rounded-full border border-border bg-background px-2.5 py-0.5 text-xs font-medium text-foreground transition-colors hover:bg-accent/20",
          className
        )}
        aria-label={`Xem toàn văn ${label}`}
      >
        {label}
      </button>
      {opener !== null ? (
        <ArticleModal citation={{ dieu_number: dieu, dieu_title: "", law_version: lawVersion }} opener={opener} onClose={() => setOpener(null)} />
      ) : null}
    </>
  );
}
