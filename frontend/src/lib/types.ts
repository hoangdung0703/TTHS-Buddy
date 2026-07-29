// Shared response/request shapes matching the backend contract defined in requirements.md.
// Field names must stay in sync with what Phase 3-7 services will eventually return.

export interface Citation {
  dieu_number: string;
  dieu_title: string;
  law_version: string;
}

export interface ChatQueryRequest {
  question: string;
}

export interface ChatQueryResponse {
  answer: string;
  citations: Citation[];
}

export interface ChatSuggestion {
  id: string;
  text: string;
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

export interface QuizAnswer {
  question_id: string;
  selected_option: string;
}

export interface QuizSubmitRequest {
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

// Not part of the Phase 7 route list in requirements.md — a lightweight client-side
// stand-in for the Phase 6 "related articles from the same retrieval" note in frontend.md,
// surfaced on the dashboard's "study suggestions" card. Revisit once a real endpoint exists.
export interface RelatedArticle {
  dieu_number: string;
  dieu_title: string;
  reason: string;
}

// Also not one of the 8 documented routes - backs the dashboard's 3 quick-stat cards and the
// simplified "Tien do trac nghiem" card (frontend.md: single average score + total count, no
// per-category breakdown). Replace with real aggregation once Phase 5/7 logging exists.
export interface DashboardStats {
  quizzes_completed: number;
  dieu_studied: number;
  conversations_count: number;
  average_quiz_score_percentage: number;
}
