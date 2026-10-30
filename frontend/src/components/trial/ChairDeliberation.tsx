"use client";

import { AlertCircle, ArrowRight, CheckCircle2, ClipboardCheck, Gavel, Info, Lock, Plus, Save, ScrollText, Trash2, Users, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";

import { ArticlePill } from "@/components/trial/ArticlePill";
import { TrialText } from "@/components/trial/TrialText";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  DECISION_UNSET_MESSAGES,
  decisionFieldShown,
  decisionFindingsFor,
  DISPOSITION_LABELS,
  formatSavedTime,
  formatVnd,
  LAW_VERSION_BLHS,
  LAW_VERSION_BLTTHS,
  legalBasisArticle,
  monthsLabel,
  parseWholeNumber,
  PENALTY_TYPE_LABELS,
  penaltyFrameText,
  type DecisionFormValues
} from "@/lib/trialRules";
import type {
  TrialCaseFile,
  TrialDecisionCheck,
  TrialDecisionCircumstance,
  TrialDecisionDraft,
  TrialDecisionFinding,
  TrialDecisionState,
  TrialExhibitDisposition,
  TrialPenaltyType
} from "@/lib/types";
import { cn } from "@/lib/utils";

// The presiding judge's deliberation room (steps 10-11, contract 3.11 and 5.4). Everything here is
// the student's own decision: no AI decision exists in this role and none is ever shown. The form's
// choices come from state.decision.form; the findings next to each field are the server's check of
// the SAVED draft (feedback, never a score). Nothing in this room goes into the transcript except
// the judgment the student pronounces.

const fieldAnchor = (field: string) => `decision-field-${field.replace(/\W/g, "-")}`;

// --- Findings -------------------------------------------------------------------------------------

function BasisPills({ basis }: { basis: readonly string[] }) {
  if (basis.length === 0) {
    return null;
  }
  return (
    <span className="flex flex-wrap gap-1.5">
      {basis.map((citation) => {
        const article = legalBasisArticle(citation);
        return article !== null ? (
          <ArticlePill key={citation} dieu={article.dieu} lawVersion={article.lawVersion} label={citation} className="h-auto min-h-7 px-2 text-left text-[0.7rem] font-normal" />
        ) : (
          <span key={citation} className="text-[0.7rem] text-muted-foreground">
            {citation}
          </span>
        );
      })}
    </span>
  );
}

function FindingLine({ finding, kind }: { finding: TrialDecisionFinding; kind: "error" | "warning" }) {
  const Icon = kind === "error" ? AlertCircle : Info;
  return (
    <li
      data-testid={kind === "error" ? "decision-error" : "decision-warning"}
      data-code={finding.code}
      className={cn(
        "flex flex-col gap-1.5 rounded-md border px-2.5 py-2 text-xs leading-relaxed",
        kind === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-900"
      )}
    >
      <span className="flex items-start gap-1.5">
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="min-w-0 break-words">
          <span className="font-semibold">{kind === "error" ? "Cần sửa: " : "Lưu ý: "}</span>
          {finding.message}
        </span>
      </span>
      <BasisPills basis={finding.basis} />
    </li>
  );
}

// The findings about one field, right under it.
function FieldFindings({ check, field }: { check: TrialDecisionCheck | null; field: string }) {
  const { errors, warnings } = decisionFindingsFor(check, field);
  if (errors.length === 0 && warnings.length === 0) {
    return null;
  }
  return (
    <ul data-testid="decision-field-findings" data-field={field} className="flex flex-col gap-1.5">
      {errors.map((finding, index) => (
        <FindingLine key={`e${index}`} finding={finding} kind="error" />
      ))}
      {warnings.map((finding, index) => (
        <FindingLine key={`w${index}`} finding={finding} kind="warning" />
      ))}
    </ul>
  );
}

function jumpTo(field: string): void {
  const target = document.getElementById(fieldAnchor(field)) ?? document.getElementById(fieldAnchor(field.replace(/\[\d+\]$/, "")));
  target?.scrollIntoView({ block: "center", behavior: "smooth" });
  target?.querySelector<HTMLElement>("input, select, textarea, button")?.focus({ preventScroll: true });
}

// --- Form building blocks -----------------------------------------------------------------------------

function Group({ field, title, basis, children, testId }: { field: string; title: string; basis?: ReactNode; children: ReactNode; testId?: string }) {
  return (
    <fieldset id={fieldAnchor(field)} data-testid={testId} className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4">
      <legend className="sr-only">{title}</legend>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {basis}
      </div>
      {children}
    </fieldset>
  );
}

