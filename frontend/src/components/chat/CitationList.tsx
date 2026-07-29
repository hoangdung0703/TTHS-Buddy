"use client";

import { Hash } from "lucide-react";
import { useState } from "react";

import type { Citation } from "@/lib/types";

interface CitationListProps {
  citations: Citation[];
}

function CitationPill({ citation }: { citation: Citation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <button
      type="button"
      onClick={() => setExpanded((current) => !current)}
      className="flex flex-col items-start gap-1 rounded-full border border-primary/20 bg-accent px-3 py-1.5 text-left text-xs font-medium text-accent-foreground transition-colors hover:bg-primary/15"
    >
      <span className="flex items-center gap-1">
        <Hash className="h-3 w-3" />
        Điều {citation.dieu_number} {citation.law_version}
      </span>
      {expanded ? (
        <span className="max-w-xs whitespace-normal text-[11px] font-normal text-muted-foreground">
          {citation.dieu_title}
        </span>
      ) : null}
    </button>
  );
}

export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 space-y-2 border-t border-border pt-3">
      <p className="text-xs font-medium text-muted-foreground">Căn cứ pháp lý · {citations.length}</p>
      <div className="flex flex-wrap gap-2">
        {citations.map((citation) => (
          <CitationPill key={`${citation.dieu_number}-${citation.law_version}`} citation={citation} />
        ))}
      </div>
    </div>
  );
}
