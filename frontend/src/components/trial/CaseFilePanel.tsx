"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { ArticlePill } from "@/components/trial/ArticlePill";
import { TrialText } from "@/components/trial/TrialText";
import { formatVnd, LAW_VERSION_BLHS, roleLabelForId } from "@/lib/trialRules";
import type { TrialCaseFile, TrialPerson, TrialRoleBrief } from "@/lib/types";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "summary", label: "Tóm tắt" },
  { key: "indictment", label: "Cáo trạng" },
  { key: "evidence", label: "Chứng cứ" },
  { key: "statements", label: "Lời khai" },
  { key: "people", label: "Nhân thân" }
] as const;
// Defendant sessions only (contract 3.3, Mục 9.14): the student's own character card, first.
const ROLE_TAB = { key: "role", label: "Vai của bạn" } as const;
export type CaseFileTab = (typeof TABS)[number]["key"] | typeof ROLE_TAB.key;
type TabKey = CaseFileTab;

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  vat_chung: "Vật chứng",
  giam_dinh: "Kết luận giám định",
  dinh_gia: "Kết luận định giá",
  tai_lieu: "Tài liệu"
};

const GENDER_LABELS: Record<string, string> = { nam: "Nam", nu: "Nữ" };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

function Paragraph({ children }: { children: ReactNode }) {
  return <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">{children}</p>;
}

function Empty() {
  return <p className="text-sm text-muted-foreground">Hồ sơ không có mục này.</p>;
}

