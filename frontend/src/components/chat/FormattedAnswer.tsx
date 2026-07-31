import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

interface FormattedAnswerProps {
  text: string;
}

const STANDALONE_BOLD_LINE_PATTERN = /^\*\*[^*]+\*\*$/;

// Gemini answers occasionally use a paragraph that is ENTIRELY "**bold**" as a pseudo section
// heading (e.g. "**Đối tượng áp dụng**" followed by its own paragraph) - not standard Markdown,
// so remark never treats it as a heading. Rewrite just those paragraphs into a real "### " heading
// before handing the rest of the text to the Markdown renderer, which handles every other case
// (bold, numbered/bulleted lists, arbitrary nesting) natively instead of via hand-rolled regex.
function promotePseudoHeadings(text: string): string {
  return text
    .split("\n\n")
    .map((block) => {
      const trimmed = block.trim();
      return STANDALONE_BOLD_LINE_PATTERN.test(trimmed) ? `### ${trimmed.slice(2, -2)}` : block;
    })
    .join("\n\n");
}

const markdownComponents: Components = {
  p: ({ children }) => <p>{children}</p>,
  h1: ({ children }) => <p className="font-serif text-base font-medium tracking-tight text-foreground">{children}</p>,
  h2: ({ children }) => <p className="font-serif text-base font-medium tracking-tight text-foreground">{children}</p>,
  h3: ({ children }) => <p className="font-serif text-base font-medium tracking-tight text-foreground">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 marker:text-muted-foreground">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-2 pl-5 marker:text-muted-foreground">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>
};

export function FormattedAnswer({ text }: FormattedAnswerProps) {
  return (
    <div className="space-y-3 text-sm leading-7 text-foreground [&_ul]:mt-1 [&_ol]:mt-1">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {promotePseudoHeadings(text)}
      </ReactMarkdown>
    </div>
  );
}
