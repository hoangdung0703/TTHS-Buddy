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
// Phase 5a/5b v2 (mock-only, see requirements.md "Phase 5a/5b v2") - the real
// question bank + backend for these are NOT built yet (waiting on nhóm luật).
// These types describe the RESPONSE SHAPE the future real endpoints are
// expected to return, so that Bước 2 (wiring real API calls in lib/api.ts) is
// a data-source swap, not a type rewrite. Do not use these for /quiz or
// /essay's OLD (Phase 5a/5b original) flow - those keep using QuizQuestion /
// EssayQuestion above, unaffected by this mock detour.
// ============================================================================

export type QuizSetV2StatusKind = "untouched" | "in_progress" | "done";

export interface QuizSetV2Status {
  kind: QuizSetV2StatusKind;
  correct_count: number; // 0 when kind is "untouched"
}

// Future: GET /api/quiz/sets-v2 - 15 bộ x 5 câu mcq_4choice thuần túy (thay cho
// GET /api/quiz/sets 5-bộ-x-18-câu của Phase 5a gốc, xem "Phase 5a/5b v2").
export interface QuizSetSummaryV2 {
  quiz_set_id: number; // 1-15
  total_questions: number; // luôn = 5 ở v2
  status: QuizSetV2Status;
}

export type EssayBankCategory = "ly_thuyet" | "van_dung" | "ban_trac_nghiem" | "tinh_huong";

export type EssayBankProgressKind = "untouched" | "started" | "complete";

export interface EssayBankProgressV2 {
  kind: EssayBankProgressKind;
  attempted_count: number;
}

// Future: GET /api/essay/banks - 4 ngân hàng theo category (thay cho pool phẳng
// của Phase 5b gốc, xem "Phase 5a/5b v2").
export interface EssayBankV2 {
  category: EssayBankCategory;
  title: string;
  subtitle: string;
  description: string;
  total_questions: number;
  progress: EssayBankProgressV2;
}

// Future: POST /api/essay/question (v2) - cùng shape với EssayQuestion (Phase 5b
// gốc), thêm bank_category vì pool giờ tách theo ngân hàng.
export interface EssayQuestionV2 extends EssayQuestion {
  bank_category: EssayBankCategory;
}

// Future: POST /api/essay/practice/random - minigame "Tôi hỏi bạn trả lời", lấy
// ngẫu nhiên 1 câu từ TOÀN BỘ pool tự luận, không giới hạn theo category. Nút
// "Câu khác" chỉ gọi endpoint này lại (next random), KHÔNG gọi submit - bỏ qua
// hoàn toàn, không tính là 1 lượt làm bài (quyết định đã chốt trong requirements.md).
export interface PracticeQuestionV2 {
  question_id: string;
  bank_category: EssayBankCategory;
  bank_label: string;
  question_text: string;
  legal_ref: string;
  key_points: string[];
  feedback: string;
}