function Choice({
  name,
  checked,
  onChange,
  disabled,
  children,
  type = "radio",
  testId
}: {
  name: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
  type?: "radio" | "checkbox";
  testId?: string;
}) {
  return (
    <label
      className={cn(
        "flex min-h-11 cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2 text-sm transition-colors",
        checked ? "border-primary/40 bg-primary/[0.05]" : "border-border hover:bg-accent/10",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      <input
        type={type}
        name={name}
        checked={checked}
        disabled={disabled}
        data-testid={testId}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
      />
      <span className="min-w-0 flex-1 break-words">{children}</span>
    </label>
  );
}

function NumberBox({
  id,
  label,
  value,
  onChange,
  unit,
  hint,
  testId
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  unit: string;
  hint?: string;
  testId: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-sm text-foreground">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          inputMode="numeric"
          autoComplete="off"
          data-testid={testId}
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/[^\d.\s]/g, ""))}
          className="h-11 w-40 max-w-full tabular-nums"
        />
        <span className="text-sm text-muted-foreground">{unit}</span>
      </div>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

const lettersLabel = (letters: readonly string[]) => letters.map((letter) => letter || "(không có điểm)").join(", ");

// --- The form (step 10, before the decision is locked) ---------------------------------------------------

interface DecisionFormProps {
  decision: TrialDecisionState;
  values: DecisionFormValues;
  onChange: (values: DecisionFormValues) => void;
  caseFile: TrialCaseFile;
  // Schema-required choices the student tried to save without ("guilty", "penalty_type").
  unset: readonly string[];
  dirty: boolean;
  disabled: boolean;
}

export function DecisionForm({ decision, values, onChange, caseFile, unset, dirty, disabled }: DecisionFormProps) {
  const { form, check } = decision;
  const id = useId();
  const set = <K extends keyof DecisionFormValues>(key: K, value: DecisionFormValues[K]) => onChange({ ...values, [key]: value });
  const frame = form.frames[values.khoan];
  const factText = (factId: string) => caseFile.facts?.find((fact) => fact.id === factId)?.description ?? "";
  const evidenceText = (evidenceId: string) => caseFile.evidence?.find((item) => item.id === evidenceId)?.description ?? "";
  const reasoningLength = values.reasoning_summary.trim().length;
  const { min: reasoningMin, max: reasoningMax } = form.reasoning_limits;
  const months = parseWholeNumber(values.penalty_months);
  const unsetLine = (field: string, message: string) =>
    unset.includes(field) ? (
      <p role="alert" data-testid="decision-unset" className="text-xs text-red-700">
        {message}
      </p>
    ) : null;

  function changeKhoan(khoan: string): void {
    // Điểm of another khoản would only come back as "diem_unknown": they go with the khoản.
    const letters = form.diem[khoan] ?? [];
    onChange({ ...values, khoan, diem: values.diem.filter((letter) => letters.includes(letter)) });
  }

  function changePenalty(type: TrialPenaltyType): void {
    // Án treo only goes with tù; the hidden boxes must not keep sending a value.
    onChange(type === "tu" ? { ...values, penalty_type: type } : { ...values, penalty_type: type, suspended: false, probation_months: "" });
  }

  const rows = { mitigating: values.mitigating.length, aggravating: values.aggravating.length };
  const orphans = check === null ? [] : [...check.errors.map((f) => ({ f, kind: "error" as const })), ...check.warnings.map((f) => ({ f, kind: "warning" as const }))]
    .filter(({ f }) => !decisionFieldShown(f.field, rows));

  return (
    <div data-testid="decision-form" className="flex min-w-0 flex-col gap-4" aria-disabled={disabled || undefined}>
      <CheckSummary decision={decision} dirty={dirty} />
      {orphans.length > 0 ? (
        <ul className="flex flex-col gap-1.5" data-testid="decision-orphan-findings">
          {orphans.map(({ f, kind }, index) => (
            <FindingLine key={index} finding={f} kind={kind} />
          ))}
        </ul>
      ) : null}

      <Group
        field="guilty"
        title="1. Tội danh"
        testId="decision-group-charge"
        basis={<ArticlePill dieu={form.dieu} lawVersion={LAW_VERSION_BLHS} label={`Điều ${form.dieu} BLHS`} className="min-h-7 px-2 text-[0.7rem] font-normal" />}
      >
        <div role="radiogroup" aria-label="Có tội hay không" className="grid gap-2 sm:grid-cols-2">
          <Choice name={`${id}-guilty`} checked={values.guilty === true} onChange={() => set("guilty", true)} testId="decision-guilty-yes" disabled={disabled}>
            Bị cáo phạm tội
          </Choice>
          <Choice name={`${id}-guilty`} checked={values.guilty === false} onChange={() => set("guilty", false)} testId="decision-guilty-no" disabled={disabled}>
            Bị cáo không phạm tội
          </Choice>
        </div>
        {unsetLine("guilty", DECISION_UNSET_MESSAGES.guilty)}
        <FieldFindings check={check} field="guilty" />
        <FieldFindings check={check} field="dieu" />

        <div id={fieldAnchor("khoan")} className="flex flex-col gap-2">
          <p className="text-sm text-foreground">Khoản áp dụng (Điều {form.dieu} Bộ luật Hình sự)</p>
          <div role="radiogroup" aria-label="Khoản áp dụng" className="grid gap-2 sm:grid-cols-2">
            {form.khoan.map((khoan) => (
              <Choice key={khoan} name={`${id}-khoan`} checked={values.khoan === khoan} onChange={() => changeKhoan(khoan)} testId={`decision-khoan-${khoan}`} disabled={disabled}>
                <span className="font-medium">Khoản {khoan}</span>
                {khoan === form.charged_khoan ? <span className="ml-1.5 text-xs text-muted-foreground">(Viện kiểm sát truy tố)</span> : null}
                <span className="block text-xs text-muted-foreground" data-testid="decision-frame">
                  {penaltyFrameText(form.frames[khoan])}
                </span>
              </Choice>
            ))}
          </div>
          <FieldFindings check={check} field="khoan" />
        </div>

        <div id={fieldAnchor("diem")} className="flex flex-col gap-2">
          <p className="text-sm text-foreground">Điểm định khung của khoản {values.khoan}</p>
          {(form.diem[values.khoan] ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">Khoản này không có điểm định khung.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {(form.diem[values.khoan] ?? []).map((letter) => (
                <label key={letter} className="flex min-h-10 cursor-pointer items-center gap-2 rounded-full border border-border px-3 text-sm hover:bg-accent/10">
                  <input
                    type="checkbox"
                    data-testid={`decision-diem-${letter}`}
                    checked={values.diem.includes(letter)}
                    disabled={disabled}
                    onChange={(event) => set("diem", event.target.checked ? [...values.diem, letter] : values.diem.filter((d) => d !== letter))}
                    className="h-4 w-4 accent-[hsl(var(--primary))]"
                  />
                  Điểm {letter}
                  {form.charged_diem.includes(letter) ? <span className="text-xs text-muted-foreground">(truy tố)</span> : null}
                </label>
              ))}
            </div>
          )}
          <FieldFindings check={check} field="diem" />
        </div>
      </Group>

      <Group field="penalty_type" title="2. Hình phạt chính" testId="decision-group-penalty">
        <div role="radiogroup" aria-label="Loại hình phạt chính" className="grid gap-2 sm:grid-cols-2">
          {form.penalty_types.map((type) => (
            <Choice key={type} name={`${id}-penalty`} checked={values.penalty_type === type} onChange={() => changePenalty(type)} testId={`decision-penalty-${type}`} disabled={disabled}>
              {PENALTY_TYPE_LABELS[type]}
              {type === "khong" ? <span className="block text-xs text-muted-foreground">Khi tuyên bị cáo không phạm tội.</span> : null}
            </Choice>
          ))}
        </div>
        {unsetLine("penalty_type", DECISION_UNSET_MESSAGES.penalty_type)}
        <FieldFindings check={check} field="penalty_type" />

        {values.penalty_type === "tu" || values.penalty_type === "cai_tao_khong_giam_giu" ? (
          <div id={fieldAnchor("penalty_months")} className="flex flex-col gap-1.5">
            <NumberBox
              id={`${id}-months`}
              label={values.penalty_type === "tu" ? "Mức tù" : "Thời hạn cải tạo không giam giữ"}
              value={values.penalty_months}
              onChange={(value) => set("penalty_months", value)}
              unit={months !== null && months >= 12 ? `tháng (${monthsLabel(months)})` : "tháng"}
              hint={`${penaltyFrameText(frame)}`}
              testId="decision-months"
            />
            <FieldFindings check={check} field="penalty_months" />
          </div>
        ) : null}
        {values.penalty_type === "phat_tien" ? (
          <div id={fieldAnchor("fine_vnd")} className="flex flex-col gap-1.5">
            <NumberBox id={`${id}-fine`} label="Mức phạt tiền" value={values.fine_vnd} onChange={(value) => set("fine_vnd", value)} unit="đồng" testId="decision-fine" />
          </div>
        ) : null}
        <FieldFindings check={check} field="fine_vnd" />

        <div id={fieldAnchor("applies_dieu_54")} className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex min-h-10 cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                data-testid="decision-dieu54"
                checked={values.applies_dieu_54}
                disabled={disabled}
                onChange={(event) => set("applies_dieu_54", event.target.checked)}
                className="h-4 w-4 accent-[hsl(var(--primary))]"
              />
              Áp dụng Điều 54 (quyết định hình phạt dưới mức thấp nhất của khung)
            </label>
            <ArticlePill dieu="54" lawVersion={LAW_VERSION_BLHS} label="Điều 54 BLHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />
          </div>
          <FieldFindings check={check} field="applies_dieu_54" />
        </div>

        {values.penalty_type === "tu" ? (
          <div id={fieldAnchor("suspended")} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex min-h-10 cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  data-testid="decision-suspended"
                  checked={values.suspended}
                  disabled={disabled}
                  onChange={(event) => onChange({ ...values, suspended: event.target.checked, probation_months: event.target.checked ? values.probation_months : "" })}
                  className="h-4 w-4 accent-[hsl(var(--primary))]"
                />
                Cho hưởng án treo
              </label>
              <ArticlePill dieu="65" lawVersion={LAW_VERSION_BLHS} label="Điều 65 BLHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />
            </div>
            <FieldFindings check={check} field="suspended" />
            {values.suspended ? (
              <div id={fieldAnchor("probation_months")} className="flex flex-col gap-1.5">
                <NumberBox
                  id={`${id}-probation`}
                  label="Thời gian thử thách"
                  value={values.probation_months}
                  onChange={(value) => set("probation_months", value)}
                  unit="tháng"
                  testId="decision-probation"
                />
              </div>
            ) : null}
          </div>
        ) : (
          <FieldFindings check={check} field="suspended" />
        )}
        <FieldFindings check={check} field="probation_months" />
      </Group>

      <CircumstanceGroup
        field="mitigating"
        title="3. Tình tiết giảm nhẹ"
        dieu="51"
        points={form.mitigating_points}
        rows={values.mitigating}
        facts={form.facts}
        factText={factText}
        check={check}
        disabled={disabled}
        onChange={(rowsNext) => set("mitigating", rowsNext)}
      />
      <CircumstanceGroup
        field="aggravating"
        title="4. Tình tiết tăng nặng"
        dieu="52"
        points={form.aggravating_points}
        rows={values.aggravating}
        facts={form.facts}
        factText={factText}
        check={check}
        disabled={disabled}
        onChange={(rowsNext) => set("aggravating", rowsNext)}
      />

      <Group field="civil_amount_vnd" title="5. Trách nhiệm dân sự" testId="decision-group-civil">
        <NumberBox
          id={`${id}-civil`}
          label="Bị cáo bồi thường cho bị hại"
          value={values.civil_amount_vnd}
          onChange={(value) => set("civil_amount_vnd", value)}
          unit="đồng"
          hint={[
            form.civil_claim_vnd !== null ? `Bị hại yêu cầu trong hồ sơ: ${formatVnd(form.civil_claim_vnd)}.` : "Hồ sơ không có yêu cầu bồi thường.",
            form.compensation_vnd !== null ? `Đã bồi thường theo hồ sơ: ${formatVnd(form.compensation_vnd)}.` : ""
          ].filter(Boolean).join(" ") + " Để trống nếu không quyết định khoản bồi thường."}
          testId="decision-civil"
        />
        <FieldFindings check={check} field="civil_amount_vnd" />
      </Group>

      <Group
        field="exhibits"
        title="6. Xử lý vật chứng"
        testId="decision-group-exhibits"
        basis={<ArticlePill dieu="106" lawVersion={LAW_VERSION_BLTTHS} label="Điều 106 BLTTHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />}
      >
        {form.exhibits.length === 0 ? <p className="text-xs text-muted-foreground">Hồ sơ không có vật chứng.</p> : null}
        {form.exhibits.map((evidenceId) => (
          <div key={evidenceId} className="flex min-w-0 flex-col gap-1.5" data-testid={`decision-exhibit-${evidenceId}`}>
            <label htmlFor={`${id}-ex-${evidenceId}`} className="text-sm text-foreground">
              <span className="font-medium">{evidenceId}</span>
              {evidenceText(evidenceId) ? ` · ${evidenceText(evidenceId)}` : ""}
            </label>
            <select
              id={`${id}-ex-${evidenceId}`}
              data-testid="decision-disposition"
              value={values.exhibits[evidenceId] ?? ""}
              disabled={disabled}
              onChange={(event) => set("exhibits", { ...values.exhibits, [evidenceId]: event.target.value as TrialExhibitDisposition | "" })}
              className="min-h-11 w-full min-w-0 rounded-md border border-border bg-background px-2 text-sm text-foreground focus:border-ring focus:outline-none"
            >
              <option value="">Chọn cách xử lý...</option>
              {form.dispositions.map((disposition) => (
                <option key={disposition} value={disposition}>
                  {DISPOSITION_LABELS[disposition]}
                </option>
              ))}
            </select>
          </div>
        ))}
        <FieldFindings check={check} field="exhibits" />
      </Group>

      <Group
        field="defendant_pays_criminal_fee"
        title="7. Án phí"
        testId="decision-group-fees"
        basis={<ArticlePill dieu="136" lawVersion={LAW_VERSION_BLTTHS} label="Điều 136 BLTTHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />}
      >
        <Choice type="checkbox" name={`${id}-fee-criminal`} checked={values.defendant_pays_criminal_fee} onChange={(checked) => set("defendant_pays_criminal_fee", checked)} testId="decision-fee-criminal" disabled={disabled}>
          Bị cáo chịu án phí hình sự sơ thẩm
        </Choice>
        <FieldFindings check={check} field="defendant_pays_criminal_fee" />
        <div id={fieldAnchor("defendant_pays_civil_fee")}>
          <Choice type="checkbox" name={`${id}-fee-civil`} checked={values.defendant_pays_civil_fee} onChange={(checked) => set("defendant_pays_civil_fee", checked)} testId="decision-fee-civil" disabled={disabled}>
            Bị cáo chịu án phí dân sự sơ thẩm
          </Choice>
        </div>
        <FieldFindings check={check} field="defendant_pays_civil_fee" />
        <p className="text-xs text-muted-foreground">Bản mô phỏng không tính số tiền án phí; lời tuyên ghi mức án phí “theo quy định của pháp luật”.</p>
      </Group>

      <Group
        field="reasoning_summary"
        title="8. Nhận định của Chủ tọa"
        testId="decision-group-reasoning"
        basis={<ArticlePill dieu="260" lawVersion={LAW_VERSION_BLTTHS} label="Điều 260 BLTTHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />}
      >
        <label htmlFor={`${id}-reasoning`} className="text-xs text-muted-foreground">
          Lý do của quyết định: chứng cứ, tình tiết, căn cứ pháp luật. Lời tuyên án dùng nhận định này.
        </label>
        <Textarea
          id={`${id}-reasoning`}
          data-testid="decision-reasoning"
          value={values.reasoning_summary}
          disabled={disabled}
          onChange={(event) => set("reasoning_summary", event.target.value)}
          className="min-h-[160px] resize-y text-sm leading-relaxed"
        />
        <p data-testid="decision-reasoning-counter" className={cn("text-xs tabular-nums", reasoningLength > reasoningMax ? "font-medium text-red-700" : "text-muted-foreground")}>
          {reasoningLength.toLocaleString("vi-VN")}/{reasoningMax.toLocaleString("vi-VN")} ký tự · cần ít nhất {reasoningMin.toLocaleString("vi-VN")}
        </p>
        <FieldFindings check={check} field="reasoning_summary" />
      </Group>
    </div>
  );
}

function CircumstanceGroup({
  field,
  title,
  dieu,
  points,
  rows,
  facts,
  factText,
  check,
  disabled,
  onChange
}: {
  field: "mitigating" | "aggravating";
  title: string;
  dieu: string;
  points: Record<string, string[]>;
  rows: TrialDecisionCircumstance[];
  facts: string[];
  factText: (id: string) => string;
  check: TrialDecisionCheck | null;
  disabled: boolean;
  onChange: (rows: TrialDecisionCircumstance[]) => void;
}) {
  const id = useId();
  const khoans = Object.keys(points).sort((a, b) => Number(a) - Number(b));
  const update = (index: number, row: TrialDecisionCircumstance) => onChange(rows.map((current, i) => (i === index ? row : current)));
  return (
    <Group
      field={field}
      title={title}
      testId={`decision-group-${field}`}
      basis={<ArticlePill dieu={dieu} lawVersion={LAW_VERSION_BLHS} label={`Điều ${dieu} BLHS`} className="min-h-7 px-2 text-[0.7rem] font-normal" />}
    >
      <FieldFindings check={check} field={field} />
      {rows.length === 0 ? <p className="text-xs text-muted-foreground">Chưa có tình tiết nào.</p> : null}
      {rows.map((row, index) => {
        const letters = points[row.khoan] ?? [];
        return (
          <div key={index} id={fieldAnchor(`${field}[${index}]`)} data-testid={`decision-${field}-row`} className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-muted/20 p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <label className="sr-only" htmlFor={`${id}-${index}-khoan`}>
                Khoản
              </label>
              <select
                id={`${id}-${index}-khoan`}
                data-testid="decision-circumstance-khoan"
                value={row.khoan}
                disabled={disabled}
                onChange={(event) => update(index, { ...row, khoan: event.target.value, diem: "" })}
                className="min-h-10 min-w-0 rounded-md border border-border bg-background px-2 text-sm focus:border-ring focus:outline-none"
              >
                {khoans.map((khoan) => (
                  <option key={khoan} value={khoan}>
                    Khoản {khoan} Điều {dieu}
                    {(points[khoan] ?? []).length === 0 ? " (tình tiết khác)" : ""}
                  </option>
                ))}
              </select>
              {letters.length > 0 ? (
                <>
                  <label className="sr-only" htmlFor={`${id}-${index}-diem`}>
                    Điểm
                  </label>
                  <select
                    id={`${id}-${index}-diem`}
                    data-testid="decision-circumstance-diem"
                    value={row.diem}
                    disabled={disabled}
                    onChange={(event) => update(index, { ...row, diem: event.target.value })}
                    className="min-h-10 min-w-0 rounded-md border border-border bg-background px-2 text-sm focus:border-ring focus:outline-none"
                  >
                    <option value="">Chọn điểm...</option>
                    {letters.map((letter) => (
                      <option key={letter} value={letter}>
                        Điểm {letter}
                      </option>
                    ))}
                  </select>
                </>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="ml-auto h-9 rounded-full px-2.5"
                disabled={disabled}
                data-testid="decision-circumstance-remove"
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Bỏ
              </Button>
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">Sự việc trong hồ sơ (chọn ít nhất một):</p>
              {facts.map((factId) => (
                <label key={factId} className="flex min-h-9 cursor-pointer items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    data-testid={`decision-fact-${factId}`}
                    checked={row.fact_ids.includes(factId)}
                    disabled={disabled}
                    onChange={(event) =>
                      update(index, { ...row, fact_ids: event.target.checked ? [...row.fact_ids, factId] : row.fact_ids.filter((f) => f !== factId) })
                    }
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
                  />
                  <span className="min-w-0 break-words">
                    <span className="font-medium">{factId}</span>
                    {factText(factId) ? ` · ${factText(factId)}` : ""}
                  </span>
                </label>
              ))}
            </div>
            <FieldFindings check={check} field={`${field}[${index}]`} />
          </div>
        );
      })}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start rounded-full"
        disabled={disabled || khoans.length === 0}
        data-testid={`decision-add-${field}`}
        onClick={() => onChange([...rows, { khoan: khoans[0] ?? "1", diem: "", fact_ids: [] }])}
      >
        <Plus className="h-4 w-4" />
        Thêm tình tiết
      </Button>
    </Group>
  );
}

// "Kết quả kiểm tra": counts, and a jump to every finding.
function CheckSummary({ decision, dirty }: { decision: TrialDecisionState; dirty: boolean }) {
  const { check } = decision;
  if (check === null) {
    return (
      <p data-testid="decision-check-summary" className="rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
        Chưa kiểm tra. Bấm “Lưu nháp” hoặc “Kiểm tra”: hệ thống kiểm bản nháp đã lưu theo các quy định đã viện dẫn (không gọi AI).
      </p>
    );
  }
  const all = [...check.errors.map((f) => ({ f, kind: "error" as const })), ...check.warnings.map((f) => ({ f, kind: "warning" as const }))];
  return (
    <div data-testid="decision-check-summary" tabIndex={-1} className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 outline-none">
      <p className="text-sm text-foreground">
        <span className="font-medium">Kết quả kiểm tra</span>
        <span className="ml-1.5 text-xs text-muted-foreground">
          {check.errors.length > 0 ? `${check.errors.length} điểm cần sửa trước khi chốt` : "Không có điểm cần sửa"}
          {check.warnings.length > 0 ? ` · ${check.warnings.length} lưu ý (không chặn chốt)` : ""}
        </span>
      </p>
      {dirty ? (
        <p data-testid="decision-check-stale" className="text-xs text-muted-foreground">
          Đây là kết quả của bản đã lưu lúc {formatSavedTime(decision.updated_at)}; bạn đã sửa sau đó. Lưu lại để kiểm bản mới.
        </p>
      ) : null}
      {all.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {all.map(({ f, kind }, index) => (
            <li key={index}>
              <button
                type="button"
                onClick={() => jumpTo(f.field)}
                className={cn(
                  "min-h-8 rounded-full border px-2.5 text-left text-xs",
                  kind === "error" ? "border-red-200 bg-red-50 text-red-800 hover:bg-red-100" : "border-amber-200 bg-amber-50 text-amber-900 hover:bg-amber-100"
                )}
              >
                {kind === "error" ? "Cần sửa" : "Lưu ý"}: {fieldName(f.field)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

const FIELD_NAMES: Record<string, string> = {
  guilty: "tội danh", dieu: "điều luật", khoan: "khoản", diem: "điểm", penalty_type: "loại hình phạt", penalty_months: "mức hình phạt",
  fine_vnd: "mức phạt tiền", suspended: "án treo", probation_months: "thời gian thử thách", applies_dieu_54: "Điều 54",
  mitigating: "tình tiết giảm nhẹ", aggravating: "tình tiết tăng nặng", civil_amount_vnd: "bồi thường", reasoning_summary: "nhận định",
  exhibits: "vật chứng", defendant_pays_criminal_fee: "án phí hình sự", defendant_pays_civil_fee: "án phí dân sự"
};

function fieldName(field: string): string {
  const row = /^(mitigating|aggravating)\[(\d+)\]$/.exec(field);
  if (row !== null) {
    return `${FIELD_NAMES[row[1]]} thứ ${Number(row[2]) + 1}`;
  }
  return FIELD_NAMES[field] ?? field;
}

// --- Assessors (contract 5.4, Mục 9.16): only here, never in the transcript ---------------------------

export function AssessorOpinions({
  decision,
  canInvite,
  dirty,
  busy,
  onInvite
}: {
  decision: TrialDecisionState;
  canInvite: boolean;
  dirty: boolean;
  busy: boolean;
  onInvite: () => void;
}) {
  const opinions = decision.assessor_opinions;
  const clean = decision.check !== null && decision.check.errors.length === 0;
  if (opinions === null && !clean) {
    return null;
  }
  const changedSince = opinions !== null && (dirty || (decision.assessor_draft_updated_at !== null && decision.assessor_draft_updated_at !== decision.updated_at));
  return (
    <section data-testid="assessor-panel" aria-label="Ý kiến Hội thẩm" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Users className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          Ý kiến Hội thẩm nhân dân
        </h3>
        <ArticlePill dieu="326" lawVersion={LAW_VERSION_BLTTHS} label="Điều 326 BLTTHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />
      </div>
      <p data-testid="assessor-order-note" className="rounded-md bg-muted/40 px-2.5 py-2 text-xs leading-relaxed text-muted-foreground">
        {decision.assessor_order_note}
      </p>
      {opinions !== null ? (
        <>
          <ul className="flex flex-col gap-2">
            {opinions.map((opinion) => (
              <li key={opinion.speaker_id} data-testid="assessor-opinion" className="flex flex-col gap-1 rounded-lg border border-border px-3 py-2">
                <p className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium text-foreground">Hội thẩm {opinion.speaker_name}</span>
                  <span className={cn("rounded-full px-2 py-px text-[0.7rem] font-medium", opinion.agrees ? "bg-primary/10 text-primary" : "bg-muted text-foreground")}>
                    {opinion.agrees ? "Đồng ý với bản nháp" : "Ý kiến khác"}
                  </span>
                </p>
                <TrialText text={opinion.text} density="compact" className="text-sm text-foreground/90" />
              </li>
            ))}
          </ul>
          <p data-testid="assessor-based-on" className="text-xs text-muted-foreground">
            Ý kiến dựa trên bản nháp lưu lúc {formatSavedTime(decision.assessor_draft_updated_at)}.
            {changedSince ? " Bản nháp đã thay đổi sau đó; ý kiến không được lấy lại." : ""}
          </p>
        </>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 flex-1 text-xs text-muted-foreground">
            Tùy chọn. Hai Hội thẩm góp ý trên bản nháp đã lưu (một lần); sửa bản nháp sau đó không lấy lại ý kiến.
            {dirty ? " Lưu bản nháp trước khi nghe ý kiến." : ""}
          </p>
          {canInvite ? (
            <Button type="button" variant="outline" size="sm" className="rounded-full" disabled={busy || dirty} data-testid="assessor-invite" onClick={onInvite}>
              <Users className="h-4 w-4" />
              Nghe ý kiến Hội thẩm
            </Button>
          ) : null}
        </div>
      )}
    </section>
  );
}

// --- The locked decision, read only -------------------------------------------------------------------------

export function DecisionSummary({ draft, caseFile }: { draft: TrialDecisionDraft; caseFile: TrialCaseFile }) {
  const evidenceText = (evidenceId: string) => caseFile.evidence?.find((item) => item.id === evidenceId)?.description ?? "";
  const circumstances = (rows: TrialDecisionCircumstance[], dieu: string) =>
    rows.length === 0 ? "Không có." : rows.map((row) => `${row.diem ? `điểm ${row.diem} ` : ""}khoản ${row.khoan} Điều ${dieu} (${row.fact_ids.join(", ")})`).join("; ");
  const penalty = draft.penalty_type === "khong"
    ? "Không có hình phạt."
    : draft.penalty_type === "phat_tien"
      ? `Phạt tiền ${draft.fine_vnd !== null ? formatVnd(draft.fine_vnd) : "......"}.`
      : `${PENALTY_TYPE_LABELS[draft.penalty_type]} ${draft.penalty_months !== null ? monthsLabel(draft.penalty_months) : "......"}${draft.suspended ? `, cho hưởng án treo, thử thách ${draft.probation_months !== null ? monthsLabel(draft.probation_months) : "......"}` : ""}.`;
  const rows: [string, string][] = [
    ["Tội danh", draft.guilty ? `Bị cáo phạm tội; ${draft.diem.length ? `điểm ${lettersLabel(draft.diem)} ` : ""}khoản ${draft.khoan} Điều ${draft.dieu} Bộ luật Hình sự.` : "Bị cáo không phạm tội."],
    ["Hình phạt chính", `${penalty}${draft.applies_dieu_54 ? " Áp dụng Điều 54 Bộ luật Hình sự." : ""}`],
    ["Tình tiết giảm nhẹ", circumstances(draft.mitigating, "51")],
    ["Tình tiết tăng nặng", circumstances(draft.aggravating, "52")],
    ["Bồi thường", draft.civil_amount_vnd ? formatVnd(draft.civil_amount_vnd) : "Không quyết định khoản bồi thường."],
    ["Vật chứng", draft.exhibits.length ? draft.exhibits.map((x) => `${x.evidence_id}${evidenceText(x.evidence_id) ? ` (${evidenceText(x.evidence_id)})` : ""}: ${DISPOSITION_LABELS[x.disposition].toLowerCase()}`).join("; ") : "Không có."],
    ["Án phí", `Hình sự sơ thẩm: ${draft.defendant_pays_criminal_fee ? "bị cáo chịu" : "bị cáo không chịu"}; dân sự sơ thẩm: ${draft.defendant_pays_civil_fee ? "bị cáo chịu" : "bị cáo không chịu"}.`]
  ];
  return (
    <div data-testid="decision-locked" className="flex flex-col gap-3 rounded-xl border border-primary/15 bg-card p-3 sm:p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Lock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        Quyết định của bạn (đã chốt)
      </h3>
      <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-xs font-medium text-muted-foreground sm:pt-0.5">{label}</dt>
            <dd className="min-w-0 break-words text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      <details className="text-sm">
        <summary className="min-h-9 cursor-pointer text-xs font-medium text-primary">Nhận định của bạn</summary>
        <p className="mt-1 whitespace-pre-wrap break-words text-foreground/90">{draft.reasoning_summary}</p>
      </details>
    </div>
  );
}

// --- Step 11: the judgment, written by the system from the locked decision, read only ------------------------

export function PronouncementPanel({ decision, caseFile, completed }: { decision: TrialDecisionState; caseFile: TrialCaseFile; completed: boolean }) {
  const preview = decision.pronouncement_preview;
  return (
    <div className="flex flex-col gap-4">
      {decision.draft !== null ? <DecisionSummary draft={decision.draft} caseFile={caseFile} /> : null}
      <section data-testid="pronouncement-panel" aria-label="Lời tuyên án" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <ScrollText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            Lời tuyên án
          </h3>
          <ArticlePill dieu="327" lawVersion={LAW_VERSION_BLTTHS} label="Điều 327 BLTTHS" className="min-h-7 px-2 text-[0.7rem] font-normal" />
        </div>
        {preview === null ? (
          <p data-testid="pronouncement-empty" className="text-sm text-muted-foreground">
            Bấm “Soạn lời tuyên”: hệ thống soạn lời tuyên án từ quyết định bạn đã chốt (một lời gọi AI). Bạn đọc trước rồi bấm “Tuyên án”. Ở phiên bản này lời tuyên không sửa được.
          </p>
        ) : (
          <>
            <p data-testid="pronouncement-source" className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Info className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {completed ? "Đã tuyên. " : "Xem trước. "}Nguồn: hệ thống soạn từ quyết định của bạn; không sửa được ở phiên bản này.
            </p>
            <div data-testid="pronouncement-preview" className="max-h-[60vh] overflow-y-auto rounded-lg border border-border bg-background px-3 py-3 text-sm">
              <TrialText text={preview} />
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// --- The dock (sticky): what the student does next in the room -------------------------------------------------

// The wait before the server's first status line, by action.
const RUNNING_LABELS: Record<string, string> = {
  invite: "Hội thẩm đang góp ý trên bản nháp...",
  decide: "Đang chốt quyết định...",
  advance: "Đang chuyển sang phần tuyên án...",
  prepare_pronouncement: "Đang soạn lời tuyên án...",
  pronounce: "Đang tuyên án..."
};

interface DeliberationDockProps {
  step: number;
  decision: TrialDecisionState;
  allowedActions: readonly string[];
  busy: boolean;
  statusMessage: string | null;
  runningAction: string | null;
  saving: boolean;
  dirty: boolean;
  canDecide: boolean;
  slowNotice: string | null;
  onSave: () => void;
  onCheck: () => void;
  onDecide: () => void;
  onAdvance: (step: number) => void;
  onPrepare: () => void;
  onPronounce: () => void;
  onCancel: () => void;
}

export function DeliberationDock(props: DeliberationDockProps) {
  const { step, decision, allowedActions, busy, statusMessage, saving, dirty, slowNotice, onCancel } = props;
  const elapsed = useElapsedSeconds(busy);
  if (busy) {
    return (
      <div role="status" aria-live="polite" data-testid="deliberation-busy" className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-border bg-card px-4 py-3 text-sm">
        <span className="flex gap-1" aria-hidden="true">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
        </span>
        <span className="min-w-0 flex-1 text-foreground">{statusMessage ?? RUNNING_LABELS[props.runningAction ?? ""] ?? "Đang xử lý..."}</span>
        <span className="text-xs tabular-nums text-muted-foreground">{elapsed}s</span>
        <Button type="button" variant="outline" size="sm" className="h-9 rounded-full" onClick={onCancel} data-testid="deliberation-cancel">
          <X className="h-4 w-4" />
          Hủy chờ
        </Button>
        {slowNotice ? <p className="w-full text-xs text-muted-foreground">{slowNotice}</p> : null}
      </div>
    );
  }

  const advanceTo = allowedActions.map((a) => /^advance:(\d+)$/.exec(a)).find((m) => m !== null);
  if (step === 10 && decision.locked) {
    return (
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">Đã chốt quyết định. Tiếp theo: Tuyên án.</p>
        {advanceTo ? (
          <Button type="button" className="rounded-full" data-testid="trial-advance" data-ready="true" onClick={() => props.onAdvance(Number(advanceTo[1]))}>
            Sang bước tiếp theo
            <ArrowRight className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
    );
  }

  if (step >= 11) {
    const canPrepare = allowedActions.includes("prepare_pronouncement");
    const canPronounce = allowedActions.includes("pronounce");
    return (
      <div data-testid="pronounce-dock" className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">
          {canPronounce ? "Đọc lời tuyên ở trên rồi bấm “Tuyên án”." : "Hệ thống soạn lời tuyên từ quyết định bạn đã chốt."}
        </p>
        {canPrepare ? (
          <Button type="button" className="rounded-full" data-testid="pronounce-prepare" onClick={props.onPrepare}>
            <ScrollText className="h-4 w-4" />
            Soạn lời tuyên
          </Button>
        ) : null}
        {canPronounce ? (
          <Button type="button" className="rounded-full" data-testid="pronounce-send" onClick={props.onPronounce}>
            <Gavel className="h-4 w-4" />
            Tuyên án
          </Button>
        ) : null}
      </div>
    );
  }

  const blockedReason = dirty
    ? "Có thay đổi chưa lưu: lưu để kiểm tra trước khi chốt."
    : decision.check === null
      ? "Lưu bản nháp để hệ thống kiểm tra trước khi chốt."
      : decision.check.errors.length > 0
        ? `Còn ${decision.check.errors.length} điểm cần sửa trước khi chốt.`
        : props.canDecide
          ? decision.check.warnings.length > 0
            ? "Không có điểm cần sửa; các lưu ý không chặn chốt."
            : "Không có điểm cần sửa."
          : "";
  return (
    <div data-testid="decision-dock" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p data-testid="decision-save-state" data-dirty={dirty || undefined} className={cn("text-xs", dirty ? "font-medium text-foreground" : "text-muted-foreground")}>
          {saving ? "Đang lưu..." : dirty ? "● Có thay đổi chưa lưu" : decision.updated_at ? `Đã lưu lúc ${formatSavedTime(decision.updated_at)}` : "Chưa lưu bản nháp"}
        </p>
        <p data-testid="decision-decide-hint" className="min-w-0 flex-1 text-right text-xs text-muted-foreground [@media(max-height:640px)]:sr-only">
          {blockedReason}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" variant="outline" size="sm" className="h-10 rounded-full" disabled={saving} data-testid="decision-save" onClick={props.onSave}>
          <Save className="h-4 w-4" />
          Lưu nháp
        </Button>
        <Button type="button" variant="outline" size="sm" className="h-10 rounded-full" disabled={saving} data-testid="decision-check" onClick={props.onCheck}>
          <ClipboardCheck className="h-4 w-4" />
          Kiểm tra
        </Button>
        <Button type="button" size="sm" className="h-10 rounded-full" disabled={saving || !props.canDecide} data-testid="decision-decide" onClick={props.onDecide}>
          <CheckCircle2 className="h-4 w-4" />
          Chốt quyết định
        </Button>
      </div>
    </div>
  );
}

function useElapsedSeconds(running: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    setElapsed(0);
    if (!running) {
      return;
    }
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return elapsed;
}
