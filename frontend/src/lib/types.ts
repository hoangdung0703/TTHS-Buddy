// Shared response/request shapes matching the backend contract defined in requirements.md.
// Field names must stay in sync with what Phase 3-7 services will eventually return.

export interface Citation {
  dieu_number: string;
  dieu_title: string;
  law_version: string;
}

// GET /api/legal/articles/{dieu_number} - full-text lookup for the citation-pill "read full
// article" feature (see requirements.md "Feature nhỏ - Xem toàn văn Điều luật từ citation pill").
export interface LegalArticle {
  dieu_number: string;
  dieu_title: string | null;
  law_version: string | null;
  source_document: string;
  full_text: string;
}

export interface ChatQueryRequest {
  question: string;
}

export interface ChatQueryResponse {
  answer: string;
  citations: Citation[];
}

export interface RelatedArticle {
  dieu_number: string;
  dieu_title: string | null;
}

export interface SuggestedFollowup {
  dieu_number: string;
  suggested_question: string;
}

// POST /api/chat/query is SSE (Phase 4 Extension) - one of these per event, in this fixed
// order: citations -> answer_delta (one or more) -> suggested_followups -> done. Matches
// backend/app/models/chat.py's ChatStream*Event models.
export interface ChatStreamCitationsEvent {
  citations: Citation[];
  related_articles: RelatedArticle[];
  conversation_id: string;
  rewritten_question: string;
  // True when the earlier turns of this conversation could not be read and the answer was produced
  // without them. Optional because a backend from before this field omits it - treated as false.
  context_unavailable?: boolean;
}

export interface ChatStreamAnswerDeltaEvent {
  delta: string;
}

export interface ChatStreamSuggestedFollowupsEvent {
  suggested_followups: SuggestedFollowup[];
}

// Progress text while the server withholds the answer to run the citation-grounding guard
// (~80% of traffic - see requirements.md 2026-10-12). Always arrives before the first
// answer_delta, so it never reorders the existing events.
export interface ChatStreamStatusEvent {
  message: string;
}

// Terminal failure reported INSIDE the stream. Once the response headers are out the HTTP status
// is already 200 and cannot be changed, so a failure after that point arrives as this event
// followed by a clean close rather than as an HTTP error.
export interface ChatStreamErrorEvent {
  message: string;
}

// Only emitted for intent=answer_evaluation ("Sinh tình huống minh họa" Lượt 2), between
// answer_delta and suggested_followups. Deliberately has NO score/percentage field - matched/
// missing points only.
export interface ChatStreamGradingEvent {
  matched_points: string[];
  missing_points: string[];
  missing_points_display?: string[] | null;
}

export interface ChatSuggestion {
  id: string;
  text: string;
}

// GET /api/chat/conversations / GET /api/chat/conversations/{id} (Phase 4 Extension 2) - Sidebar
// history list + conversation reload. Matches backend/app/models/chat.py's
// Conversation*/ChatStream* models.
export interface ConversationSummary {
  conversation_id: string;
  title: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
}

export interface ConversationTurn {
  question: string;
  answer: string;
  created_at: string;
}

export interface ConversationDetailResponse {
  conversation_id: string;
  turns: ConversationTurn[];
}

export interface QuizQuestion {
  question_id: string;
  question_text: string;
  mcq_options: string[];
  dieu_number: string;
  topic_category: string;
}

export interface QuizGenerateResponse {
  questions: QuizQuestion[];
}

export interface QuizSetSummary {
  quiz_set: number;
  total_questions: number;
  main_topics: string[];
}

export interface QuizAnswer {
  question_id: string;
  selected_option: string;
}

export interface QuizSubmitRequest {
  quiz_set: number;
  answers: QuizAnswer[];
}

export interface QuizResult {
  question_id: string;
  is_correct: boolean;
  mcq_correct: string;
  dieu_number: string;
  explanation: string | null;
}

export interface QuizSubmitResponse {
  score: number;
  total: number;
  results: QuizResult[];
  // Whether the attempt was stored. Optional: a backend from before this field existed omits it,
  // and its absence must read as "saved" - only an explicit false means the write failed.
  saved?: boolean;
}

export interface KeywordYesterday {
  dieu_number: string;
  keyword: string;
  count: number;
}

export interface WeakTopic {
  topic_category: string;
  score_percentage: number;
}

