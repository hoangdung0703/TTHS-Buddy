import {
  deleteMockConversation,
  gradeMockQuiz,
  MOCK_CHAT_SUGGESTIONS,
  MOCK_CONVERSATIONS,
  MOCK_DASHBOARD_STATS,
  MOCK_KEYWORDS_YESTERDAY,
  MOCK_QUIZ_QUESTIONS,
  MOCK_QUIZ_SETS,
  MOCK_WEAK_TOPICS,
  renameMockConversation,
  resolveMockChatAnswer,
  resolveMockConversationDetail,
  withMockDelay
} from "@/lib/mockData";
import type {
  ChatStreamAnswerDeltaEvent,
  ChatStreamCitationsEvent,
  ChatStreamErrorEvent,
  ChatStreamGradingEvent,
  ChatStreamStatusEvent,
  ChatStreamSuggestedFollowupsEvent,
  ChatSuggestion,
  ConversationDetailResponse,
  ConversationListResponse,
  ConversationSummary,
  DashboardStats,
  KeywordYesterday,
  LegalArticle,
  Note,
  NoteListResponse,
  NoteUpsertRequest,
  QuizGenerateResponse,
  QuizQuestion,
  QuizSetSummary,
  QuizSetSummaryV2,
  QuizStatsV2,
  QuizSubmitRequest,
  QuizSubmitResponse,
  TrialCreateRequest,
  TrialDetail,
  TrialListResponse,
  TrialRecord,
  TrialState,
  TrialUtterance,
  WeakTopic
} from "@/lib/types";
import { parseTrialErrorBody, type ParsedTrialError } from "@/lib/trialRules";
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
  // Progress text for the buffered path. Optional so existing callers keep compiling and so a
  // caller that does not care can simply omit it.
  onStatus?: (event: ChatStreamStatusEvent) => void;
  // Server-side failure reported inside the stream (the response is already 200 by then, so it
  // cannot arrive as an HTTP error). Optional for the same reason as onStatus.
  onError?: (event: ChatStreamErrorEvent) => void;
}

// Splits one complete "event: <name>\ndata: <json>" block (already split on the blank-line
// separator by the caller) into its name and parsed data, or null for a block without both.
function parseSseBlock(block: string): { eventName: string; data: unknown } | null {
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
    return null;
  }
  return { eventName, data: JSON.parse(dataLine) as unknown };
}

// Dispatches one block to the matching chat handler. Unknown/malformed blocks (e.g. a stray
// "done" event, which carries no data the UI needs) are ignored rather than thrown - a single
// unrecognized event must never abort an otherwise-successful stream.
function dispatchSseBlock(block: string, handlers: ChatStreamHandlers): void {
  const parsed = parseSseBlock(block);
  if (parsed === null) {
    return;
  }

  const { eventName, data } = parsed;
  if (eventName === "citations") {
    handlers.onCitations(data as ChatStreamCitationsEvent);
  } else if (eventName === "answer_delta") {
    handlers.onDelta(data as ChatStreamAnswerDeltaEvent);
  } else if (eventName === "suggested_followups") {
    handlers.onSuggestedFollowups(data as ChatStreamSuggestedFollowupsEvent);
  } else if (eventName === "grading_result") {
    handlers.onGradingResult(data as ChatStreamGradingEvent);
  } else if (eventName === "status") {
    handlers.onStatus?.(data as ChatStreamStatusEvent);
  } else if (eventName === "error") {
    handlers.onError?.(data as ChatStreamErrorEvent);
  }
}

// Reads a 2xx SSE body block by block. Shared by every streaming route (chat, notes, trials).
async function readSseBlocks(body: ReadableStream<Uint8Array>, onBlock: (block: string) => void): Promise<void> {
  const reader = body.getReader();
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
      onBlock(buffer.slice(0, separatorIndex));
      buffer = buffer.slice(separatorIndex + 2);
      separatorIndex = buffer.indexOf("\n\n");
    }
  }
}

