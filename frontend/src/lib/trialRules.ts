// Pure rules for "Phiên tòa giả định" (docs/phien-toa-gia-dinh/API-CONTRACT.md). No React, no
// fetch and no "@/" imports, so tests/trialRules.test.mjs can load this file directly with Node.
// Everything that decides WHAT the student may do comes from state.allowed_actions; the helpers
// here only translate that list into UI pieces and pre-check text the server would reject anyway.

import type { TrialClerkDraft, TrialClerkSection, TrialConfig, TrialRecordDocument, TrialRecordSection, TrialState, TrialUtterance } from "./types";

// --- Text limits --------------------------------------------------------------------------------
// The server sends the limits of the current slot in state.text_limits (contract Mục 3.4/5); that is
// the only source. The per-step table below is kept solely as a fallback for a backend that does
// not send the field yet - it mirrors trial_state_machine.text_limits at the time of writing.
export const TRIAL_TEXT_SCHEMA_MAX = 6000;
export const TRIAL_TEXT_DEFAULT_MAX = 1500;

export interface TrialTextLimits {
  min: number;
  max: number;
  // Shown under the composer: what this text is.
  label: string;
}

const STEP_TEXT_LABELS: Record<number, string> = {
  1: "Báo cáo",
  3: "Cáo trạng",
  5: "Câu hỏi",
  6: "Bản luận tội",
  7: "Bài bào chữa",
  8: "Ý kiến đối đáp"
};

function textLabelForStep(step: number): string {
  return STEP_TEXT_LABELS[step] ?? "Ý kiến";
}

// Fallback only - see textLimitsForState.
export function textLimitsForStep(step: number): TrialTextLimits {
  const label = textLabelForStep(step);
  switch (step) {
    case 3:
      return { min: 100, max: TRIAL_TEXT_SCHEMA_MAX, label };
    case 6:
    case 7:
      return { min: 300, max: TRIAL_TEXT_SCHEMA_MAX, label };
    case 8:
      return { min: 1, max: TRIAL_TEXT_SCHEMA_MAX, label };
    default:
      return { min: 1, max: TRIAL_TEXT_DEFAULT_MAX, label };
  }
}

function isValidServerLimits(limits: unknown): limits is { min: number; max: number } {
  if (limits === null || typeof limits !== "object") {
    return false;
  }
  const { min, max } = limits as { min?: unknown; max?: unknown };
  return Number.isInteger(min) && Number.isInteger(max) && (min as number) >= 1 && (max as number) >= (min as number);
}

// Limits for the composer: the server's text_limits when present and well-formed, otherwise the
// per-step fallback. The label (wording only) always comes from the step.
export function textLimitsForState(state: Pick<TrialState, "current_step" | "text_limits">): TrialTextLimits {
  if (isValidServerLimits(state.text_limits)) {
    return { min: state.text_limits.min, max: state.text_limits.max, label: textLabelForStep(state.current_step) };
  }
  return textLimitsForStep(state.current_step);
}

// Returns the Vietnamese reason the text cannot be sent yet, or null when it can. Length is counted
// on the trimmed text for the minimum (the server strips before comparing) and on the raw text for
// the maximum (the server measures the raw body).
export function validateTrialText(text: string, limits: TrialTextLimits): string | null {
  const trimmedLength = text.trim().length;
  if (trimmedLength === 0) {
    return "Bạn chưa nhập nội dung.";
  }
  if (text.length > limits.max) {
    return `${limits.label} dài quá ${limits.max.toLocaleString("vi-VN")} ký tự. Bạn rút gọn bớt nhé.`;
  }
  if (trimmedLength < limits.min) {
    return `${limits.label} cần ít nhất ${limits.min.toLocaleString("vi-VN")} ký tự (hiện có ${trimmedLength.toLocaleString("vi-VN")}).`;
  }
  return null;
}

// --- allowed_actions ------------------------------------------------------------------------------

export interface ParsedActions {
  canSpeak: boolean;
  // Non-null only for "speak:ID1|ID2": the student must pick one of these as addressee.
  addressees: string[] | null;
  canEndSlot: boolean;
  advanceTo: number | null;
  canContinue: boolean;
}