// The case file panel (contract Mục 7). Shows only what the server sends; it has no place for, and
// never asks for, a verdict, character cards or a plea.
//
// Names come ONLY from the case file (display_names / <person>.name), which the server has already
// anonymised ("Trần Đức H"); never from `participants`, which carries full names for the transcript
// (contract Mục 7, Mục 9.12). Nothing here rebuilds or replaces a name.
export function CaseFilePanel({
  caseFile,
  isInjuryCase,
  tab: controlledTab,
  onTabChange,
  wide = false,
  roleBrief = null
}: {
  caseFile: TrialCaseFile;
  // Điều 134: measure_value is % tổn thương cơ thể, not đồng.
  isInjuryCase: boolean;
  // Optional controlled tab, so the side panel and the expanded view stay on the same tab.
  tab?: CaseFileTab;
  onTabChange?: (tab: CaseFileTab) => void;
  // Expanded reading view: larger type for the indictment and statements.
  wide?: boolean;
  // Defendant sessions: adds the "Vai của bạn" tab. Null (or a missing key) for every other role.
  roleBrief?: TrialRoleBrief | null;
}) {
  const [ownTab, setOwnTab] = useState<TabKey>("summary");
  const tabs: ReadonlyArray<{ key: TabKey; label: string }> = roleBrief ? [ROLE_TAB, ...TABS] : TABS;
  const wanted = controlledTab ?? ownTab;
  const tab: TabKey = tabs.some((item) => item.key === wanted) ? wanted : "summary";
  const setTab = (next: TabKey) => {
    setOwnTab(next);
    onTabChange?.(next);
  };
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const baseId = useId();

  const displayName = (id: string): string => {
    const fromMap = caseFile.display_names?.[id];
    if (fromMap) {
      return fromMap;
    }
    const people = [caseFile.defendant, caseFile.victim, caseFile.related_party, ...(caseFile.witnesses ?? [])];
    return people.find((person) => person?.id === id)?.name ?? "";
  };
  const nameOf = (id: string) => [roleLabelForId(id), displayName(id)].filter(Boolean).join(" ") || id;
  const textSize = wide ? "text-base" : "text-[0.9375rem]";

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const index = tabs.findIndex((item) => item.key === tab);
    let next = index;
    if (event.key === "ArrowRight") {
      next = (index + 1) % tabs.length;
    } else if (event.key === "ArrowLeft") {
      next = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = tabs.length - 1;
    } else {
      return;
    }
    event.preventDefault();
    setTab(tabs[next].key);
    tabRefs.current[next]?.focus();
  }

  const charge = caseFile.charge;

  return (
    <div className="flex min-h-0 min-w-0 flex-col">
      {/* Wraps onto a second row instead of scrolling, so all five tabs are visible from 320px up. */}
      <div role="tablist" aria-label="Hồ sơ vụ án" onKeyDown={handleKeyDown} className="flex flex-wrap gap-1.5 border-b border-border pb-3">
        {tabs.map((item, index) => (
          <button
            key={item.key}
            ref={(element) => {
              tabRefs.current[index] = element;
            }}
            id={`${baseId}-tab-${item.key}`}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            aria-controls={`${baseId}-panel-${item.key}`}
            tabIndex={tab === item.key ? 0 : -1}
            onClick={() => setTab(item.key)}
            className={cn(
              "min-h-9 rounded-full border px-3 text-[0.8125rem] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              tab === item.key
                ? "border-primary bg-primary font-medium text-primary-foreground"
                : "border-border bg-background text-muted-foreground hover:bg-accent/15 hover:text-foreground"
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div
        id={`${baseId}-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`${baseId}-tab-${tab}`}
        tabIndex={0}
        className="flex min-w-0 flex-col gap-5 overflow-y-auto py-4 focus-visible:outline-none"
      >
        {tab === "role" && roleBrief ? <RoleBriefView brief={roleBrief} /> : null}

        {tab === "summary" ? (
          <>
            {caseFile.title ? <p className="font-serif text-lg font-light leading-snug text-foreground">{caseFile.title}</p> : null}
            {charge ? (
              <Section title="Tội danh truy tố">
                <Paragraph>{charge.crime_name}</Paragraph>
                <div className="flex flex-wrap items-center gap-1.5">
                  <ArticlePill
                    dieu={charge.dieu}
                    lawVersion={LAW_VERSION_BLHS}
                    label={`Khoản ${charge.khoan}${charge.diem && charge.diem.length > 0 ? `, điểm ${charge.diem.join(", ")}` : ""} Điều ${charge.dieu} BLHS`}
                  />
                </div>
              </Section>
            ) : null}
            {caseFile.incident_summary ? (
              <Section title="Tóm tắt vụ việc">
                <Paragraph>{caseFile.incident_summary}</Paragraph>
              </Section>
            ) : null}
            {typeof caseFile.measure_value === "number" ? (
              <Section title={isInjuryCase ? "Tỷ lệ tổn thương cơ thể" : "Giá trị tài sản"}>
                <Paragraph>{isInjuryCase ? `${caseFile.measure_value}%` : formatVnd(caseFile.measure_value)}</Paragraph>
              </Section>
            ) : null}
            {caseFile.facts && caseFile.facts.length > 0 ? (
              <Section title="Diễn biến">
                <ol className="flex flex-col gap-2">
                  {caseFile.facts.map((fact) => (
                    <li key={fact.id} className="text-sm leading-relaxed text-foreground">
                      {fact.time || fact.place ? (
                        <span className="block text-xs text-muted-foreground">{[fact.time, fact.place].filter(Boolean).join(" · ")}</span>
                      ) : null}
                      <span className="whitespace-pre-wrap break-words">{fact.description}</span>
                    </li>
                  ))}
                </ol>
              </Section>
            ) : null}
            {(caseFile.aggravating?.length ?? 0) > 0 || (caseFile.mitigating?.length ?? 0) > 0 ? (
              <Section title="Tình tiết được nêu trong hồ sơ">
                <div className="flex flex-wrap gap-1.5">
                  {caseFile.aggravating?.map((item) => (
                    <ArticlePill key={`a-${item.khoan}-${item.diem}`} dieu="52" lawVersion={LAW_VERSION_BLHS} label={`Tăng nặng: điểm ${item.diem} khoản ${item.khoan} Điều 52 BLHS`} />
                  ))}
                  {caseFile.mitigating?.map((item) => (
                    <ArticlePill key={`m-${item.khoan}-${item.diem}`} dieu="51" lawVersion={LAW_VERSION_BLHS} label={`Giảm nhẹ: điểm ${item.diem} khoản ${item.khoan} Điều 51 BLHS`} />
                  ))}
                </div>
              </Section>
            ) : null}
            {caseFile.civil_claim ? (
              <Section title="Yêu cầu bồi thường">
                <Paragraph>
                  {nameOf(caseFile.civil_claim.claimant_id)} yêu cầu {formatVnd(caseFile.civil_claim.amount_vnd)}
                  {caseFile.civil_claim.basis ? `. ${caseFile.civil_claim.basis}` : ""}
                </Paragraph>
              </Section>
            ) : null}
            {typeof caseFile.compensation_vnd === "number" ? (
              <Section title="Đã bồi thường">
                <Paragraph>{formatVnd(caseFile.compensation_vnd)}</Paragraph>
              </Section>
            ) : null}
          </>
        ) : null}

        {tab === "indictment" ? (
          caseFile.indictment_text ? (
            <TrialText text={caseFile.indictment_text} className={cn("text-foreground", textSize, wide && "max-w-[68ch]")} />
          ) : (
            <Empty />
          )
        ) : null}

        {tab === "evidence" ? (
          <>
            {caseFile.evidence && caseFile.evidence.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {caseFile.evidence.map((item) => (
                  <li key={item.id} className="rounded-lg border border-border bg-background px-3 py-2.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      {item.id} · {EVIDENCE_TYPE_LABELS[item.type] ?? item.type}
                    </p>
                    <Paragraph>{item.description}</Paragraph>
                    {typeof item.value_vnd === "number" ? <p className="mt-1 text-xs text-muted-foreground">Giá trị: {formatVnd(item.value_vnd)}</p> : null}
                    {typeof item.injury_percent === "number" ? (
                      <p className="mt-1 text-xs text-muted-foreground">Tỷ lệ tổn thương: {item.injury_percent}%</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty />
            )}
            {caseFile.extra_amounts && caseFile.extra_amounts.length > 0 ? (
              <Section title="Các khoản tiền khác">
                <ul className="flex flex-col gap-1">
                  {caseFile.extra_amounts.map((item) => (
                    <li key={`${item.label}-${item.amount_vnd}`} className="text-sm text-foreground">
                      {item.label}: {formatVnd(item.amount_vnd)}
                      {item.evidence_id ? <span className="text-xs text-muted-foreground"> ({item.evidence_id})</span> : null}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
          </>
        ) : null}

        {tab === "statements" ? (
          caseFile.pretrial_statements && caseFile.pretrial_statements.length > 0 ? (
            <ul className="flex flex-col gap-4">
              {caseFile.pretrial_statements.map((statement) => (
                <li key={statement.person_id} className="flex flex-col gap-1">
                  <p className="text-xs font-semibold text-foreground">{nameOf(statement.person_id)}</p>
                  <TrialText text={statement.summary} density={wide ? "reading" : "compact"} className={cn("text-foreground", wide ? textSize : "text-sm")} />
                  {statement.inconsistencies && statement.inconsistencies.length > 0 ? (
                    <ul className="mt-1 flex flex-col gap-1 border-l-2 border-accent/60 pl-3">
                      {statement.inconsistencies.map((item, index) => (
                        <li key={index} className="text-xs leading-relaxed text-muted-foreground">
                          Điểm chưa thống nhất: {item.text}
                          {typeof item.claimed_amount_vnd === "number" ? ` (${formatVnd(item.claimed_amount_vnd)})` : ""}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <Empty />
          )
        ) : null}

        {tab === "people" ? (
          <div className="flex flex-col gap-4">
            {caseFile.defendant ? <PersonCard person={caseFile.defendant} title={nameOf(caseFile.defendant.id)} detailed /> : null}
            {caseFile.victim ? <PersonCard person={caseFile.victim} title={nameOf(caseFile.victim.id)} /> : null}
            {caseFile.witnesses?.map((witness) => <PersonCard key={witness.id} person={witness} title={nameOf(witness.id)} />)}
            {caseFile.related_party ? <PersonCard person={caseFile.related_party} title={nameOf(caseFile.related_party.id)} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// The character card as a role-play hint, never as proven facts: the server's note leads, verbatim.
function RoleBriefView({ brief }: { brief: TrialRoleBrief }) {
  return (
    <div data-testid="trial-role-brief" className="flex flex-col gap-4">
      <p data-testid="trial-role-brief-note" className="rounded-lg border border-primary/15 bg-secondary/40 px-3 py-2 text-sm leading-relaxed text-foreground">
        {brief.note}
      </p>
      {brief.stance ? (
        <Section title="Lập trường gợi ý">
          <Paragraph>{brief.stance}</Paragraph>
        </Section>
      ) : null}
      {brief.knowledge.length > 0 ? (
        <Section title="Những gì nhân vật biết">
          <ul className="flex list-disc flex-col gap-1 pl-5 text-sm leading-relaxed text-foreground">
            {brief.knowledge.map((item, index) => (
              <li key={index} className="break-words">
                {item}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {brief.demeanor ? (
        <Section title="Thái độ">
          <Paragraph>{brief.demeanor}</Paragraph>
        </Section>
      ) : null}
    </div>
  );
}

function PersonCard({ person, title, detailed }: { person: TrialPerson; title: string; detailed?: boolean }) {
  const rows: Array<[string, string | number | null | undefined]> = [
    ["Giới tính", person.gender ? GENDER_LABELS[person.gender] ?? person.gender : null],
    ["Tuổi", person.age],
    ["Nghề nghiệp", person.occupation],
    ["Nơi cư trú", person.residence_place]
  ];
  if (detailed) {
    rows.push(["Trình độ học vấn", person.education], ["Tiền án, tiền sự", person.prior_record], ["Biện pháp ngăn chặn", person.preventive_measure]);
  }
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2.5">
      <p className="mb-1.5 text-sm font-semibold text-foreground">{title}</p>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
        {rows
          .filter(([, value]) => value !== null && value !== undefined && value !== "")
          .map(([label, value]) => (
            <InfoRow key={label} label={label} value={String(value)} />
          ))}
      </dl>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="break-words text-foreground">{value}</dd>
    </>
  );
}
