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
}

export interface ChatStreamAnswerDeltaEvent {
  delta: string;
}

export interface ChatStreamSuggestedFollowupsEvent {
  suggested_followups: SuggestedFollowup[];
}

// Only emitted for intent=answer_evaluation ("Sinh tình huống minh họa" Lượt 2), between
// answer_delta and suggested_followups. Deliberately has NO score/percentage field - matched/
// missing points only, same shape as EssaySubmitResponse's grading fields so the chat UI can
// reuse that module's matched/missing visual language.
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
}

export interface EssayQuestion {
  question_id: string;
  question_text: string;
  dieu_number: string;
  topic_category: string;
}

export interface EssaySubmitRequest {
  question_id: string;
  user_answer: string;
}

export interface EssaySubmitResponse {
  matched_points: string[];
  missing_points: string[];
  feedback: string;
  suggested_dieu: string[];
  // Display-only, natural-language merge of missing_points. Null/undefined when the LLM didn't
  // return a usable value - render missing_points as separate bullets instead.
  missing_points_display?: string[] | null;
}

export interface KeywordYesterday {
  dieu_number: string;
  keyword: string;
  count: number;
}

export interface WeakTopic {
  topic_category: string;
  score_percentage: number;
  // Real essay bank category the user actually practiced this topic under (derived server-side
  // from essay_attempts.category), null when only quiz history exists for this topic - see
  // requirements.md "Feature — Redesign Dashboard Hero".
  essay_bank_category: EssayBankCategory | null;
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
// Phase 5a/5b v2 (real backend, see requirements.md "Phase 5a/5b v2" Buoc B) -
// 15 bộ x 5 câu mcq_4choice thuần túy (Quiz) và 4 ngân hàng theo category, 111
// câu (Essay). Backend routes: GET /api/quiz/sets, GET /api/quiz/stats,
// GET /api/essay/banks, POST /api/essay/question (body: {category?,
// exclude_question_id?}).
// ============================================================================

export type QuizSetV2StatusKind = "untouched" | "done";

export interface QuizSetV2Status {
  kind: QuizSetV2StatusKind;
  correct_count: number; // 0 when kind is "untouched"
}

// GET /api/quiz/sets - 15 bộ x 5 câu mcq_4choice thuần túy.
export interface QuizSetSummaryV2 {
  quiz_set_id: number; // 1-15
  total_questions: number; // luôn = 5 ở v2
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

export type EssayBankCategory = "ly_thuyet" | "van_dung" | "ban_trac_nghiem" | "tinh_huong";

export type EssayBankProgressKind = "untouched" | "started" | "complete";

export interface EssayBankProgressV2 {
  kind: EssayBankProgressKind;
  attempted_count: number;
}

// Raw shape from GET /api/essay/banks - title/subtitle/description/icon are
// presentation-only and NOT sent by the backend (see lib/essayBankPresentation.ts);
// combined with those into EssayBankV2 client-side (see lib/api.ts getEssayBanksV2).
export interface EssayBankSummary {
  category: EssayBankCategory;
  total_questions: number;
  questions_practiced: number;
}

export interface EssayBankV2 {
  category: EssayBankCategory;
  title: string;
  subtitle: string;
  description: string;
  total_questions: number;
  progress: EssayBankProgressV2;
}

// POST /api/essay/question - cùng shape với EssayQuestion (Phase 5b gốc), thêm
// bank_category vì pool giờ tách theo ngân hàng.
export interface EssayQuestionV2 extends EssayQuestion {
  bank_category: EssayBankCategory;
}

// GET /api/essay/banks/{category}/questions - backs the "chọn tự do" grid (requirements.md
// "Doi luong Tu luan"). status derived server-side from the latest essay_attempts row for that
// question. Deliberately NO dieu_number field - that's the answer's legal basis (see
// ingestion/question_bank.json's "explanation"), and this endpoint returns the whole bank's list
// in one response before the user has opened/answered any of them, so including it would leak
// every question's answer over the wire even though the UI never renders it pre-submit.
export type EssayBankQuestionStatus = "done" | "needs_review" | "not_done";

export interface EssayBankQuestionListItem {
  question_id: string;
  order: number;
  question_text: string;
  status: EssayBankQuestionStatus;
}

// Minigame "Tôi hỏi bạn trả lời" - lấy ngẫu nhiên 1 câu từ TOÀN BỘ pool tự luận
// (POST /api/essay/question không kèm category), không giới hạn theo category.
// Nút "Câu khác" gọi lại endpoint này với exclude_question_id = câu hiện tại,
// KHÔNG gọi submit - bỏ qua hoàn toàn, không tính là 1 lượt làm bài (quyết định
// đã chốt trong requirements.md). legal_ref suy ra client-side từ dieu_number.
export interface PracticeQuestionV2 {
  question_id: string;
  bank_category: EssayBankCategory;
  bank_label: string;
  question_text: string;
  legal_ref: string;
}