export function parseAllowedActions(actions: readonly string[]): ParsedActions {
  const parsed: ParsedActions = { canSpeak: false, addressees: null, canEndSlot: false, advanceTo: null, canContinue: false };
  for (const action of actions) {
    if (action === "speak") {
      parsed.canSpeak = true;
    } else if (action.startsWith("speak:")) {
      parsed.canSpeak = true;
      parsed.addressees = action.slice("speak:".length).split("|").filter((id) => id.length > 0);
    } else if (action === "end_slot") {
      parsed.canEndSlot = true;
    } else if (action.startsWith("advance:")) {
      const target = Number(action.slice("advance:".length));
      parsed.advanceTo = Number.isInteger(target) ? target : null;
    } else if (action === "continue") {
      parsed.canContinue = true;
    }
  }
  return parsed;
}

// What the composer area shows. Derived from the server state only.
//  - "speak": the student's turn (input and/or end-slot button)
//  - "advance": the current step is done, only "Sang bước tiếp theo"
//  - "paused": the AI owes a turn (guard pause, lost connection, reload) - only "Tiếp tục"
//  - "exhausted": guard fuse tripped (awaiting ai, no actions) - only abandon/delete
//  - "waiting": awaiting user/ai with nothing actionable (should not happen; shown as locked)
//  - "finished": completed or abandoned
export type ComposerMode = "speak" | "advance" | "paused" | "exhausted" | "waiting" | "finished";

export function composerMode(state: TrialState): ComposerMode {
  if (state.status !== "active" || state.awaiting === "none") {
    return "finished";
  }
  const parsed = parseAllowedActions(state.allowed_actions);
  if (state.awaiting === "ai") {
    if (parsed.canContinue) {
      return "paused";
    }
    return state.allowed_actions.length === 0 ? "exhausted" : "waiting";
  }
  if (parsed.canSpeak || parsed.canEndSlot) {
    return "speak";
  }
  if (parsed.advanceTo !== null) {
    return "advance";
  }
  return "waiting";
}

export function endSlotLabel(step: number): string {
  if (step === 2) {
    return "Không có ý kiến";
  }
  if (step === 5) {
    return "Kết thúc phần hỏi của tôi";
  }
  if (step === 8) {
    return "Kết thúc đối đáp";
  }
  return "Kết thúc phần của tôi";
}

// The observer role (contract 5.1) has no speaking turn at all: the AI plays every role and the
// student only moves the hearing on.
export const OBSERVER_ROLE = "nguoi_xem";

export function isObserverRole(role: string): boolean {
  return role === OBSERVER_ROLE;
}

// The clerk role (contract 5.2) speaks once, the step-1 report; from step 2 the AI plays every
// other role and the student takes notes, then writes IV.2 and IV.3 of the record.
export const CLERK_ROLE = "thu_ky";

export function isClerkRole(role: string): boolean {
  return role === CLERK_ROLE;
}

// Roles with no speaking turn in the current state: the composer area is the observer's (advance,
// continue, progress) rather than an input.
export function usesObserverControls(role: string, mode: ComposerMode): boolean {
  return isObserverRole(role) || (isClerkRole(role) && mode !== "speak");
}