// Matches GET /api/dashboard/stats exactly as specified in requirements.md Phase 7 - backs the
// dashboard's 3 quick-stat cards and the simplified "Tien do trac nghiem" card (single average
// score + total count, no per-category breakdown, per the "bản rút gọn cho 05/09" scope note).
export interface DashboardStats {
  total_quiz_attempts: number;
  average_score: number;
  dieu_studied_count: number;
}

// ============================================================================
// Trắc nghiệm v2 (real backend, see requirements.md "Phase 5a/5b v2" Buoc B).
// Backend routes: GET /api/quiz/sets, GET /api/quiz/stats.
// ============================================================================

export type QuizSetV2StatusKind = "untouched" | "done";

export interface QuizSetV2Status {
  kind: QuizSetV2StatusKind;
  correct_count: number; // 0 when kind is "untouched"
}

// GET /api/quiz/sets - số bộ đề và số câu mỗi bộ do ngân hàng đề quyết định, không cố định.
export interface QuizSetSummaryV2 {
  quiz_set_id: number;
  total_questions: number;
  status: QuizSetV2Status;
}

// GET /api/quiz/stats - dùng cho Dashboard Khối 1 (progress ring MCQ tổng hợp).
export interface QuizStatsV2 {
  average_score_percentage: number;
  correct_total: number;
  questions_total: number;
  quiz_sets_attempted: number;
  total_quiz_sets: number;
}

// Vở ghi cá nhân (requirements.md "Feature - Vở ghi cá nhân + Chat trả lời dựa trên nội dung ghi
// chú"). This is the storage/CRUD foundation only - NOT yet read by Chat/retrieval.
export interface Note {
  id: string;
  title: string | null;
  content: string;
  tag: string | null;
  created_at: string;
  updated_at: string;
}

export interface NoteListResponse {
  notes: Note[];
}

export interface NoteUpsertRequest {
  title: string | null;
  content: string;
  tag: string | null;
}

// ============================================================================
// Phiên tòa giả định (docs/phien-toa-gia-dinh/API-CONTRACT.md is the source of truth for every
// shape below). Never persisted client-side: transcript, case file and record live in page memory
// only and are re-read with GET /api/trials/{id}.
// ============================================================================

// The roles the client knows how to present. Which ones may be chosen comes from config.user_roles.
export type TrialUserRole = "ksv" | "luat_su" | "nguoi_xem" | "thu_ky" | "bi_cao" | "chu_toa";
export type TrialStatus = "active" | "completed" | "abandoned";
export type TrialAwaiting = "user" | "ai" | "none";
export type TrialUtteranceKind = "speech" | "procedural" | "notice";

export interface TrialSummary {
  session_id: string;
  title: string;
  crime_key: string;
  user_role: TrialUserRole;
  current_step: number;
  status: TrialStatus;
  updated_at: string;
}

export interface TrialCrime {
  crime_key: string;
  crime_name: string;
  dieu: string;
  allowed_khoan: string[];
}

export interface TrialConfig {
  crimes: TrialCrime[];
  user_roles: string[];
  limits: { max_cases_per_day: number; max_active_sessions: number; max_witnesses: number; abandon_after_days: number };
  // usage_available = false: the server could not read the usage log (cases_today is then 0 but
  // does not mean the quota is used up). Missing on an older backend: treat as true.
  remaining: { cases_today: number; active_sessions: number; usage_available?: boolean };
}

export interface TrialListResponse {
  sessions: TrialSummary[];
  config: TrialConfig;
}

export interface TrialCreateRequest {
  crime_key: string;
  user_role: TrialUserRole;
  victim_present: boolean;
  witness_count: number;
  has_related_party: boolean;
}

export interface TrialState {
  session_id: string;
  current_step: number;
  step_title: string;
  status: TrialStatus;
  awaiting: TrialAwaiting;
  allowed_actions: string[];
  version: number;
  // Characters allowed for the next "speak" in the current slot; null when speaking is not
  // allowed. Optional so an older backend without the field still parses.
  text_limits?: { min: number; max: number } | null;
  // Observer role only (contract 5.1): the static procedure note of current_step; null otherwise.
  procedure_note?: TrialProcedureNote | null;
  // Clerk role only (contract 5.2): what to note down at current_step; null otherwise.
  clerk_prompt?: TrialClerkPrompt | null;
  // Clerk role only, while the step-1 report waits for the student: template text and the summoned
  // people to check it against; null at any other time.
  clerk_report?: TrialClerkReport | null;
  // Defendant role only (contract 5.3): the question put to the student that waits for an answer
  // (đoạn xen); null at any other time and for every other role.
  pending_question?: TrialPendingQuestion | null;
  // Presiding judge role only, steps 2-11 (contract 5.4): the step's checklist, counters and limits.
  presiding?: TrialPresiding | null;
  // Presiding judge role only, steps 10-11: the student's own decision. Not used before step 10.
  decision?: Record<string, unknown> | null;
}

