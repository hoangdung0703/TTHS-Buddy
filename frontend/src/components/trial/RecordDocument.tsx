import { Fragment } from "react";

import { TrialText } from "@/components/trial/TrialText";
import type { TrialRecordDocument, TrialRecordEntry, TrialRecordField, TrialRecordSection } from "@/lib/types";
import { cn } from "@/lib/utils";

// The record laid out as Mẫu số 22-HS (contract 3.7). Order: disclaimer, preamble (outside the form:
// observer sessions, an unfinalised clerk draft), court name | national header, title, opening, sections, closing,
// signatures, appendix (outside the form), disclaimer.
// Every string is shown as sent - nothing is edited, shortened or filled in: a null field is the
// form's dotted blank.

function Blank() {
  return (
    <span data-testid="record-blank" className="tracking-[0.2em] text-muted-foreground print:text-black">
      ......<span className="sr-only"> (để trống)</span>
    </span>
  );
}

function FieldLine({ field }: { field: TrialRecordField }) {
  return (
    <p className="break-words">
      <span>{field.label}: </span>
      {field.value === null ? (
        <Blank />
      ) : field.simulated ? (
        <em data-testid="record-simulated">
          {field.value}
          <span className="sr-only"> (giả định)</span>
        </em>
      ) : (
        field.value
      )}
    </p>
  );
}

function Entry({ entry }: { entry: TrialRecordEntry }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="font-semibold">
        {entry.speaker_role}
        {entry.speaker_name ? ` ${entry.speaker_name}` : ""}:
      </p>
      <TrialText text={entry.text} className="pl-4 print:pl-3" />
    </div>
  );
}

function ContentLabel({ kind }: { kind: "summary" | "verbatim" | "user" | "system" }) {
  return (
    <span
      data-testid="record-content-label"
      className="ml-2 inline-flex items-center rounded-full border border-border bg-secondary px-2 py-0.5 align-middle text-[0.7rem] font-medium text-secondary-foreground print:bg-transparent"
    >
      {kind === "summary" ? "Tóm tắt" : kind === "user" ? "Người học soạn" : kind === "system" ? "Hệ thống dựng" : "Nguyên văn"}
    </span>
  );
}

function hasBody(section: TrialRecordSection): boolean {
  return (section.entries?.length ?? 0) > 0 || (section.summary ?? "").length > 0;
}

// notesFirst: the appendix's notes introduce it (heading, notes, fields, entries - contract 3.7); in
// the form's sections the fixed notes follow the content (e.g. "Hội đồng xét xử vào phòng nghị án...").
// An appendix with fields (the presiding judge's "Biên bản nghị án") is built by code from the
// student's decision and says so.
function Section({ section, level, notesFirst = false }: { section: TrialRecordSection; level: 1 | 2; notesFirst?: boolean }) {
  const notes = section.notes?.map((note, index) => (
    <p key={index} className={cn("break-words", notesFirst && "italic text-muted-foreground print:text-black")}>
      {note}
    </p>
  ));
  const isSummary = section.content === "summary" && (section.summary ?? "").length > 0;
  // Clerk sessions (contract 3.7): IV.2 and IV.3 are the student's own text, labelled as such; an
  // empty one is the form's dotted blank.
  const isUser = section.content === "user";
  const Heading = level === 1 ? "h2" : "h3";
  return (
    <section className="flex flex-col gap-3">
      <Heading className={cn("break-after-avoid font-bold", level === 1 ? "mt-4 text-base" : "mt-2 text-[0.95rem]")}>
        {section.heading}
        {/* Subsections that carry speech say whether it is the clerk's summary or verbatim. */}
        {level === 2 && isUser ? <ContentLabel kind="user" /> : null}
        {level === 2 && !isUser && hasBody(section) ? <ContentLabel kind={isSummary ? "summary" : "verbatim"} /> : null}
        {notesFirst && (section.fields?.length ?? 0) > 0 ? <ContentLabel kind="system" /> : null}
      </Heading>
      {isUser && section.author_note ? (
        <p data-testid="record-author-note" className="-mt-2 text-xs italic text-muted-foreground print:text-black">
          ({section.author_note})
        </p>
      ) : null}
      {notesFirst ? notes : null}
      {section.fields?.map((field, index) => <FieldLine key={index} field={field} />)}
      {isUser ? (
        (section.summary ?? "").length > 0 ? (
          <div data-testid="record-user-text">
            <TrialText text={section.summary ?? ""} />
          </div>
        ) : (
          <p>
            <Blank />
          </p>
        )
      ) : isSummary ? (
        <TrialText text={section.summary ?? ""} />
      ) : (
        section.entries?.map((entry) => <Entry key={entry.seq} entry={entry} />)
      )}
      {section.subsections?.map((sub, index) => <Section key={index} section={sub} level={2} />)}
      {notesFirst ? null : notes}
    </section>
  );
}