// One line telling the student what this step expects of them. Purely explanatory: it never
// decides which buttons exist.
export function stepHint(step: number, role: string, isUserTurn: boolean): string {
  if (isObserverRole(role)) {
    return observerStepHint(step);
  }
  if (isClerkRole(role)) {
    return step === 1 && isUserTurn
      ? "Báo cáo Hội đồng xét xử sự có mặt của những người được triệu tập. Lời mẫu đã điền sẵn: đối chiếu với danh sách rồi sửa nếu cần."
      : observerStepHint(step);
  }
  const isKsv = role === "ksv";
  switch (step) {
    case 1:
      return "Thư ký báo cáo sự có mặt của những người được triệu tập.";
    case 2:
      return isUserTurn
        ? "Chủ tọa hỏi ý kiến về việc thay đổi người tiến hành tố tụng. Bạn có thể nêu ý kiến hoặc bấm “Không có ý kiến”."
        : "Chủ tọa khai mạc phiên tòa, kiểm tra căn cước và giải thích quyền, nghĩa vụ.";
    case 3:
      return isKsv
        ? "Công bố bản cáo trạng (ít nhất 100 ký tự). Có thể điền sẵn cáo trạng trong hồ sơ rồi chỉnh trước khi gửi."
        : "Kiểm sát viên công bố bản cáo trạng.";
    case 4:
      return "Hội đồng xét xử xét hỏi bị cáo và những người tham gia tố tụng.";
    case 5:
      return isUserTurn
        ? "Chọn người được hỏi rồi đặt từng câu hỏi (tối đa 8 câu). Hỏi xong, bấm “Kết thúc phần hỏi của tôi”."
        : isKsv
          ? "Luật sư bào chữa đang xét hỏi."
          : "Kiểm sát viên xét hỏi trước, sau đó đến lượt bạn.";
    case 6:
      return isKsv
        ? "Trình bày bản luận tội (ít nhất 300 ký tự): đánh giá chứng cứ, tội danh, điều khoản, tình tiết tăng nặng, giảm nhẹ và đề nghị hướng xử lý."
        : "Kiểm sát viên trình bày bản luận tội.";
    case 7:
      return isKsv
        ? "Luật sư trình bày bài bào chữa cho bị cáo."
        : "Trình bày bài bào chữa (ít nhất 300 ký tự): phản bác hoặc làm rõ chứng cứ, tình tiết giảm nhẹ và đề nghị của bạn.";
    case 8:
      return isKsv
        ? "Đối đáp với ý kiến của luật sư (1–3 vòng). Hết ý kiến thì bấm “Kết thúc đối đáp”."
        : "Kiểm sát viên đối đáp trước, bạn đáp lại (1–3 vòng). Hết ý kiến thì bấm “Kết thúc đối đáp”.";
    case 9:
      return "Bị cáo nói lời sau cùng.";
    case 10:
      return "Hội đồng xét xử vào phòng nghị án.";
    case 11:
      return "Chủ tọa tuyên đọc bản án mô phỏng.";
    default:
      return "";
  }
}

function observerStepHint(step: number): string {
  switch (step) {
    case 3:
      return "Kiểm sát viên công bố bản cáo trạng.";
    case 5:
      return "Kiểm sát viên xét hỏi trước, sau đó đến luật sư bào chữa.";
    case 6:
      return "Kiểm sát viên trình bày bản luận tội.";
    case 7:
      return "Luật sư trình bày bài bào chữa cho bị cáo.";
    case 8:
      return "Kiểm sát viên đối đáp, luật sư đáp lại.";
    default:
      return stepHint(step, "", false);
  }
}

// --- Utterances -----------------------------------------------------------------------------------

// Adds streamed utterances to the transcript: an event whose seq is already present is ignored
// (contract Mục 4), and the result stays ordered by seq.
export function mergeUtterances(current: readonly TrialUtterance[], incoming: readonly TrialUtterance[]): TrialUtterance[] {
  const seen = new Set(current.map((u) => u.seq));
  const added = incoming.filter((u) => {
    if (seen.has(u.seq)) {
      return false;
    }
    seen.add(u.seq);
    return true;
  });
  if (added.length === 0) {
    return current as TrialUtterance[];
  }
  return [...current, ...added].sort((a, b) => a.seq - b.seq);
}

// --- Errors ---------------------------------------------------------------------------------------

export interface ParsedTrialError {
  status: number;
  code: string | null;
  // True only for the feature-flag 404 ({"detail": "Not Found"}, no app error envelope). A 404
  // "Trial not found" (missing or someone else's session) is NOT this.
  featureDisabled: boolean;
  state: TrialState | null;
  // error.message of the envelope. Shown verbatim only for the codes whose message the contract
  // says is student-facing (see messageForTrialError).
  serverMessage: string | null;
}

