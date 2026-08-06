"use client";

import { AlertCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

import { FormattedAnswer } from "@/components/chat/FormattedAnswer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, getLegalArticle } from "@/lib/api";
import type { Citation, LegalArticle } from "@/lib/types";

interface ArticleModalProps {
  citation: Citation;
  onClose: () => void;
}

// Citation-pill "read full article" panel (see requirements.md "Feature nhỏ - Xem toàn văn
// Điều luật từ citation pill"). A modal instead of navigating away, per that requirement - the
// student stays on the chat page and the conversation/streaming state is untouched.
export function ArticleModal({ citation, onClose }: ArticleModalProps) {
  const [article, setArticle] = useState<LegalArticle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

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

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-8"
      onClick={onClose}
      role="presentation"
    >
      <Card
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto"
        onClick={(event) => event.stopPropagation()}
      >
        <CardHeader className="flex-row items-start justify-between gap-4 border-b border-border">
          <div>
            <CardTitle className="font-serif text-xl font-light tracking-tight text-foreground">
              Điều {citation.dieu_number}
              {article?.dieu_title ? ` — ${article.dieu_title}` : ""}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{citation.law_version}</p>
          </div>
          <button
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
    </div>
  );
}