function Disclaimer({ text }: { text: string }) {
  return (
    <p data-testid="record-disclaimer" className="text-center text-xs font-medium uppercase tracking-wide text-muted-foreground print:text-[9pt] print:text-black">
      *** {text} ***
    </p>
  );
}

export function RecordDocument({ record }: { record: TrialRecordDocument }) {
  const hasSimulated = [...record.opening, ...record.closing, ...record.sections.flatMap((s) => s.fields ?? [])].some((f) => f.simulated);

  return (
    <div className="flex flex-col gap-6">
      <Disclaimer text={record.disclaimer} />

      {(record.preamble ?? []).length > 0 ? (
        <div data-testid="record-preamble" className="-mt-3 flex flex-col gap-0.5 text-center text-xs italic text-muted-foreground print:text-[9pt] print:text-black">
          {record.preamble?.map((line, index) => (
            <p key={index} className="break-words">
              {line}
            </p>
          ))}
        </div>
      ) : null}

      <p className="text-right text-[0.7rem] italic leading-snug text-muted-foreground print:text-black">{record.form_reference}</p>

      <header className="grid grid-cols-2 gap-4 text-center text-sm">
        <div className="flex flex-col items-center gap-1">
          <p className="font-bold uppercase">{record.court_name}</p>
          <span aria-hidden="true" className="h-px w-16 bg-foreground/60" />
        </div>
        <div className="flex flex-col items-center gap-0.5">
          {record.national_header.map((line, index) => (
            <p key={index} className={index === 0 ? "font-bold uppercase" : "font-semibold"}>
              {line}
            </p>
          ))}
          <span aria-hidden="true" className="mt-1 h-px w-32 bg-foreground/60" />
        </div>
      </header>

      <div className="text-center">
        <p className="text-xl font-bold tracking-wide">{record.title}</p>
        <p className="mt-1 font-bold">{record.subtitle}</p>
        {hasSimulated ? (
          <p className="mt-2 text-xs italic text-muted-foreground print:text-black">Các giá trị in nghiêng là giả định do hệ thống mô phỏng gán.</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1.5">
        {record.opening.map((field, index) => (
          <FieldLine key={index} field={field} />
        ))}
      </div>

      {record.sections.map((section, index) => (
        <Section key={index} section={section} level={1} />
      ))}

      <div className="mt-2 flex flex-col gap-1.5">
        {record.closing.map((field, index) => (
          <FieldLine key={index} field={field} />
        ))}
      </div>

      <div className="mt-4 grid break-inside-avoid grid-cols-2 gap-6 text-center">
        {record.signatures.map((signature, index) => (
          <div key={index} className="flex flex-col items-center gap-1">
            <p className="text-sm font-bold uppercase">{signature.title}</p>
            <p className="text-xs italic text-muted-foreground print:text-black">{signature.note}</p>
            <span aria-hidden="true" className="h-16" />
            <p className="font-semibold">{signature.name}</p>
          </div>
        ))}
      </div>

      {(record.appendix ?? []).length > 0 ? (
        <div data-testid="record-appendix" className="mt-6 flex flex-col gap-4 border-t-2 border-dashed border-border pt-6 print:break-before-page print:border-0 print:pt-0">
          {record.appendix?.map((section, index) => (
            <Fragment key={index}>
              <Section section={section} level={1} notesFirst />
            </Fragment>
          ))}
        </div>
      ) : null}

      <Disclaimer text={record.disclaimer} />
    </div>
  );
}
