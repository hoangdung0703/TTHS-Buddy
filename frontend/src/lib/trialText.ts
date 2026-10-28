// Plain-text structure for trial texts (contract Mục 4.1): AI utterances, the indictment and the
// record. Pure and dependency-free (tests/trialText.test.mjs loads it with Node). The output is
// plain strings only - the renderer puts them in React text nodes, never in HTML, and nothing here
// is markdown: "**", "#" or "*" stay literal characters.
//
// Convention (server-normalised): paragraphs are separated by one blank line; a line starting with
// "- " is a bullet; consecutive lines inside a paragraph are line breaks of the same block; a line
// like "II. Hành vi phạm tội và chứng cứ" is a section heading; a long paragraph may open with a
// lead phrase ending in a colon ("Về hành vi phạm tội:").

export type TrialTextBlock =
  | { type: "heading"; text: string }
  | { type: "list"; items: string[] }
  | { type: "paragraph"; lead: string | null; lines: string[] };

const HEADING_RE = /^[IVX]+\.\s/;
const BULLET_PREFIX = "- ";
// "Về <...>:" at the start of a paragraph, the whole phrase at most LEAD_MAX_CHARS long.
const LEAD_RE = /^(Về [^:\n]+:)(?=\s|$)/;
const LEAD_MAX_CHARS = 60;
// Long-speech threshold of the server convention (Mục 4.1).
const LONG_TEXT_CHARS = 600;

function splitLead(line: string): { lead: string | null; rest: string } {
  const match = LEAD_RE.exec(line);
  if (match === null || match[1].length > LEAD_MAX_CHARS) {
    return { lead: null, rest: line };
  }
  return { lead: match[1], rest: line.slice(match[1].length).replace(/^\s+/, "") };
}

export function parseTrialText(text: string): TrialTextBlock[] {
  const blocks: TrialTextBlock[] = [];
  const normalised = text.replace(/\r\n?/g, "\n");

  for (const rawParagraph of normalised.split(/\n[ \t]*\n/)) {
    const lines = rawParagraph.split("\n").filter((line) => line.trim().length > 0);
    let paragraph: { type: "paragraph"; lead: string | null; lines: string[] } | null = null;
    let list: { type: "list"; items: string[] } | null = null;

    for (const line of lines) {
      if (HEADING_RE.test(line)) {
        paragraph = null;
        list = null;
        blocks.push({ type: "heading", text: line.trim() });
      } else if (line.startsWith(BULLET_PREFIX)) {
        paragraph = null;
        if (list === null) {
          list = { type: "list", items: [] };
          blocks.push(list);
        }
        list.items.push(line.slice(BULLET_PREFIX.length).trim());
      } else {
        list = null;
        if (paragraph === null) {
          // Only the first line of a paragraph can carry the lead phrase.
          const { lead, rest } = splitLead(line);
          paragraph = { type: "paragraph", lead, lines: rest.length > 0 ? [rest] : [] };
          blocks.push(paragraph);
        } else {
          paragraph.lines.push(line);
        }
      }
    }
  }
  return blocks;
}

// A long text gets the reading layout (wider measure, paragraph spacing); a one-paragraph short
// text keeps the compact bubble.
export function isLongTrialText(text: string): boolean {
  if (text.length > LONG_TEXT_CHARS) {
    return true;
  }
  const blocks = parseTrialText(text);
  return blocks.length > 1 || blocks.some((block) => block.type !== "paragraph");
}