export type TrialPresidingItemKind = "item" | "ask" | "invite" | "return" | "decide" | "pronounce";

export interface TrialPresidingItem {
  key: string;
  label: string;
  kind: TrialPresidingItemKind;
  required: boolean;
  done: boolean;
  // Can be done right now (order, conditions, no AI running).
  available: boolean;
  // "Dùng lời mẫu" text with full names; null when the item has none.
  template: string | null;
  // BLTTHS article numbers.
  basis: string[];
  ai_calls: number;
  note: string | null;
}

export interface TrialPresidingLimits {
  item: { min: number; max: number };
  ask: { min: number; max: number };
  remark: { min: number; max: number };
  reasoning?: { min: number; max: number };
}

export interface TrialPresiding {
  step: number;
  items: TrialPresidingItem[];
  missing_required: string[];
  counters: { questions_left: number; remarks_left: number; debate_rounds: number };
  ask_addressees: string[];
  remark_addressees: string[];
  limits: TrialPresidingLimits;
  // Điều 323: the button may be pressed now / was used / the short step 5 is running.
  return_available: boolean;
  returned: boolean;
  in_return: boolean;
  // false = template wording still a draft; shown neutrally, no review badge (contract 5.4).
  templates_reviewed: boolean;
}

export interface TrialDeclineNote {
  text: string;
  // Full citations as the server writes them ("điểm h khoản 2 Điều 61 Bộ luật Tố tụng hình sự").
  legal_basis: string[];
  reviewed: boolean;
}

export interface TrialPendingQuestion {
  // The question's utterance in the transcript.
  seq: number;
  speaker_id: string;
  speaker_role: string;
  speaker_name: string;
  text: string;
  // Step-2 identity question only: the answer built from the case file, prefilled and editable.
  prefill: string | null;
  // Present when "decline" is allowed (steps 4-5).
  decline_note: TrialDeclineNote | null;
}

// "Vai của bạn" (contract 3.3): the defendant's own character card, a role-play hint only. The key
// is absent for every other role.
export interface TrialRoleBrief {
  stance: string;
  knowledge: string[];
  demeanor: string;
  // Shown verbatim (contract Mục 9.14).
  note: string;
}

export interface TrialClerkPrompt {
  step: number;
  text: string;
  reviewed: boolean;
}

export interface TrialAttendanceEntry {
  speaker_id: string;
  role: string;
  name: string;
  // false = absent, with a request to be tried in absence.
  present: boolean;
}

export interface TrialClerkReport {
  prefill: string;
  attendance: TrialAttendanceEntry[];
}

export interface TrialProcedureNote {
  step: number;
  title: string;
  text: string;
  // BLTTHS article numbers.
  legal_basis: string[];
  // false = draft still waiting for the legal team's review.
  reviewed: boolean;
}

export interface TrialUtterance {
  seq: number;
  step: number;
  speaker_id: string;
  speaker_role: string;
  speaker_name: string;
  is_user: boolean;
  kind: TrialUtteranceKind;
  text: string;
  addressee: string | null;
  // Presiding judge sessions only: the checklist item this line carries out; null otherwise.
  procedure_item?: string | null;
}

export interface TrialParticipant {
  id: string;
  role: string;
  name: string;
  gender?: string;
}

export interface TrialStepInfo {
  number: number;
  title: string;
  legal_basis: string[];
}

export interface TrialPerson {
  id: string;
  // Panel display name, already anonymised by the server ("Trần Đức H").
  name?: string | null;
  gender?: string | null;
  age?: number | null;
  occupation?: string | null;
  residence_place?: string | null;
  statement_summary?: string | null;
  education?: string | null;
  prior_record?: string | null;
  preventive_measure?: string | null;
}

export interface TrialFact {
  id: string;
  time?: string | null;
  place?: string | null;
  description: string;
}

export interface TrialEvidence {
  id: string;
  type: string;
  description: string;
  value_vnd?: number | null;
  injury_percent?: number | null;
  fact_id?: string | null;
}

