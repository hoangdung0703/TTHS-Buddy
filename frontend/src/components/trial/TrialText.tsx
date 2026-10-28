import { Fragment } from "react";

import { parseTrialText } from "@/lib/trialText";
import { cn } from "@/lib/utils";

// Renders a trial text by the plain-text convention of contract Mục 4.1 (see lib/trialText.ts):
// paragraphs, "- " bullets, "I. ..." headings and a bold "Về ...:" lead. Text is only ever placed in
// React text nodes - no HTML injection, no markdown. Copying still copies the source text.
//
// density: "compact" for short chat bubbles, "reading" for long speeches, the indictment and the
// record (paragraph spacing and a calmer line height).
export function TrialText({
  text,
  density = "reading",
  className
}: {
  text: string;
  density?: "compact" | "reading";
  className?: string;
}) {
  const blocks = parseTrialText(text);
  const reading = density === "reading";

  return (
    <div className={cn("min-w-0 break-words", reading ? "space-y-3 leading-7" : "space-y-2 leading-relaxed", className)}>
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return (
            <p key={index} data-trial-text="heading" className={cn("font-semibold tracking-tight", index > 0 && reading && "pt-2")}>
              {block.text}
            </p>
          );
        }
        if (block.type === "list") {
          return (
            <ul key={index} data-trial-text="list" className="list-disc space-y-1 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{item}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} data-trial-text="paragraph">
            {block.lead !== null ? (
              <strong data-trial-text="lead" className="font-semibold">
                {block.lead}
                {block.lines.length > 0 ? " " : ""}
              </strong>
            ) : null}
            {block.lines.map((line, lineIndex) => (
              <Fragment key={lineIndex}>
                {lineIndex > 0 ? <br /> : null}
                {line}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
