import {
  gradeMockEssay,
  gradeMockQuiz,
  MOCK_CHAT_SUGGESTIONS,
  MOCK_DASHBOARD_STATS,
  MOCK_ESSAY_QUESTIONS,
  MOCK_KEYWORDS_YESTERDAY,
  MOCK_QUIZ_QUESTIONS,
  MOCK_RELATED_ARTICLES,
  MOCK_WEAK_TOPICS,
  resolveMockChatAnswer,
  withMockDelay
} from "@/lib/mockData";
import type {
  ChatQueryResponse,
  ChatSuggestion,
  DashboardStats,
  EssayQuestion,
  EssaySubmitRequest,
  EssaySubmitResponse,
  KeywordYesterday,
  QuizGenerateResponse,
  QuizSubmitRequest,
  QuizSubmitResponse,
  RelatedArticle,
  WeakTopic
} from "@/lib/types";

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

export async function apiFetch<TResponse>(path: string, init: RequestInit = {}): Promise<TResponse> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers
    }
  });

  if (!response.ok) {
    const errorMessage = await response.text();
    throw new ApiError(response.status, errorMessage || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

export async function getChatSuggestions(): Promise<ChatSuggestion[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_CHAT_SUGGESTIONS);
  }

  return apiFetch<ChatSuggestion[]>("/api/chat/suggestions");
}

export async function sendChatQuery(question: string): Promise<ChatQueryResponse> {
  if (isMockDataEnabled()) {
    return withMockDelay(resolveMockChatAnswer(question));
  }

  return apiFetch<ChatQueryResponse>("/api/chat/query", {
    method: "POST",
    body: JSON.stringify({ question })
  });
}

export async function getQuiz(): Promise<QuizGenerateResponse> {
  if (isMockDataEnabled()) {
    return withMockDelay({ questions: MOCK_QUIZ_QUESTIONS });
  }

  return apiFetch<QuizGenerateResponse>("/api/quiz/generate", { method: "POST", body: JSON.stringify({}) });
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

  return apiFetch<KeywordYesterday[]>("/api/dashboard/keywords-yesterday");
}

export async function getWeakTopics(): Promise<WeakTopic[]> {
  if (isMockDataEnabled()) {
    return withMockDelay(MOCK_WEAK_TOPICS);
  }

  return apiFetch<WeakTopic[]>("/api/dashboard/weak-topics");
}

// See the RelatedArticle comment in lib/types.ts - this is not one of the documented
// Phase 7 routes, kept mock-only until a real endpoint is defined.
export async function getRelatedArticles(): Promise<RelatedArticle[]> {
  return withMockDelay(MOCK_RELATED_ARTICLES);
}

// See the DashboardStats comment in lib/types.ts - backs the quick-stat cards and the
// simplified quiz progress card, kept mock-only until real log aggregation exists.
export async function getDashboardStats(): Promise<DashboardStats> {
  return withMockDelay(MOCK_DASHBOARD_STATS);
}
