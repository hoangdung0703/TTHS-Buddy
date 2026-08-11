import {
  deleteMockConversation,
  gradeMockEssay,
  gradeMockQuiz,
  MOCK_CHAT_SUGGESTIONS,
  MOCK_CONVERSATIONS,
  MOCK_DASHBOARD_STATS,
  MOCK_ESSAY_QUESTIONS,
  MOCK_KEYWORDS_YESTERDAY,
  MOCK_QUIZ_QUESTIONS,
  MOCK_QUIZ_SETS,
  MOCK_WEAK_TOPICS,
  renameMockConversation,
  resolveMockChatAnswer,
  resolveMockConversationDetail,
  withMockDelay
} from "@/lib/mockData";
import { ESSAY_BANK_DESCRIPTIONS, ESSAY_BANK_SUBTITLES, ESSAY_BANK_TITLES } from "@/lib/essayBankPresentation";
import type {
  ChatStreamAnswerDeltaEvent,
  ChatStreamCitationsEvent,
  ChatStreamGradingEvent,
  ChatStreamSuggestedFollowupsEvent,
  ChatSuggestion,
  ConversationDetailResponse,
  ConversationListResponse,
  ConversationSummary,
  DashboardStats,
  EssayBankCategory,
  EssayBankQuestionListItem,
  EssayBankSummary,
  EssayBankV2,
  EssayQuestion,
  EssayQuestionV2,
  EssaySubmitRequest,
  EssaySubmitResponse,
  KeywordYesterday,
  LegalArticle,
  PracticeQuestionV2,
  QuizGenerateResponse,
  QuizQuestion,
  QuizSetSummary,
  QuizSetSummaryV2,
  QuizStatsV2,
  QuizSubmitRequest,
  QuizSubmitResponse,
  WeakTopic
} from "@/lib/types";
import { getSupabaseClient } from "@/lib/supabaseClient";

const DEFAULT_API_BASE_URL = "http://localhost:8000";

export class ApiError extends Error {
  public readonly status: number;

  public constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;
}

// Central switch: flip NEXT_PUBLIC_USE_MOCK_DATA to "false" once Phase 3-7 ship real data.
// No component should read this env var directly - every data access goes through this file.
function isMockDataEnabled(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCK_DATA !== "false";
}

// Every real (non-mock) route requires a Supabase JWT (see backend require_supabase_user) -
// attach it here once so individual api.ts functions don't each have to remember to.
async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await getSupabaseClient().auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<TResponse>(path: string, init: RequestInit = {}): Promise<TResponse> {
  const authHeader = await getAuthHeader();
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...init.headers
    }
  });

  if (!response.ok) {
    const errorMessage = await response.text();
    throw new ApiError(response.status, errorMessage || `Request failed with status ${response.status}`);
  }

  // DELETE/PATCH conversation routes return 204 No Content - response.json() would throw on the
  // empty body, so short-circuit instead of parsing.
  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

export async function getChatSuggestions(): Promise<ChatSuggestion[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_CHAT_SUGGESTIONS);
  }

  const { suggestions } = await apiFetch<{ suggestions: ChatSuggestion[] }>("/api/chat/suggestions");
  return suggestions;
}

export interface ChatStreamHandlers {
  onCitations: (event: ChatStreamCitationsEvent) => void;
  onDelta: (event: ChatStreamAnswerDeltaEvent) => void;
  onSuggestedFollowups: (event: ChatStreamSuggestedFollowupsEvent) => void;
  // Only fires for intent=answer_evaluation turns ("Sinh tình huống minh họa" Lượt 2) - see
  // ChatStreamGradingEvent.
  onGradingResult: (event: ChatStreamGradingEvent) => void;
}

// Parses one complete "event: <name>\ndata: <json>" block (already split on the blank-line
// separator by the caller) and dispatches it to the matching handler. Unknown/malformed blocks
// (e.g. a stray "done" event, which carries no data the UI needs) are ignored rather than
// thrown - a single unrecognized event must never abort an otherwise-successful stream.
function dispatchSseBlock(block: string, handlers: ChatStreamHandlers): void {
  let eventName: string | null = null;
  let dataLine: string | null = null;

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLine = line.slice("data:".length).trim();
    }
  }

  if (eventName === null || dataLine === null || dataLine.length === 0) {
    return;
  }

  const data = JSON.parse(dataLine) as unknown;
  if (eventName === "citations") {
    handlers.onCitations(data as ChatStreamCitationsEvent);
  } else if (eventName === "answer_delta") {
    handlers.onDelta(data as ChatStreamAnswerDeltaEvent);
  } else if (eventName === "suggested_followups") {
    handlers.onSuggestedFollowups(data as ChatStreamSuggestedFollowupsEvent);
  } else if (eventName === "grading_result") {
    handlers.onGradingResult(data as ChatStreamGradingEvent);
  }
}

