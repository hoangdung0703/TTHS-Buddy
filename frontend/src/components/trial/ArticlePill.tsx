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
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
        className={cn(
          "inline-flex min-h-8 items-center rounded-full border border-border bg-background px-2.5 py-0.5 text-xs font-medium text-foreground transition-colors hover:bg-accent/20",
          className
        )}
        aria-label={`Xem toàn văn ${label}`}
      >
        {label}
      </button>
      {open ? (
        <ArticleModal citation={{ dieu_number: dieu, dieu_title: "", law_version: lawVersion }} onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}