export interface TrialPretrialStatement {
  person_id: string;
  summary: string;
  inconsistencies?: { text: string; claimed_amount_vnd?: number | null }[];
}

export interface TrialCircumstance {
  khoan: string;
  diem: string;
  fact_ids?: string[];
}

// Deliberately no character cards and no defendant_plea: the server never sends them (contract
// Mục 7), and nothing here may depend on a verdict either.
export interface TrialCaseFile {
  title?: string;
  incident_summary?: string;
  defendant?: TrialPerson | null;
  victim?: TrialPerson | null;
  witnesses?: TrialPerson[];
  related_party?: TrialPerson | null;
  facts?: TrialFact[];
  evidence?: TrialEvidence[];
  pretrial_statements?: TrialPretrialStatement[];
  charge?: { dieu: string; khoan: string; diem?: string[]; crime_name: string } | null;
  measure_value?: number | null;
  compensation_vnd?: number | null;
  extra_amounts?: { label: string; amount_vnd: number; evidence_id?: string | null }[];
  mitigating?: TrialCircumstance[];
  aggravating?: TrialCircumstance[];
  civil_claim?: { claimant_id: string; amount_vnd: number; basis?: string | null } | null;
  indictment_text?: string;
  // id -> panel display name, anonymised for lay participants (contract Mục 7).
  display_names?: Record<string, string>;
}

export interface TrialDetail {
  state: TrialState;
  title: string;
  crime_key: string;
  user_role: TrialUserRole;
  disclaimer: string;
  court: { name: string; hearing_date: string; venue: string };
  participants: Record<string, TrialParticipant>;
  case_file: TrialCaseFile;
  steps: TrialStepInfo[];
  utterances: TrialUtterance[];
  // Defendant sessions only; the key is missing otherwise.
  role_brief?: TrialRoleBrief;
}

// GET /api/trials/{id}/record (contract 3.7): `record` follows Mẫu số 22-HS; `text` is its plain
// rendering, for copy and as a fallback. `record` is optional so an older backend still renders.
export interface TrialRecordField {
  label: string;
  // null = no data: shown as the form's dotted blank, never filled in.
  value: string | null;
  // Value assigned by the simulation (date, venue, ...), shown as such.
  simulated?: boolean;
}

export interface TrialRecordEntry {
  seq: number;
  step: number;
  speaker_role: string;
  speaker_name: string;
  text: string;
}

export interface TrialRecordSection {
  heading: string;
  // "user": written by the student clerk (contract 3.7); `summary` is their text, null when empty.
  content?: "verbatim" | "summary" | "user" | null;
  summary?: string | null;
  author_note?: string | null;
  summary_fallback?: boolean;
  fields?: TrialRecordField[];
  entries?: TrialRecordEntry[];
  notes?: string[];
  subsections?: TrialRecordSection[];
}

export interface TrialRecordDocument {
  disclaimer: string;
  form_reference: string;
  // Lines outside the form shown right after the opening disclaimer (observer sessions); [] otherwise.
  preamble?: string[];
  court_name: string;
  national_header: string[];
  title: string;
  subtitle: string;
  opening: TrialRecordField[];
  sections: TrialRecordSection[];
  closing: TrialRecordField[];
  signatures: { title: string; note: string; name: string }[];
  appendix?: TrialRecordSection[];
  // true = the student clerk has not finalised the record yet.
  draft?: boolean;
}

export interface TrialRecord {
  session_id: string;
  text: string;
  record?: TrialRecordDocument;
  // Clerk sessions only (contract 3.7/3.9); null for every other role.
  clerk?: TrialClerkDraft | null;
}

// GET/PUT /api/trials/{id}/notes (contract 3.8). Stored on the server only, never in the browser.
export interface TrialNotes {
  notes: string;
  updated_at: string | null;
  max_chars: number;
}

export type TrialClerkSection = "iv2" | "iv3";

export interface TrialClerkNotice {
  section: TrialClerkSection;
  code: string;
  // Vietnamese, shown as sent.
  message: string;
}

// PUT /record/draft response, also `clerk` of GET /record (contract 3.9).
export interface TrialClerkDraft {
  iv2: string;
  iv3: string;
  updated_at: string | null;
  finalized: boolean;
  finalized_at: string | null;
  notices: TrialClerkNotice[];
  limits: { min: number; max: number; hard_max: number };
}