// Shared by sendChatQuery and askAboutPassage - both routes speak the same SSE event format. Throws
// ApiError for a non-2xx response (auth, rate limit, validation), which arrives before the stream
// starts; failures after that arrive as an `error` event instead.
async function readSseStream(response: Response, handlers: ChatStreamHandlers): Promise<void> {
  if (!response.ok || response.body === null) {
    const errorMessage = await response.text();
    throw new ApiError(response.status, errorMessage || `Request failed with status ${response.status}`);
  }

  await readSseBlocks(response.body, (block) => dispatchSseBlock(block, handlers));
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

  await readSseStream(response, handlers);
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
// Trắc nghiệm v2 (requirements.md "Phase 5a/5b v2" Buoc B). Không đi qua
// NEXT_PUBLIC_USE_MOCK_DATA - luôn gọi backend thật.
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

// ============================================================================
// Vở ghi cá nhân: CRUD plus Giai đoạn 2 "Hỏi AI trên đoạn được chọn" (askAboutPassage). Notes are
// never read by Chat. Always hits the real backend (no NEXT_PUBLIC_USE_MOCK_DATA branch, same as
// the V2 quiz routes above).
// ============================================================================

export async function getNotes(): Promise<Note[]> {
  const { notes } = await apiFetch<NoteListResponse>("/api/notes");
  return notes;
}

export async function createNote(request: NoteUpsertRequest): Promise<Note> {
  return apiFetch<Note>("/api/notes", { method: "POST", body: JSON.stringify(request) });
}

export async function updateNote(noteId: string, request: NoteUpsertRequest): Promise<Note> {
  return apiFetch<Note>(`/api/notes/${noteId}`, { method: "PUT", body: JSON.stringify(request) });
}

export async function deleteNote(noteId: string): Promise<void> {
  await apiFetch<void>(`/api/notes/${noteId}`, { method: "DELETE" });
}

// Same limit as the backend's NotesAskRequest.passage (backend/app/models/notes.py). Both count
// UTF-16 units / code points the same way for Vietnamese text, which is all in the BMP.
export const PASSAGE_MAX_CHARS = 3000;
export const NOTES_QUESTION_MAX_CHARS = 2000;

export type NotesAskHandlers = Pick<ChatStreamHandlers, "onCitations" | "onDelta" | "onStatus" | "onError">;

// POST /api/notes/ask - SSE in the same format as /api/chat/query: status -> answer_delta (one,
// the answer is checked before it is sent) -> citations -> done, or an `error` event. The passage
// is sent to the model and discarded server-side; it is never stored.
export async function askAboutPassage(
  passage: string,
  question: string,
  conversationId: string | null,
  handlers: NotesAskHandlers
): Promise<void> {
  const authHeader = await getAuthHeader();
  const response = await fetch(`${getApiBaseUrl()}/api/notes/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader },
    body: JSON.stringify(
      conversationId ? { passage, question, conversation_id: conversationId } : { passage, question }
    )
  });

  await readSseStream(response, { ...handlers, onSuggestedFollowups: () => {}, onGradingResult: () => {} });
}

// ============================================================================
// Phiên tòa giả định (docs/phien-toa-gia-dinh/API-CONTRACT.md). Always the real backend. Nothing
// returned here may be written to storage or logs - callers keep it in component state only.
// ============================================================================

// Carries the parsed error envelope: `code` (trial_*, rate_limit_exceeded...), the server `state`
// on a 409, and `featureDisabled` for the TRIAL_ENABLED=false 404.
export class TrialApiError extends ApiError {
  public readonly code: string | null;
  public readonly featureDisabled: boolean;
  public readonly state: TrialState | null;
  public readonly serverMessage: string | null;

  public constructor(parsed: ParsedTrialError) {
    super(parsed.status, parsed.code ?? `HTTP ${parsed.status}`);
    this.name = "TrialApiError";
    this.code = parsed.code;
    this.featureDisabled = parsed.featureDisabled;
    this.state = parsed.state;
    this.serverMessage = parsed.serverMessage;
  }
}

async function trialRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const authHeader = await getAuthHeader();
  const response = await fetch(`${getApiBaseUrl()}/api/trials${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader, ...init.headers }
  });
  if (!response.ok) {
    throw new TrialApiError(parseTrialErrorBody(response.status, await response.text()));
  }
  return response;
}

// --- Feature probe ---------------------------------------------------------------------------------
// The flag lives only in the backend. HEAD /api/trials (contract 3.0) answers 204 when the feature
// is on, 404 when it is off and 401 without a valid token; unlike GET it runs no cleanup and no
// limit counting. Probed once per page load and kept in module memory (never in storage). Only a
// definite answer is cached; 401, a network error or 5xx leaves it unknown so a later page can ask
// again.
export type TrialFeatureStatus = "unknown" | "enabled" | "disabled";

let trialFeatureStatus: TrialFeatureStatus = "unknown";
let trialFeatureProbe: Promise<TrialFeatureStatus> | null = null;
const trialFeatureListeners = new Set<(status: TrialFeatureStatus) => void>();

export function getTrialFeatureStatus(): TrialFeatureStatus {
  return trialFeatureStatus;
}

export function rememberTrialFeature(status: Exclude<TrialFeatureStatus, "unknown">): void {
  if (trialFeatureStatus === status) {
    return;
  }
  trialFeatureStatus = status;
  trialFeatureListeners.forEach((listener) => listener(status));
}

export function subscribeTrialFeature(listener: (status: TrialFeatureStatus) => void): () => void {
  trialFeatureListeners.add(listener);
  return () => {
    trialFeatureListeners.delete(listener);
  };
}

export function probeTrialFeature(): Promise<TrialFeatureStatus> {
  if (trialFeatureStatus !== "unknown") {
    return Promise.resolve(trialFeatureStatus);
  }
  if (trialFeatureProbe === null) {
    trialFeatureProbe = headTrialFeature()
      .catch((): TrialFeatureStatus => "unknown")
      .then((status) => {
        trialFeatureProbe = null;
        if (status !== "unknown") {
          rememberTrialFeature(status);
        }
        return trialFeatureStatus;
      });
  }
  return trialFeatureProbe;
}

