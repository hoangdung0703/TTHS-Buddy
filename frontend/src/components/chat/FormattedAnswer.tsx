import { Fragment } from "react";

interface FormattedAnswerProps {
  text: string;
}

const BOLD_SEGMENT_PATTERN = /(\*\*[^*]+\*\*)/g;
const NUMBERED_LINE_PATTERN = /^\d+\.\s+/;

// Renders the limited markdown-like subset used in RAG answers (bold subheadings,
// numbered consequence/condition lists) without pulling in a full markdown parser.
function renderInlineBold(segment: string, keyPrefix: string) {
  const parts = segment.split(BOLD_SEGMENT_PATTERN).filter((part) => part.length > 0);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${keyPrefix}-${index}`} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }

    return <Fragment key={`${keyPrefix}-${index}`}>{part}</Fragment>;
  });
}

export function FormattedAnswer({ text }: FormattedAnswerProps) {
  const blocks = text.split("\n\n").filter((block) => block.trim().length > 0);

  return (
    <div className="space-y-3 text-sm leading-7 text-foreground">
      {blocks.map((block, blockIndex) => {
        const lines = block.split("\n");
        const isNumberedList = lines.every((line) => NUMBERED_LINE_PATTERN.test(line.trim()));
        const isHeading = /^\*\*[^*]+\*\*$/.test(block.trim());

        if (isHeading) {
          return (
            <p key={blockIndex} className="font-serif text-base font-medium tracking-tight text-foreground">
              {block.trim().slice(2, -2)}
            </p>
          );
        }

        if (isNumberedList) {
          return (
            <ol key={blockIndex} className="list-decimal space-y-2 pl-5">
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInlineBold(line.trim().replace(NUMBERED_LINE_PATTERN, ""), `${blockIndex}-${lineIndex}`)}</li>
              ))}
            </ol>
          );
        }

        return <p key={blockIndex}>{renderInlineBold(block, `${blockIndex}`)}</p>;
      })}
    </div>
  );
}
