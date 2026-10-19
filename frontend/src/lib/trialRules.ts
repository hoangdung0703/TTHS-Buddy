// Pure rules for "Phiên tòa giả định" (docs/phien-toa-gia-dinh/API-CONTRACT.md). No React, no
// fetch and no "@/" imports, so tests/trialRules.test.mjs can load this file directly with Node.
// Everything that decides WHAT the student may do comes from state.allowed_actions; the helpers
// here only translate that list into UI pieces and pre-check text the server would reject anyway.

import type { TrialState, TrialUtterance } from "./types";

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

// One line telling the student what this step expects of them. Purely explanatory: it never
// decides which buttons exist.
export function stepHint(step: number, role: string, isUserTurn: boolean): string {
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
}

export function parseTrialErrorBody(status: number, bodyText: string): ParsedTrialError {
  let body: unknown = null;
  try {
    body = bodyText.length > 0 ? JSON.parse(bodyText) : null;
  } catch {
    body = null;
  }
  const record = (body !== null && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const envelope = record.error as { code?: unknown } | undefined;
  const code = envelope !== undefined && typeof envelope.code === "string" ? envelope.code : null;
  const state = record.state !== undefined && record.state !== null && typeof record.state === "object"
    ? (record.state as TrialState)
    : null;
  const featureDisabled = status === 404 && envelope === undefined && record.detail === "Not Found";
  return { status, code, featureDisabled, state };
}

// Vietnamese, student-facing. Never includes anything the student typed.
export function messageForTrialError(error: Pick<ParsedTrialError, "status" | "code">): string {
  switch (error.code) {
    case "trial_daily_case_limit":
      return "Hôm nay bạn đã tạo đủ số vụ án cho phép. Bạn quay lại vào ngày mai nhé.";
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
  luat_su: "Luật sư bào chữa"
};

export const TRIAL_STATUS_LABELS: Record<string, string> = {
  active: "Đang diễn ra",
  completed: "Hoàn thành",
  abandoned: "Đã bỏ"
};

export const TRIAL_TOTAL_STEPS = 11;

// law_version values of the corpus (ingestion/document_registry.py), used by the "Điều N" pills to
// open the existing ArticleModal. Step legal_basis numbers are BLTTHS; charge, Điều 51/52 are BLHS.
export const LAW_VERSION_BLTTHS = "BLTTHS 2015 (số 101/2015/QH13, sửa đổi bổ sung 2021)";
export const LAW_VERSION_BLHS = "BLHS - Văn bản hợp nhất năm 2025";
