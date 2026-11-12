"use client";

import { AlertCircle, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { FormattedAnswer } from "@/components/chat/FormattedAnswer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useModalLayer } from "@/hooks/useModalLayer";
import { ApiError, getLegalArticle } from "@/lib/api";
import type { Citation, LegalArticle } from "@/lib/types";

interface ArticleModalProps {
  citation: Citation;
  // The pill that was clicked (event.currentTarget), where focus returns on close.
  opener: HTMLElement | null;
  onClose: () => void;
}

// Citation-pill "read full article" panel (see requirements.md "Feature nhỏ - Xem toàn văn
// Điều luật từ citation pill"). A modal instead of navigating away, per that requirement - the
// student stays on the chat page and the conversation/streaming state is untouched.
// Rendered in a portal on document.body: the pills that open it sit inside cards, sticky docks
// and drawers that create their own stacking context (e.g. "relative z-10"), and a fixed overlay
// left inside one of those is painted under that context's later siblings.
export function ArticleModal({ citation, opener, onClose }: ArticleModalProps) {
  const [article, setArticle] = useState<LegalArticle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef(opener);
  const titleId = useId();

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setArticle(null);

    getLegalArticle(citation.dieu_number, citation.law_version)
      .then((result) => {
        if (!cancelled) {
          setArticle(result);
        }
      })
      .catch((fetchError: unknown) => {
        if (cancelled) {
          return;
        }
        const message =
          fetchError instanceof ApiError && fetchError.status === 404
            ? "Không tìm thấy toàn văn Điều này trong dữ liệu đã nạp."
            : "Không thể tải toàn văn Điều luật, vui lòng thử lại.";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [citation.dieu_number, citation.law_version]);

  // Scroll lock, focus trap, Esc (this dialog only, not a drawer it was opened from) and focus
  // back to the pill that opened it.
  useModalLayer({ open: true, containerRef: dialogRef, initialFocusRef: closeRef, returnFocusRef: openerRef, onClose });

  return createPortal(
    <div
      data-testid="article-modal-overlay"
      className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 px-4 py-8 print:hidden"
      onClick={(event) => {
        // React events bubble through the portal to the opener's tree; keep them here.
        event.stopPropagation();
        onClose();
      }}
      role="presentation"
    >
      <Card
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="article-modal"
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto overscroll-contain"
        onClick={(event) => event.stopPropagation()}
      >
        <CardHeader className="flex-row items-start justify-between gap-4 border-b border-border">
          <div>
            <CardTitle id={titleId} className="font-serif text-xl font-light tracking-tight text-foreground">
              Điều {citation.dieu_number}
              {article?.dieu_title ? ` — ${article.dieu_title}` : ""}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{citation.law_version}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </CardHeader>

        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <span className="flex gap-1">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
              </span>
              Đang tải toàn văn Điều luật...
            </div>
          ) : null}

          {!isLoading && error !== null ? (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          ) : null}

          {!isLoading && article !== null ? <FormattedAnswer text={article.full_text} /> : null}
        </CardContent>
      </Card>
    </div>,
    document.body
  );
}