export async function sendChatQuery(
  question: string,
  conversationId: string | null,
  handlers: ChatStreamHandlers
): Promise<void> {
  if (isMockDataEnabled()) {
    const mock = await withMockDelay(resolveMockChatAnswer(question));
    handlers.onCitations({
      citations: mock.citations,
      related_articles: [],
      conversation_id: conversationId ?? "mock-conversation",
      rewritten_question: question
    });
    handlers.onDelta({ delta: mock.answer });
    handlers.onSuggestedFollowups({ suggested_followups: [] });
    return;
  }

  const authHeader = await getAuthHeader();
  const response = await fetch(`${getApiBaseUrl()}/api/chat/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader },
    body: JSON.stringify(conversationId ? { question, conversation_id: conversationId } : { question })
  });

  if (!response.ok || response.body === null) {
    const errorMessage = await response.text();
    throw new ApiError(response.status, errorMessage || `Request failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      dispatchSseBlock(buffer.slice(0, separatorIndex), handlers);
      buffer = buffer.slice(separatorIndex + 2);
      separatorIndex = buffer.indexOf("\n\n");
    }
  }
}

export async function getConversations(): Promise<ConversationSummary[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_CONVERSATIONS);
  }

  const { conversations } = await apiFetch<ConversationListResponse>("/api/chat/conversations");
  return conversations;
}

export async function getConversationDetail(conversationId: string): Promise<ConversationDetailResponse> {
  if (isMockDataEnabled()) {
    return withMockDelay(resolveMockConversationDetail(conversationId));
  }

  return apiFetch<ConversationDetailResponse>(`/api/chat/conversations/${conversationId}`);
}

// Feature nhỏ - xóa hội thoại (see requirements.md "Xóa/đổi tên hội thoại + Sao chép câu trả
// lời"). Backend returns 204 No Content on success, 404 if the id doesn't exist or belongs to
// another user (same ownership-hides-behind-404 pattern as GET detail).
export async function deleteConversation(conversationId: string): Promise<void> {
  if (isMockDataEnabled()) {
    deleteMockConversation(conversationId);
    await withMockDelay(undefined);
    return;
  }

  await apiFetch<void>(`/api/chat/conversations/${conversationId}`, { method: "DELETE" });
}