export function parseTrialErrorBody(status: number, bodyText: string): ParsedTrialError {
  let body: unknown = null;
  try {
    body = bodyText.length > 0 ? JSON.parse(bodyText) : null;
  } catch {
    body = null;
  }
  const record = (body !== null && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const envelope = record.error as { code?: unknown; message?: unknown } | undefined;
  const code = envelope !== undefined && typeof envelope.code === "string" ? envelope.code : null;
  const serverMessage = envelope !== undefined && typeof envelope.message === "string" && envelope.message.trim().length > 0
    ? envelope.message
    : null;
  const state = record.state !== undefined && record.state !== null && typeof record.state === "object"
    ? (record.state as TrialState)
    : null;
  const featureDisabled = status === 404 && envelope === undefined && record.detail === "Not Found";
  return { status, code, featureDisabled, state, serverMessage };
}

// Fallbacks for the two case-creation refusals whose server message is shown verbatim.
export const GLOBAL_DAILY_LIMIT_MESSAGE =
  "Hôm nay hệ thống đã tạo đủ số vụ án mô phỏng cho phép. Bạn vui lòng quay lại vào ngày mai; các phiên tòa đang dở vẫn tiếp tục được.";
export const USAGE_LOG_UNAVAILABLE_MESSAGE =
  "Tạm thời chưa tạo được vụ án mới vì hệ thống không kiểm tra được hạn mức. Bạn vui lòng thử lại sau; các phiên tòa đang dở vẫn tiếp tục được.";

// Vietnamese, student-facing. Never includes anything the student typed.
export function messageForTrialError(error: Pick<ParsedTrialError, "status" | "code"> & { serverMessage?: string | null }): string {
  switch (error.code) {
    case "trial_daily_case_limit":
      return "Hôm nay bạn đã tạo đủ số vụ án cho phép. Bạn quay lại vào ngày mai nhé.";
    // Contract Mục 2: these two messages are written for the student and shown as sent.
    case "trial_global_daily_limit":
      return error.serverMessage ?? GLOBAL_DAILY_LIMIT_MESSAGE;
    case "trial_usage_log_unavailable":
      return error.serverMessage ?? USAGE_LOG_UNAVAILABLE_MESSAGE;
    case "trial_active_session_limit":
      return "Bạn đang có đủ số phiên tòa dở dang cho phép. Hãy hoàn thành, bỏ hoặc xóa bớt một phiên trước khi tạo phiên mới.";
    case "rate_limit_exceeded":
      return "Bạn thao tác hơi nhanh. Đợi khoảng một phút rồi thử lại nhé.";
    case "trial_version_mismatch":
    case "trial_step_mismatch":
    case "trial_not_your_turn":
    case "trial_not_ai_turn":
    case "trial_action_not_allowed":
    case "trial_turn_limit":
    case "trial_skip_not_allowed":
      return "Phiên tòa vừa thay đổi trạng thái (có thể do bạn bấm hai lần hoặc mở ở cửa sổ khác). Đã tải lại diễn biến mới nhất.";
    case "trial_busy":
      return "Phiên tòa đang được xử lý ở một cửa sổ khác. Đợi vài giây rồi thử lại.";
    case "trial_slot_not_finished":
      return "Phần này chưa thể kết thúc: bạn cần thực hiện ít nhất một lượt trước.";
    case "trial_missing_addressee":
      return "Bạn chọn người được hỏi trước khi gửi câu hỏi nhé.";
    case "trial_empty_text":
      return "Bạn chưa nhập nội dung.";
    case "trial_text_too_short":
      return "Nội dung còn ngắn hơn mức tối thiểu của phần này.";
    case "trial_text_too_long":
      return "Nội dung dài quá mức cho phép của phần này. Bạn rút gọn bớt nhé.";
    case "trial_not_active":
      return "Phiên tòa này đã kết thúc hoặc đã bị bỏ, chỉ còn xem lại được.";
    case "trial_not_completed":
      return "Biên bản chỉ có khi phiên tòa đã hoàn thành.";
    case "trial_guard_exhausted":
      return GUARD_EXHAUSTED_MESSAGE;
    case "trial_not_clerk":
      return "Phiên tòa này không phải vai Thư ký nên không có ghi chép hay phần biên bản để soạn.";
    case "trial_record_finalized":
      return "Biên bản đã được chốt nên không sửa được nữa. Đã chuyển sang chế độ xem.";
    case "trial_record_section_empty":
      return "Chưa chốt được: mục 2 hoặc mục 3 của phần IV còn trống. Bạn viết đủ hai mục rồi chốt lại nhé.";
    case "data_unavailable":
      return "Máy chủ dữ liệu đang tạm gián đoạn. Bạn thử lại sau ít phút nhé.";
    default:
      break;
  }
  if (error.status === 401) {
    return "Phiên đăng nhập đã hết hạn. Bạn tải lại trang và đăng nhập lại nhé.";
  }
  if (error.status === 404) {
    return "Không tìm thấy phiên tòa này. Có thể phiên đã bị xóa.";
  }
  if (error.status === 422) {
    return "Dữ liệu gửi lên không hợp lệ (có thể nội dung quá dài). Bạn kiểm tra lại nhé.";
  }
  if (error.status === 429) {
    return "Bạn thao tác hơi nhanh. Đợi khoảng một phút rồi thử lại nhé.";
  }
  return "Đã có lỗi xảy ra. Bạn thử lại sau ít phút nhé.";
}

// --- Case creation limits (contract 3.1) ----------------------------------------------------------

// Contract 3.1: the wording when the usage log cannot be read. Never "đã tạo đủ 5 vụ".
export const USAGE_UNAVAILABLE_NOTICE = "Tạm thời chưa tạo được vụ án mới, bạn vui lòng thử lại sau.";

// False only when the server says so; an older backend without the field counts as available.
export function isUsageAvailable(config: Pick<TrialConfig, "remaining">): boolean {
  return config.remaining.usage_available !== false;
}

// Why creating a new case is locked, or null when it is not.
export function caseCreationBlockedReason(config: Pick<TrialConfig, "remaining" | "limits">): string | null {
  if (!isUsageAvailable(config)) {
    return USAGE_UNAVAILABLE_NOTICE;
  }
  if (config.remaining.cases_today <= 0) {
    return `Hôm nay bạn đã tạo đủ ${config.limits.max_cases_per_day} vụ án. Bạn quay lại vào ngày mai nhé.`;
  }
  if (config.remaining.active_sessions <= 0) {
    return `Bạn đang có ${config.limits.max_active_sessions} phiên dở dang. Hãy hoàn thành, bỏ hoặc xóa bớt một phiên để tạo phiên mới.`;
  }
  return null;
}

// Refusals to create a case that are limits, not failures: shown as a calm notice, not an error box.
// The global cap and the fail-closed usage log are about the whole system, not this student.
export function isCaseLimitCode(code: string | null): boolean {
  return code === "trial_daily_case_limit" || code === "trial_active_session_limit"
    || code === "trial_global_daily_limit" || code === "trial_usage_log_unavailable";
}

// 409 codes after which the client just re-syncs (contract Mục 6): soft, not an error box.
export function isResyncConflict(code: string | null): boolean {
  return code === "trial_version_mismatch" || code === "trial_step_mismatch" || code === "trial_not_your_turn"
    || code === "trial_not_ai_turn" || code === "trial_action_not_allowed" || code === "trial_turn_limit"
    || code === "trial_skip_not_allowed" || code === "trial_not_active" || code === "trial_busy";
}

export const GUARD_EXHAUSTED_MESSAGE =
  "Phiên tòa không thể tiếp tục ở bước này. Bạn có thể bỏ phiên hoặc xóa phiên rồi tạo vụ án mới.";

// --- Formatting -------------------------------------------------------------------------------------

export function formatVnd(amount: number): string {
  return `${amount.toLocaleString("vi-VN")} đồng`;
}

export const TRIAL_ROLE_LABELS: Record<string, string> = {
  ksv: "Kiểm sát viên",
  luat_su: "Luật sư bào chữa",
  nguoi_xem: "Người xem",
  thu_ky: "Thư ký phiên tòa"
};

export const TRIAL_STATUS_LABELS: Record<string, string> = {
  active: "Đang diễn ra",
  completed: "Hoàn thành",
  abandoned: "Đã bỏ"
};

export const TRIAL_TOTAL_STEPS = 11;

// Role label for a participant id, for the case-file panel (which must not read `participants`).
export function roleLabelForId(id: string): string {
  if (id.startsWith("NLC_")) {
    return "Người làm chứng";
  }
  const labels: Record<string, string> = {
    BI_CAO: "Bị cáo",
    BI_HAI: "Bị hại",
    NLQ: "Người có quyền lợi, nghĩa vụ liên quan",
    CHU_TOA: "Chủ tọa",
    HOI_THAM_1: "Hội thẩm",
    HOI_THAM_2: "Hội thẩm",
    THU_KY: "Thư ký",
    KSV: "Kiểm sát viên",
    LUAT_SU: "Luật sư bào chữa"
  };
  return labels[id] ?? "";
}

// law_version values of the corpus (ingestion/document_registry.py), used by the "Điều N" pills to
// open the existing ArticleModal. Step legal_basis numbers are BLTTHS; charge, Điều 51/52 are BLHS.
export const LAW_VERSION_BLTTHS = "BLTTHS 2015 (số 101/2015/QH13, sửa đổi bổ sung 2021)";
export const LAW_VERSION_BLHS = "BLHS - Văn bản hợp nhất năm 2025";

// --- Clerk: notes and record draft (contract 3.8-3.10) -------------------------------------------------

export const CLERK_NOTES_DEFAULT_MAX = 20000;
// Fallback for a draft response without `limits`; the server's values win.
export const CLERK_SECTION_DEFAULT_LIMITS = { min: 200, max: 4000, hard_max: 6000 };
export const CLERK_SECTIONS: readonly TrialClerkSection[] = ["iv2", "iv3"];
export const CLERK_SECTION_TITLES: Record<TrialClerkSection, string> = {
  iv2: "2. Hỏi và trả lời tại phiên tòa",
  iv3: "3. Tranh luận tại phiên tòa"
};
// The transcript steps each section reports on (contract 3.7: IV.2 = steps 4-5, IV.3 = steps 6-8).
export const CLERK_SECTION_STEPS: Record<TrialClerkSection, readonly number[]> = { iv2: [4, 5], iv3: [6, 7, 8] };

// "ok" inside the suggested range; "short"/"long" outside it (a "Lưu ý", saving still works);
// "over" above the hard cap (the server answers 422, so saving is blocked); "empty" no text.
export type ClerkLengthStatus = "empty" | "short" | "ok" | "long" | "over";

export function clerkSectionLength(text: string, limits: { min: number; max: number; hard_max: number }): ClerkLengthStatus {
  if (text.length > limits.hard_max) {
    return "over";
  }
  const trimmed = text.trim().length;
  if (trimmed === 0) {
    return "empty";
  }
  if (trimmed < limits.min) {
    return "short";
  }
  return trimmed > limits.max ? "long" : "ok";
}

// "Chốt biên bản" needs both sections written and within the hard cap; notices never block it.
export function canFinalizeClerkDraft(draft: Record<TrialClerkSection, string>, limits: { hard_max: number }): boolean {
  return CLERK_SECTIONS.every((key) => draft[key].trim().length > 0 && draft[key].length <= limits.hard_max);
}

// One plain sentence per notice code, shown under the server's own message: what the student can
// do about it. Feedback only; nothing here is a score.
const CLERK_NOTICE_HINTS: Record<string, string> = {
  empty: "Mục này cần có nội dung trước khi chốt biên bản.",
  too_short: "Mục này hơi ngắn so với gợi ý; bạn có thể ghi thêm ý chính của từng người.",
  too_long: "Mục này dài hơn gợi ý; biên bản chỉ cần ghi tóm tắt ý chính.",
  unknown_amount: "Kiểm tra lại số tiền: biên bản chỉ ghi con số đã được nêu tại phiên tòa.",
  unknown_percent: "Kiểm tra lại tỷ lệ: biên bản chỉ ghi con số đã được nêu tại phiên tòa.",
  citation_missing_law: "Khi viện dẫn Điều luật, ghi rõ là Bộ luật Hình sự hay Bộ luật Tố tụng hình sự.",
  citation_not_in_section: "Điều luật này không ai viện dẫn trong phần tương ứng; kiểm tra lại số Điều.",
  unknown_name: "Nếu bạn viết tắt hoặc gõ khác tên, hãy ghi tên đầy đủ như trong diễn biến phiên tòa."
};

export function clerkNoticeHint(code: string): string | null {
  return CLERK_NOTICE_HINTS[code] ?? null;
}

// The record subsection the clerk writes (content "user"), found by its place in part IV.
export function clerkSubsection(record: TrialRecordDocument, key: TrialClerkSection): TrialRecordSection | null {
  const partIv = record.sections.find((section) => section.heading.startsWith("IV."));
  const wanted = key === "iv2" ? "2." : "3.";
  return partIv?.subsections?.find((sub) => sub.heading.startsWith(wanted)) ?? null;
}

// The draft preview: the record with the clerk's saved text in IV.2 and IV.3, so "Xem" shows what
// was last saved without another request. Returns a new object; the input is not changed.
export function applyClerkDraft(record: TrialRecordDocument, draft: Pick<TrialClerkDraft, "iv2" | "iv3">): TrialRecordDocument {
  const fill = (sub: TrialRecordSection): TrialRecordSection => {
    if (sub.content !== "user") {
      return sub;
    }
    const key: TrialClerkSection | null = sub.heading.startsWith("2.") ? "iv2" : sub.heading.startsWith("3.") ? "iv3" : null;
    if (key === null) {
      return sub;
    }
    return { ...sub, summary: draft[key].length > 0 ? draft[key] : null };
  };
  return {
    ...record,
    sections: record.sections.map((section) => (section.subsections ? { ...section, subsections: section.subsections.map(fill) } : section))
  };
}

// "08:12" from an ISO timestamp, in the reader's local time; "" when missing or unreadable.
export function formatSavedTime(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}