async function headTrialFeature(): Promise<TrialFeatureStatus> {
  const authHeader = await getAuthHeader();
  const response = await fetch(`${getApiBaseUrl()}/api/trials`, { method: "HEAD", headers: authHeader });
  if (response.ok) {
    return "enabled";
  }
  // A HEAD response has no body, but this route only answers 404 when TRIAL_ENABLED is off.
  if (response.status === 404) {
    return "disabled";
  }
  // A backend that predates the HEAD route: fall back to the GET probe.
  if (response.status === 405) {
    return getTrials()
      .then((): TrialFeatureStatus => "enabled")
      .catch((error: unknown): TrialFeatureStatus => (error instanceof TrialApiError && error.featureDisabled ? "disabled" : "unknown"));
  }
  return "unknown";
}

function noteFeatureFromError(error: unknown): void {
  if (error instanceof TrialApiError && error.featureDisabled) {
    rememberTrialFeature("disabled");
  }
}

// --- Plain routes ------------------------------------------------------------------------------------

async function trialJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    const response = await trialRequest(path, init);
    return (await response.json()) as T;
  } catch (error) {
    noteFeatureFromError(error);
    throw error;
  }
}

export async function getTrials(): Promise<TrialListResponse> {
  const result = await trialJson<TrialListResponse>("");
  rememberTrialFeature("enabled");
  return result;
}

export async function getTrial(sessionId: string): Promise<TrialDetail> {
  return trialJson<TrialDetail>(`/${encodeURIComponent(sessionId)}`);
}

// Returns the state object directly (contract 3.5: not wrapped).
export async function abandonTrial(sessionId: string): Promise<TrialState> {
  return trialJson<TrialState>(`/${encodeURIComponent(sessionId)}/abandon`, { method: "POST" });
}

// 204 No Content on success.
export async function deleteTrial(sessionId: string): Promise<void> {
  try {
    await trialRequest(`/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  } catch (error) {
    noteFeatureFromError(error);
    throw error;
  }
}

export async function getTrialRecord(sessionId: string): Promise<TrialRecord> {
  return trialJson<TrialRecord>(`/${encodeURIComponent(sessionId)}/record`);
}

// --- Streaming routes ----------------------------------------------------------------------------------

export interface TrialStreamHandlers {
  onStatus?: (message: string) => void;
  onSession?: (event: { session_id: string; title: string }) => void;
  onUtterance?: (utterance: TrialUtterance) => void;
  onState?: (state: TrialState) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

function dispatchTrialBlock(block: string, handlers: TrialStreamHandlers): void {
  const parsed = parseSseBlock(block);
  if (parsed === null) {
    return;
  }
  const { eventName, data } = parsed;
  if (eventName === "status") {
    handlers.onStatus?.((data as ChatStreamStatusEvent).message);
  } else if (eventName === "session") {
    handlers.onSession?.(data as { session_id: string; title: string });
  } else if (eventName === "utterance") {
    handlers.onUtterance?.(data as TrialUtterance);
  } else if (eventName === "state") {
    handlers.onState?.(data as TrialState);
  } else if (eventName === "error") {
    handlers.onError?.((data as ChatStreamErrorEvent).message);
  } else if (eventName === "done") {
    handlers.onDone?.();
  }
}

async function streamTrial(path: string, body: unknown, handlers: TrialStreamHandlers, signal?: AbortSignal): Promise<void> {
  let response: Response;
  try {
    response = await trialRequest(path, { method: "POST", body: JSON.stringify(body), signal });
  } catch (error) {
    noteFeatureFromError(error);
    throw error;
  }
  if (response.body === null) {
    throw new TrialApiError({ status: response.status, code: null, featureDisabled: false, state: null, serverMessage: null });
  }
  await readSseBlocks(response.body, (block) => dispatchTrialBlock(block, handlers));
}

// POST /api/trials - SSE: status x2 -> session -> utterance x n -> state -> done, or status -> error.
export async function createTrial(request: TrialCreateRequest, handlers: TrialStreamHandlers, signal?: AbortSignal): Promise<void> {
  await streamTrial("", request, handlers, signal);
}

export type TrialTurnRequest =
  | { expected_step: number; expected_version: number; action: "speak"; text: string; addressee?: string }
  | { expected_step: number; expected_version: number; action: "end_slot" | "continue" }
  | { expected_step: number; expected_version: number; action: "advance"; target_step: number };

// POST /api/trials/{id}/turn - SSE. Only the fields of the chosen action are sent: the schema
// forbids extras.
export async function sendTrialTurn(
  sessionId: string,
  request: TrialTurnRequest,
  handlers: TrialStreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  await streamTrial(`/${encodeURIComponent(sessionId)}/turn`, request, handlers, signal);
}