// Feature nhỏ - đổi tên hội thoại. An empty/whitespace-only title tells the backend to clear the
// custom title (falls back to the auto-generated one from the first question) - the caller
// should re-fetch getConversations() afterward to pick up whichever title the server resolved,
// rather than guessing the fallback client-side.
export async function renameConversation(conversationId: string, title: string): Promise<void> {
  if (isMockDataEnabled()) {
    renameMockConversation(conversationId, title);
    await withMockDelay(undefined);
    return;
  }

  await apiFetch<void>(`/api/chat/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title })
  });
}

// GET /api/legal/articles/{dieu_number} - the citation-pill "read full article" feature (see
// requirements.md "Feature nhỏ - Xem toàn văn Điều luật từ citation pill"). law_version is
// required, not optional: several documents in the corpus reuse the same dieu_number
// (BLTTHS/BLHS/Nghi dinh 250/2 Thong tu lien tich), so it's the only thing that disambiguates
// which article a given citation pill is actually pointing at.
export async function getLegalArticle(dieuNumber: string, lawVersion: string): Promise<LegalArticle> {
  const query = new URLSearchParams({ law_version: lawVersion });
  return apiFetch<LegalArticle>(`/api/legal/articles/${encodeURIComponent(dieuNumber)}?${query.toString()}`);
}

export async function getQuizSets(): Promise<QuizSetSummary[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_QUIZ_SETS);
  }

  const { quiz_sets: quizSets } = await apiFetch<{ quiz_sets: QuizSetSummary[] }>("/api/quiz/sets");
  return quizSets;
}

export async function getQuiz(quizSet: number): Promise<QuizGenerateResponse> {
  if (isMockDataEnabled()) {
    return withMockDelay({ questions: MOCK_QUIZ_QUESTIONS });
  }

  return apiFetch<QuizGenerateResponse>("/api/quiz/generate", {
    method: "POST",
    body: JSON.stringify({ quiz_set: quizSet })
  });
}

export async function submitQuiz(request: QuizSubmitRequest): Promise<QuizSubmitResponse> {
  if (isMockDataEnabled()) {
    return withMockDelay(gradeMockQuiz(request.answers));
  }

  return apiFetch<QuizSubmitResponse>("/api/quiz/submit", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export async function getEssayQuestion(excludeQuestionId?: string): Promise<EssayQuestion> {
  if (isMockDataEnabled()) {
    const candidates = MOCK_ESSAY_QUESTIONS.filter((question) => question.question_id !== excludeQuestionId);
    const nextQuestion = candidates[0] ?? MOCK_ESSAY_QUESTIONS[0];
    return withMockDelay(nextQuestion);
  }

  return apiFetch<EssayQuestion>("/api/essay/question", { method: "POST", body: JSON.stringify({}) });
}

export async function submitEssay(request: EssaySubmitRequest): Promise<EssaySubmitResponse> {
  if (isMockDataEnabled()) {
    return withMockDelay(gradeMockEssay(request.question_id, request.user_answer));
  }

  return apiFetch<EssaySubmitResponse>("/api/essay/submit", {
    method: "POST",
    body: JSON.stringify(request)
  });
}

export async function getKeywordsYesterday(): Promise<KeywordYesterday[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_KEYWORDS_YESTERDAY);
  }

  const { keywords } = await apiFetch<{ keywords: KeywordYesterday[] }>("/api/dashboard/keywords-yesterday");
  return keywords;
}

export async function getWeakTopics(): Promise<WeakTopic[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_WEAK_TOPICS);
  }

  const { weak_topics: weakTopics } = await apiFetch<{ weak_topics: WeakTopic[] }>("/api/dashboard/weak-topics");
  return weakTopics;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_DASHBOARD_STATS);
  }

  return apiFetch<DashboardStats>("/api/dashboard/stats");
}

// ============================================================================
// Phase 5a/5b v2 (requirements.md "Phase 5a/5b v2" Buoc B) - 15 bộ x 5 câu
// mcq_4choice (Quiz) và 4 ngân hàng theo category, 111 câu (Essay). Không đi
// qua NEXT_PUBLIC_USE_MOCK_DATA - luôn gọi backend thật, thay thế hoàn toàn
// lib/mockDataV2.ts (đã xóa).
// ============================================================================

export async function getQuizSetsV2(): Promise<QuizSetSummaryV2[]> {
  const { quiz_sets: quizSets } = await apiFetch<{ quiz_sets: QuizSetSummaryV2[] }>("/api/quiz/sets");
  return quizSets;
}

export async function getQuizStatsV2(): Promise<QuizStatsV2> {
  return apiFetch<QuizStatsV2>("/api/quiz/stats");
}

export async function getQuizV2(quizSetId: number): Promise<QuizQuestion[]> {
  const { questions } = await apiFetch<QuizGenerateResponse>("/api/quiz/generate", {
    method: "POST",
    body: JSON.stringify({ quiz_set: quizSetId })
  });
  return questions;
}

export async function submitQuizV2(quizSetId: number, answers: QuizSubmitRequest["answers"]): Promise<QuizSubmitResponse> {
  return apiFetch<QuizSubmitResponse>("/api/quiz/submit", {
    method: "POST",
    body: JSON.stringify({ quiz_set: quizSetId, answers })
  });
}

function toEssayBankV2(summary: EssayBankSummary): EssayBankV2 {
  const attemptedCount = summary.questions_practiced;
  const kind = attemptedCount === 0 ? "untouched" : attemptedCount >= summary.total_questions ? "complete" : "started";

  return {
    category: summary.category,
    title: ESSAY_BANK_TITLES[summary.category],
    subtitle: ESSAY_BANK_SUBTITLES[summary.category],
    description: ESSAY_BANK_DESCRIPTIONS[summary.category],
    total_questions: summary.total_questions,
    progress: { kind, attempted_count: attemptedCount }
  };
}

export async function getEssayBanksV2(): Promise<EssayBankV2[]> {
  const { banks } = await apiFetch<{ banks: EssayBankSummary[] }>("/api/essay/banks");
  return banks.map(toEssayBankV2);
}

export async function getEssayBankQuestionListV2(category: EssayBankCategory): Promise<EssayBankQuestionListItem[]> {
  const { questions } = await apiFetch<{ category: EssayBankCategory; questions: EssayBankQuestionListItem[] }>(
    `/api/essay/banks/${category}/questions`
  );
  return questions;
}

export async function getPracticeQuestionV2(excludeQuestionId?: string): Promise<PracticeQuestionV2> {
  const question = await apiFetch<EssayQuestionV2 & { category: EssayBankCategory }>("/api/essay/question", {
    method: "POST",
    body: JSON.stringify(excludeQuestionId ? { exclude_question_id: excludeQuestionId } : {})
  });

  return {
    question_id: question.question_id,
    bank_category: question.category,
    bank_label: ESSAY_BANK_TITLES[question.category],
    question_text: question.question_text,
    legal_ref: question.dieu_number ? `Điều ${question.dieu_number} BLTTHS 2015` : "Không có Điều luật cụ thể"
  };
}
