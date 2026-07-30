import {
  gradeMockEssay,
  gradeMockQuiz,
  MOCK_CHAT_SUGGESTIONS,
  MOCK_DASHBOARD_STATS,
  MOCK_ESSAY_QUESTIONS,
  MOCK_KEYWORDS_YESTERDAY,
  MOCK_QUIZ_QUESTIONS,
  MOCK_QUIZ_SETS,
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
  QuizSetSummary,
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
