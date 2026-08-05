"use client";

import { Hash } from "lucide-react";
import { useState } from "react";

import { ArticleModal } from "@/components/chat/ArticleModal";
import type { Citation } from "@/lib/types";

interface CitationListProps {
  citations: Citation[];
}

function CitationPill({ citation, onOpen }: { citation: Citation; onOpen: (citation: Citation) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      className="flex min-h-11 items-center gap-1 rounded-full border border-primary/20 bg-accent px-3 py-1.5 text-left text-xs font-medium text-accent-foreground transition-colors hover:bg-primary/15"
    >
      <Hash className="h-3 w-3" />
      Điều {citation.dieu_number} {citation.law_version}
    </button>
  );
}

export function CitationList({ citations }: CitationListProps) {
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);

  if (citations.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 space-y-2 border-t border-border pt-3">
      <p className="text-xs font-medium text-muted-foreground">Căn cứ pháp lý · {citations.length}</p>
      <div className="flex flex-wrap gap-2">
        {citations.map((citation) => (
          <CitationPill
            key={`${citation.dieu_number}-${citation.law_version}`}
            citation={citation}
            onOpen={setOpenCitation}
          />
        ))}
      </div>

      {openCitation !== null ? (
        <ArticleModal citation={openCitation} onClose={() => setOpenCitation(null)} />
      ) : null}
    </div>
  );
}
