// Pure rules for "Phiên tòa giả định" (docs/phien-toa-gia-dinh/API-CONTRACT.md). No React, no
// fetch and no "@/" imports, so tests/trialRules.test.mjs can load this file directly with Node.
// Everything that decides WHAT the student may do comes from state.allowed_actions; the helpers
// here only translate that list into UI pieces and pre-check text the server would reject anyway.

import type {
  TrialClerkDraft,
  TrialClerkSection,
  TrialConfig,
  TrialDecisionCheck,
  TrialDecisionCircumstance,
  TrialDecisionDraft,
  TrialDecisionFinding,
  TrialDecisionForm,
  TrialDecisionState,
  TrialExhibitDisposition,
  TrialPenaltyFrame,
  TrialPenaltyType,
  TrialPresiding,
  TrialPresidingItem,
  TrialRecordDocument,
  TrialRecordSection,
  TrialState,
  TrialUtterance
} from "./types";

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

// The defendant (contract 5.3) answers questions at steps 2, 4, 5 and speaks freely at 7-9.
const DEFENDANT_TEXT_LABELS: Record<number, string> = {
  7: "Ý kiến bổ sung",
  8: "Ý kiến tranh luận",
  9: "Lời nói sau cùng"
};

function textLabelForStep(step: number, role = ""): string {
  if (isDefendantRole(role)) {
    return DEFENDANT_TEXT_LABELS[step] ?? "Câu trả lời";
  }
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
// per-step fallback. The label (wording only) always comes from the step and the role.
export function textLimitsForState(state: Pick<TrialState, "current_step" | "text_limits">, role = ""): TrialTextLimits {
  if (isValidServerLimits(state.text_limits)) {
    return { min: state.text_limits.min, max: state.text_limits.max, label: textLabelForStep(state.current_step, role) };
  }
  if (isDefendantRole(role)) {
    // Fallback mirrors contract 3.4: answers 1-1500, steps 7-9 1-3000.
    return { min: 1, max: state.current_step >= 7 ? 3000 : TRIAL_TEXT_DEFAULT_MAX, label: textLabelForStep(state.current_step, role) };
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
  // Defendant role, steps 4-5: refuse to answer the pending question.
  canDecline: boolean;
}

export function parseAllowedActions(actions: readonly string[]): ParsedActions {
  const parsed: ParsedActions = { canSpeak: false, addressees: null, canEndSlot: false, advanceTo: null, canContinue: false, canDecline: false };
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
    } else if (action === "decline") {
      parsed.canDecline = true;
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
//  - "preside": presiding judge role (contract 5.4), the step's checklist actions
//  - "finished": completed or abandoned
export type ComposerMode = "speak" | "advance" | "paused" | "exhausted" | "waiting" | "preside" | "finished";

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
  if (hasPresidingAction(state.allowed_actions)) {
    return "preside";
  }
  if (parsed.advanceTo !== null) {
    return "advance";
  }
  return "waiting";
}

export function endSlotLabel(step: number, role = ""): string {
  // Contract 5.3: the defendant's two optional turns.
  if (isDefendantRole(role) && (step === 7 || step === 8)) {
    return step === 7 ? "Không bổ sung" : "Không có ý kiến";
  }
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

// The defendant role (contract 5.3): answers each question the AI puts to them ("đoạn xen"), may
// refuse at steps 4-5, has two optional turns (steps 7, 8) and the last word (step 9).
export const DEFENDANT_ROLE = "bi_cao";

export function isDefendantRole(role: string): boolean {
  return role === DEFENDANT_ROLE;
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
  if (isDefendantRole(role)) {
    return defendantStepHint(step, isUserTurn);
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

function defendantStepHint(step: number, isUserTurn: boolean): string {
  if (!isUserTurn) {
    return observerStepHint(step);
  }
  switch (step) {
    case 2:
      return "Trả lời câu hỏi của Chủ tọa. Câu hỏi lý lịch đã điền sẵn từ hồ sơ; kiểm tra rồi sửa nếu cần.";
    case 4:
    case 5:
      return "Trả lời câu hỏi đang chờ. Bạn có quyền từ chối trả lời; việc từ chối được ghi vào biên bản.";
    case 7:
      return "Bạn có thể bổ sung ý kiến bào chữa cho mình, hoặc bấm “Không bổ sung”.";
    case 8:
      return "Bạn có thể tranh luận với Kiểm sát viên, hoặc bấm “Không có ý kiến”.";
    case 9:
      return "Nói lời sau cùng. Không ai được đặt câu hỏi khi bị cáo nói lời sau cùng; nói xong là hết phần này.";
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
  // Presiding judge, 409 trial_procedure_incomplete: the required items still to do ([] otherwise).
  missingItems: string[];
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
  const missingItems = Array.isArray(record.missing_items) ? record.missing_items.filter((key): key is string => typeof key === "string") : [];
  return { status, code, featureDisabled, state, missingItems, serverMessage };
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
    case "trial_procedure_incomplete":
      return "Chưa chuyển bước được: còn mục bắt buộc chưa làm. Các mục đó đã được đánh dấu trong khung Điều hành.";
    case "trial_item_not_available":
      return "Mục này chưa làm được lúc này (chưa đúng thứ tự hoặc chưa đủ điều kiện). Đã tải lại trạng thái phiên tòa.";
    case "trial_item_done":
      return "Mục này đã làm rồi. Muốn nói thêm, bạn dùng “Phát biểu khác”.";
    case "trial_return_not_allowed":
      return "Chưa trở lại xét hỏi được lúc này: chỉ ở bước 8, sau ít nhất một vòng đối đáp và trước khi kết thúc tranh luận.";
    case "trial_return_used":
      return "Phiên này đã trở lại xét hỏi một lần; không dùng lại được.";
    case "trial_decision_missing":
      return "Bạn lưu bản nháp quyết định trước đã.";
    case "trial_decision_invalid":
      return "Bản nháp quyết định còn lỗi cần sửa trước khi chốt.";
    case "trial_decision_locked":
      return "Quyết định đã chốt nên không sửa được nữa.";
    case "trial_pronouncement_missing":
      return "Chưa có lời tuyên soạn sẵn. Bạn soạn lời tuyên trước đã.";
    case "trial_not_presiding":
      return "Phiên tòa này không phải vai Chủ tọa.";
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
    || code === "trial_skip_not_allowed" || code === "trial_not_active" || code === "trial_busy"
    || code === "trial_item_not_available" || code === "trial_item_done" || code === "trial_return_not_allowed"
    || code === "trial_return_used" || code === "trial_decision_locked" || code === "trial_pronouncement_missing";
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
  thu_ky: "Thư ký phiên tòa",
  bi_cao: "Bị cáo",
  chu_toa: "Chủ tọa phiên tòa"
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

// --- Defendant (contract 5.3) -------------------------------------------------------------------------

// The presiding judge's invitation that opens an optional defendant turn (steps 7, 8): the server
// writes it as a plain utterance, with no pending_question. The latest CHU_TOA line of the step,
// unless the student has spoken after it.
export function chairInvitation(utterances: readonly TrialUtterance[], step: number): TrialUtterance | null {
  for (let index = utterances.length - 1; index >= 0; index--) {
    const utterance = utterances[index];
    if (utterance.step !== step || utterance.is_user) {
      return null;
    }
    if (utterance.speaker_id === "CHU_TOA" && utterance.kind !== "notice") {
      return utterance;
    }
  }
  return null;
}

// "điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự" -> the article and corpus law_version for an
// ArticlePill; null when the citation names no article of a known code.
export function legalBasisArticle(citation: string): { dieu: string; lawVersion: string } | null {
  const match = /Điều\s+(\d+)/.exec(citation);
  if (match === null) {
    return null;
  }
  if (/Tố tụng hình sự|BLTTHS/.test(citation)) {
    return { dieu: match[1], lawVersion: LAW_VERSION_BLTTHS };
  }
  if (/Bộ luật Hình sự|BLHS/.test(citation)) {
    return { dieu: match[1], lawVersion: LAW_VERSION_BLHS };
  }
  return null;
}

export const DECLINE_CONFIRM_MESSAGE =
  "Từ chối trả lời câu hỏi này? Biên bản sẽ ghi “Bị cáo không trả lời câu hỏi này.” và Hội đồng xét xử có thể công bố lời khai của bạn ở giai đoạn điều tra.";

// --- Presiding judge (contract 5.4) --------------------------------------------------------------------

// The student runs the hearing from step 2: a checklist per step (state.presiding), the AI speaking
// only when asked or invited. Which item is done, required or available, and when the step may
// move on, is read from state.presiding and state.allowed_actions only (contract Mục 9.15).
export const CHAIR_ROLE = "chu_toa";

export function isChairRole(role: string): boolean {
  return role === CHAIR_ROLE;
}

const PRESIDING_ACTION_PREFIXES = ["item:", "ask:", "invite:"];
const PRESIDING_ACTIONS = ["remark", "return_to_questioning", "decide", "prepare_pronouncement", "pronounce"];

export function hasPresidingAction(actions: readonly string[]): boolean {
  return actions.some((action) => PRESIDING_ACTIONS.includes(action) || PRESIDING_ACTION_PREFIXES.some((prefix) => action.startsWith(prefix)));
}

export interface ChairActions {
  // Keys listed in "item:k1|k2" / "invite:k1|k2".
  items: string[];
  invites: string[];
  // Who may be questioned now ("ask:ID1|ID2"); [] when no question may be put.
  askTo: string[];
  canRemark: boolean;
  canReturn: boolean;
  advanceTo: number | null;
}

export function parseChairActions(actions: readonly string[]): ChairActions {
  const parsed: ChairActions = { items: [], invites: [], askTo: [], canRemark: false, canReturn: false, advanceTo: null };
  const list = (action: string, prefix: string) => action.slice(prefix.length).split("|").filter((key) => key.length > 0);
  for (const action of actions) {
    if (action.startsWith("item:")) {
      parsed.items = list(action, "item:");
    } else if (action.startsWith("invite:")) {
      parsed.invites = list(action, "invite:");
    } else if (action.startsWith("ask:")) {
      parsed.askTo = list(action, "ask:");
    } else if (action === "remark") {
      parsed.canRemark = true;
    } else if (action === "return_to_questioning") {
      parsed.canReturn = true;
    } else if (action.startsWith("advance:")) {
      const target = Number(action.slice("advance:".length));
      parsed.advanceTo = Number.isInteger(target) ? target : null;
    }
  }
  return parsed;
}

// Who a question of this ask item may go to (contract 5.4: hoi_bi_cao is the defendant,
// hoi_nguoi_khac everyone else, hoi_lai anyone), within the server's current list.
export function askAddresseesForItem(key: string, askTo: readonly string[]): string[] {
  if (key === "hoi_bi_cao") {
    return askTo.filter((id) => id === "BI_CAO");
  }
  if (key === "hoi_nguoi_khac") {
    return askTo.filter((id) => id !== "BI_CAO");
  }
  return [...askTo];
}

// Whether the item can be acted on now: the server marks it available AND its action is listed.
export function chairItemActionable(item: TrialPresidingItem, actions: ChairActions): boolean {
  if (!item.available || chairItemInDeliberation(item)) {
    return false;
  }
  switch (item.kind) {
    case "item":
      return actions.items.includes(item.key);
    case "invite":
      return actions.invites.includes(item.key);
    case "ask":
      return askAddresseesForItem(item.key, actions.askTo).length > 0;
    case "return":
      return actions.canReturn;
    default:
      return false;
  }
}

// "Dùng lời mẫu" is one click when the template says everything the action needs: items and
// invitations (empty text = template), and a question that can only go to one person.
export function chairOneClickTemplate(item: TrialPresidingItem, actions: ChairActions): boolean {
  if (item.template === null || item.template.trim().length === 0 || !chairItemActionable(item, actions)) {
    return false;
  }
  if (item.kind === "ask") {
    return askAddresseesForItem(item.key, actions.askTo).length === 1;
  }
  return item.kind === "item" || item.kind === "invite";
}

// What the composer sends: one checklist item ("item:<key>" / "invite:<key>"), a question, a
// "phát biểu khác", or the Điều 323 return.
export type ChairTarget = string;

export interface ChairTargetOption {
  value: ChairTarget;
  label: string;
}

export function chairTargetOptions(presiding: TrialPresiding, actions: ChairActions): ChairTargetOption[] {
  const options: ChairTargetOption[] = [];
  for (const item of presiding.items) {
    if ((item.kind === "item" || item.kind === "invite") && chairItemActionable(item, actions)) {
      options.push({ value: `${item.kind}:${item.key}`, label: item.label });
    }
  }
  if (actions.askTo.length > 0) {
    options.push({ value: "ask", label: "Đặt câu hỏi" });
  }
  if (actions.canRemark) {
    options.push({ value: "remark", label: "Phát biểu khác" });
  }
  if (actions.canReturn) {
    options.push({ value: "return", label: "Trở lại xét hỏi (Điều 323)" });
  }
  return options;
}

// The chosen target if still offered; otherwise a question when one may be put, then the first
// required item not done yet, then whatever is first.
export function resolveChairTarget(current: ChairTarget, presiding: TrialPresiding, options: readonly ChairTargetOption[]): ChairTarget | null {
  if (options.some((option) => option.value === current)) {
    return current;
  }
  if (options.some((option) => option.value === "ask")) {
    return "ask";
  }
  const required = presiding.items.find((item) => item.required && !item.done && options.some((option) => option.value === `${item.kind}:${item.key}`));
  if (required !== undefined) {
    return `${required.kind}:${required.key}`;
  }
  return options[0]?.value ?? null;
}

// The checklist item behind an "item:<key>" / "invite:<key>" target.
export function chairTargetItem(target: ChairTarget, presiding: TrialPresiding): TrialPresidingItem | null {
  const [kind, key] = target.split(":");
  if (key === undefined || (kind !== "item" && kind !== "invite")) {
    return null;
  }
  return presiding.items.find((item) => item.key === key && item.kind === kind) ?? null;
}

// Length limits of a target (from presiding.limits); `optional` = an empty box sends the template.
export function chairTextLimits(target: ChairTarget, presiding: TrialPresiding): TrialTextLimits & { optional: boolean } {
  if (target === "ask") {
    return { ...presiding.limits.ask, label: "Câu hỏi", optional: false };
  }
  if (target === "remark") {
    return { ...presiding.limits.remark, label: "Phát biểu", optional: false };
  }
  const item = target === "return" ? null : chairTargetItem(target, presiding);
  const hasTemplate = target === "return" || (item?.template ?? "").trim().length > 0;
  return { ...presiding.limits.item, label: "Lời điều hành", optional: hasTemplate };
}

// Null when the text can be sent; an empty box is fine where the template stands in.
export function validateChairText(text: string, limits: TrialTextLimits & { optional: boolean }): string | null {
  if (limits.optional && text.trim().length === 0) {
    return text.length > limits.max ? validateTrialText(text, limits) : null;
  }
  return validateTrialText(text, limits);
}

// Labels of every checklist item (backend trial_presiding.STEP_ITEMS), for lines of earlier steps
// in the transcript; the current step's labels come from state.presiding and win.
const CHAIR_ITEM_LABELS: Record<string, string> = {
  khai_mac: "Khai mạc, đọc quyết định đưa vụ án ra xét xử",
  kiem_tra_can_cuoc: "Kiểm tra căn cước bị cáo",
  kiem_tra_co_mat: "Kiểm tra sự có mặt, giới thiệu thành phần",
  giai_thich_quyen: "Phổ biến quyền và nghĩa vụ",
  hoi_thay_doi: "Hỏi đề nghị thay đổi người tiến hành tố tụng",
  cam_doan_nlc: "Người làm chứng cam đoan, cách ly người làm chứng",
  hoi_yeu_cau: "Hỏi yêu cầu triệu tập thêm, xem xét chứng cứ, hoãn phiên tòa",
  moi_cong_bo_cao_trang: "Mời Kiểm sát viên công bố cáo trạng",
  hoi_bi_cao: "Hỏi bị cáo",
  cong_bo_loi_khai_bi_hai: "Công bố lời khai của bị hại vắng mặt",
  hoi_nguoi_khac: "Hỏi người tham gia tố tụng khác",
  moi_hoi_tham_hoi: "Mời Hội thẩm hỏi",
  moi_ksv_hoi: "Mời Kiểm sát viên xét hỏi",
  moi_ls_hoi: "Mời luật sư xét hỏi",
  ket_thuc_xet_hoi: "Kết thúc xét hỏi",
  hoi_lai: "Hỏi lại",
  moi_luan_toi: "Mời Kiểm sát viên trình bày luận tội",
  moi_bao_chua: "Mời luật sư bào chữa",
  moi_bi_hai_trinh_bay: "Mời bị hại trình bày",
  hoi_bi_cao_bo_sung: "Hỏi bị cáo có bổ sung ý kiến bào chữa",
  moi_doi_dap: "Mời đối đáp (vòng 1)",
  vong_2: "Mời đối đáp thêm (vòng 2)",
  tro_lai_xet_hoi: "Trở lại việc xét hỏi",
  ket_thuc_tranh_luan: "Kết thúc tranh luận",
  moi_loi_sau_cung: "Cho bị cáo nói lời sau cùng",
  vao_nghi_an: "Vào phòng nghị án",
  tuyen_an: "Tuyên án",
  remark: "Phát biểu khác"
};

export function chairItemLabel(key: string | null | undefined, presiding?: TrialPresiding | null): string | null {
  if (!key) {
    return null;
  }
  return presiding?.items.find((item) => item.key === key)?.label ?? CHAIR_ITEM_LABELS[key] ?? null;
}

// One line on what the student does at this step. Explanatory only.
export function chairStepHint(step: number, presiding: TrialPresiding | null | undefined): string {
  if (presiding?.in_return) {
    return "Trở lại xét hỏi (Điều 323): hỏi thêm nếu cần, có thể mời Kiểm sát viên, luật sư hỏi, rồi kết thúc xét hỏi để về lại bước 8.";
  }
  switch (step) {
    case 1:
      return "Thư ký báo cáo sự có mặt. Từ bước 2 bạn điều hành phiên tòa.";
    case 2:
      return "Khai mạc trước tiên, rồi làm các mục còn lại. AI chỉ nói khi bạn hỏi hoặc mời.";
    case 4:
      return "Hỏi bị cáo ít nhất một câu; có thể hỏi người khác hoặc mời Hội thẩm hỏi.";
    case 5:
      return "Mời Kiểm sát viên, luật sư xét hỏi, rồi kết thúc xét hỏi.";
    case 8:
      return "Mời đối đáp; kết thúc tranh luận sau cùng.";
    case 9:
      return presiding?.items.some((item) => item.key === "moi_loi_sau_cung" && item.done)
        ? "Bị cáo đã nói lời sau cùng: không ai được hỏi thêm bị cáo (khoản 2 Điều 324 BLTTHS)."
        : "Cho bị cáo nói lời sau cùng.";
    case 10:
      return "Vào phòng nghị án; ở đó bạn lập quyết định, kiểm tra và chốt.";
    case 11:
      return "Hệ thống soạn lời tuyên từ quyết định bạn đã chốt; đọc trước rồi tuyên án.";
    default:
      return "Làm các mục bắt buộc trong khung Điều hành, rồi bấm “Sang bước tiếp theo”.";
  }
}

export const CHAIR_RETURN_CONFIRM_MESSAGE =
  "Trở lại xét hỏi (Điều 323 BLTTHS)? Mỗi phiên chỉ dùng được một lần. Phiên tòa quay về bước 5 thu gọn: bạn hỏi tối đa 3 câu, có thể mời Kiểm sát viên, luật sư hỏi, rồi kết thúc xét hỏi để về lại bước 8 và đối đáp lại.";

// --- Presiding judge: deliberation and judgment (contract 3.11, 5.4, steps 10-11) ------------------

// The deliberation room opens once "vào phòng nghị án" is done (step 10) and stays for step 11.
export function chairDeliberationOpen(state: Pick<TrialState, "current_step" | "presiding" | "decision">): boolean {
  if (state.decision === null || state.decision === undefined) {
    return false;
  }
  if (state.current_step >= 11) {
    return true;
  }
  return state.current_step === 10 && (state.presiding?.items.some((item) => item.key === "vao_nghi_an" && item.done) ?? false);
}

// Checklist rows that are done in the deliberation room, never from the checklist: the assessors'
// comments (their invitation would otherwise put a line in the transcript), "decide" and "pronounce".
export function chairItemInDeliberation(item: Pick<TrialPresidingItem, "key" | "kind">): boolean {
  return item.kind === "decide" || item.kind === "pronounce" || item.key === "y_kien_hoi_tham";
}

export const PENALTY_TYPE_LABELS: Record<TrialPenaltyType, string> = {
  tu: "Tù có thời hạn",
  cai_tao_khong_giam_giu: "Cải tạo không giam giữ",
  phat_tien: "Phạt tiền",
  khong: "Không có hình phạt"
};

export const DISPOSITION_LABELS: Record<TrialExhibitDisposition, string> = {
  tra_lai: "Trả lại cho chủ sở hữu hoặc người quản lý hợp pháp",
  tich_thu_sung_ngan_sach: "Tịch thu, nộp ngân sách nhà nước",
  tich_thu_tieu_huy: "Tịch thu và tiêu hủy",
  luu_ho_so: "Lưu trong hồ sơ vụ án"
};

// What the form holds while the student edits: numbers as typed, choices that must be made
// explicitly ("" / null) instead of a default that would suggest an answer.
export interface DecisionFormValues {
  guilty: boolean | null;
  khoan: string;
  diem: string[];
  penalty_type: TrialPenaltyType | "";
  penalty_months: string;
  fine_vnd: string;
  suspended: boolean;
  probation_months: string;
  applies_dieu_54: boolean;
  mitigating: TrialDecisionCircumstance[];
  aggravating: TrialDecisionCircumstance[];
  civil_amount_vnd: string;
  reasoning_summary: string;
  exhibits: Record<string, TrialExhibitDisposition | "">;
  defendant_pays_criminal_fee: boolean;
  defendant_pays_civil_fee: boolean;
}

const numberText = (value: number | null | undefined): string => (value === null || value === undefined ? "" : String(value));

// The saved draft as form values, or an empty form: only the charged khoản and điểm are preselected
// (contract 5.4); nothing else is filled in.
export function decisionFormValues(decision: Pick<TrialDecisionState, "draft" | "form">): DecisionFormValues {
  const { draft, form } = decision;
  const exhibits: Record<string, TrialExhibitDisposition | ""> = {};
  for (const id of form.exhibits) {
    exhibits[id] = draft?.exhibits.find((exhibit) => exhibit.evidence_id === id)?.disposition ?? "";
  }
  if (draft === null) {
    return {
      guilty: null, khoan: form.charged_khoan, diem: [...form.charged_diem], penalty_type: "", penalty_months: "", fine_vnd: "", suspended: false,
      probation_months: "", applies_dieu_54: false, mitigating: [], aggravating: [], civil_amount_vnd: "", reasoning_summary: "", exhibits,
      defendant_pays_criminal_fee: false, defendant_pays_civil_fee: false
    };
  }
  return {
    guilty: draft.guilty,
    khoan: draft.khoan,
    diem: [...draft.diem],
    penalty_type: draft.penalty_type,
    penalty_months: numberText(draft.penalty_months),
    fine_vnd: numberText(draft.fine_vnd),
    suspended: draft.suspended,
    probation_months: numberText(draft.probation_months),
    applies_dieu_54: draft.applies_dieu_54,
    mitigating: draft.mitigating.map((item) => ({ ...item, fact_ids: [...item.fact_ids] })),
    aggravating: draft.aggravating.map((item) => ({ ...item, fact_ids: [...item.fact_ids] })),
    civil_amount_vnd: numberText(draft.civil_amount_vnd),
    reasoning_summary: draft.reasoning_summary,
    exhibits,
    defendant_pays_criminal_fee: draft.defendant_pays_criminal_fee,
    defendant_pays_civil_fee: draft.defendant_pays_civil_fee
  };
}

// "2.000.000", "2 000 000 đồng" -> 2000000; "" -> null. Digits only: the inputs never hold a sign.
export function parseWholeNumber(text: string): number | null {
  const digits = text.replace(/\D/g, "");
  if (digits.length === 0) {
    return null;
  }
  const value = Number(digits);
  return Number.isSafeInteger(value) ? value : null;
}

// Choices the schema needs before the draft can be sent (422 otherwise). Everything else - even a
// draft full of hard errors - is saved and checked by the server.
export function decisionUnsetFields(values: DecisionFormValues): ("guilty" | "penalty_type")[] {
  const unset: ("guilty" | "penalty_type")[] = [];
  if (values.guilty === null) {
    unset.push("guilty");
  }
  if (values.penalty_type === "") {
    unset.push("penalty_type");
  }
  return unset;
}

export const DECISION_UNSET_MESSAGES: Record<"guilty" | "penalty_type", string> = {
  guilty: "Chọn bị cáo có tội hay không phạm tội trước khi lưu.",
  penalty_type: "Chọn loại hình phạt chính trước khi lưu (không phạm tội thì chọn “Không có hình phạt”)."
};

// The PUT /decision body.decision. Only the contract's fields; fine_vnd only with phạt tiền,
// probation only with án treo; exhibits without a chosen disposition are left out (the server then
// reports exhibit_missing). Null when a schema-required choice is still unset.
export function decisionBody(values: DecisionFormValues, form: Pick<TrialDecisionForm, "dieu" | "exhibits">): TrialDecisionDraft | null {
  if (values.guilty === null || values.penalty_type === "") {
    return null;
  }
  const exhibits: TrialDecisionDraft["exhibits"] = [];
  for (const id of form.exhibits) {
    const disposition = values.exhibits[id];
    if (disposition) {
      exhibits.push({ evidence_id: id, disposition });
    }
  }
  return {
    guilty: values.guilty,
    dieu: form.dieu,
    khoan: values.khoan,
    diem: [...values.diem],
    penalty_type: values.penalty_type,
    penalty_months: parseWholeNumber(values.penalty_months),
    fine_vnd: values.penalty_type === "phat_tien" ? parseWholeNumber(values.fine_vnd) : null,
    suspended: values.suspended,
    probation_months: values.suspended ? parseWholeNumber(values.probation_months) : null,
    applies_dieu_54: values.applies_dieu_54,
    mitigating: values.mitigating.map((item) => ({ khoan: item.khoan, diem: item.diem, fact_ids: [...item.fact_ids] })),
    aggravating: values.aggravating.map((item) => ({ khoan: item.khoan, diem: item.diem, fact_ids: [...item.fact_ids] })),
    civil_amount_vnd: parseWholeNumber(values.civil_amount_vnd),
    reasoning_summary: values.reasoning_summary,
    exhibits,
    defendant_pays_criminal_fee: values.defendant_pays_criminal_fee,
    defendant_pays_civil_fee: values.defendant_pays_civil_fee
  };
}

// True when the form differs from what is saved (the draft, or the empty form when nothing is).
export function decisionDirty(values: DecisionFormValues, saved: DecisionFormValues): boolean {
  return JSON.stringify(values) !== JSON.stringify(saved);
}

export interface FieldFindings {
  errors: TrialDecisionFinding[];
  warnings: TrialDecisionFinding[];
}

// The server's findings about one field ("khoan", "mitigating[0]", ...), exact match.
export function decisionFindingsFor(check: TrialDecisionCheck | null | undefined, field: string): FieldFindings {
  return {
    errors: check?.errors.filter((finding) => finding.field === field) ?? [],
    warnings: check?.warnings.filter((finding) => finding.field === field) ?? []
  };
}

// Fields the form shows findings next to. A finding about any other field (or a row that no longer
// exists) is listed in the summary at the top instead, so none is ever hidden.
const DECISION_FIELDS = new Set([
  "guilty", "dieu", "khoan", "diem", "penalty_type", "penalty_months", "fine_vnd", "suspended", "probation_months", "applies_dieu_54",
  "mitigating", "aggravating", "civil_amount_vnd", "reasoning_summary", "exhibits", "defendant_pays_criminal_fee", "defendant_pays_civil_fee"
]);

export function decisionFieldShown(field: string, rows: { mitigating: number; aggravating: number }): boolean {
  if (DECISION_FIELDS.has(field)) {
    return true;
  }
  const match = /^(mitigating|aggravating)\[(\d+)\]$/.exec(field);
  return match !== null && Number(match[2]) < rows[match[1] as "mitigating" | "aggravating"];
}

// "36 tháng (3 năm)"-style durations: whole years when exact.
export function monthsLabel(months: number): string {
  if (months < 12) {
    return `${months} tháng`;
  }
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return rest === 0 ? `${years} năm` : `${years} năm ${rest} tháng`;
}

// The penalty frame of a khoản as the form shows it next to the months box (contract 5.4: frames).
export function penaltyFrameText(frame: TrialPenaltyFrame | null | undefined): string {
  if (frame === null || frame === undefined) {
    return "Hệ thống chưa tách được khung hình phạt của khoản này.";
  }
  const parts = [`tù từ ${monthsLabel(frame.prison_min_months)} đến ${monthsLabel(frame.prison_max_months)}`];
  if (frame.non_custodial_max_months !== null) {
    parts.push(`cải tạo không giam giữ đến ${monthsLabel(frame.non_custodial_max_months)}`);
  }
  if (frame.fine_as_main) {
    parts.push("phạt tiền");
  }
  return `Khung: ${parts.join("; ")}.`;
}

// "decide" is offered only by the server (no hard error in the saved draft); the form also waits for
// unsaved edits to be saved and checked first.
export function canDecide(state: Pick<TrialState, "allowed_actions" | "decision">, dirty: boolean): boolean {
  return !dirty && state.allowed_actions.includes("decide") && (state.decision?.check?.errors.length ?? 1) === 0;
}

export const CHAIR_DECIDE_CONFIRM_MESSAGE =
  "Chốt quyết định? Sau khi chốt, bạn không sửa được bản nháp nữa; lời tuyên án sẽ được soạn từ đúng quyết định này.";
export const CHAIR_PRONOUNCE_CONFIRM_MESSAGE =
  "Tuyên án bằng lời tuyên này? Lời tuyên được ghi vào diễn biến phiên tòa dưới tên Chủ tọa và phiên tòa kết thúc.";
export const CHAIR_LEAVE_CONFIRM_MESSAGE = "Bản nháp quyết định có thay đổi chưa lưu. Rời trang thì các thay đổi này sẽ mất. Vẫn rời trang?";
