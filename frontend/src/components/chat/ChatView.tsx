"use client";

import { AlertCircle, Check, Copy, Scale, SendHorizontal } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { CitationList } from "@/components/chat/CitationList";
import { FormattedAnswer } from "@/components/chat/FormattedAnswer";
import { ApiError, getChatSuggestions, getConversationDetail, sendChatQuery } from "@/lib/api";
import type { ChatSuggestion, Citation } from "@/lib/types";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

const COPY_FEEDBACK_DURATION_MS = 1800;

function createMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Module-scoped (not component state) so it survives the unmount/remount that router.replace
// causes when a bare-/chat conversation gets its first real conversation_id (see the finally
// block in handleAsk below). Without this, the freshly-mounted /chat/[id] instance starts with
// empty messages and re-fetches from the server - and if a 2nd question is sent before that
// fetch resolves, its plain setMessages(loaded) overwrite (not a functional update) can wipe out
// the just-appended message, since both race to be the last setMessages call. Handing the
// already-correct local state across the remount avoids the refetch (and the race) entirely.
let pendingFreshConversationHandoff: { conversationId: string; messages: ChatMessage[] } | null = null;

interface ChatViewProps {
  // The conversation_id segment from the URL (/chat/[conversationId]), or null on the bare
  // /chat route - null means "start a brand new conversation", matching the pre-existing
  // "Hoi thoai moi" behavior exactly (see requirements.md Phase 4 Extension 2).
  conversationId: string | null;
}

export function ChatView({ conversationId }: ChatViewProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    pendingFreshConversationHandoff?.conversationId === conversationId
      ? pendingFreshConversationHandoff.messages
      : []
  );
  const [suggestions, setSuggestions] = useState<ChatSuggestion[]>([]);
  const [input, setInput] = useState<string>("");
  const [isSending, setIsSending] = useState<boolean>(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(
    conversationId !== null && pendingFreshConversationHandoff?.conversationId !== conversationId
  );
  const [error, setError] = useState<string | null>(null);
  // Client-held for the lifetime of this chat session (Phase 4 Extension) - captured from the
  // first "citations" SSE event and reused on every follow-up question so the backend can look
  // up recent turns for query understanding/multi-turn context. Initialized from the URL's
  // conversationId (Phase 4 Extension 2) when reloading an existing conversation, instead of
  // always starting null.
  const [activeConversationId, setActiveConversationId] = useState<string | null>(conversationId);
  // Distinguishes "waiting for the first byte" (show the typing-dots indicator) from "actively
  // streaming into a message bubble" (show the bubble instead) - null before the first SSE event
  // of the current request arrives, then the id of the assistant message being streamed into.
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  // Feature nhỏ - "Sao chép" button transient feedback: which assistant message's copy just
  // succeeded, reset after COPY_FEEDBACK_DURATION_MS so the icon/label reverts on its own.
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Guards the auto-send-from-?q= flow (requirements.md "Feature — Redesign Dashboard Hero",
  // nút "Ôn tập") against double-firing (React StrictMode double-invokes effects in dev, and
  // this component re-renders while the query is streaming in).
  const autoSendHandledRef = useRef(false);
  // Mirrors `messages` synchronously so handleAsk's finally block can hand off the freshest
  // array to pendingFreshConversationHandoff without waiting for a re-render.
  const messagesRef = useRef<ChatMessage[]>(messages);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    void getChatSuggestions().then(setSuggestions);
  }, []);

  // /chat?q=<topic question> (Dashboard "Chủ đề cần ôn lại" -> "Ôn tập"): only on the bare /chat
  // route (conversationId === null, always a brand-new conversation - see ChatViewProps), auto
  // fill + send the question through the normal handleAsk/SSE pipeline, then strip the param via
  // router.replace so a refresh/back doesn't resend it.
  useEffect(() => {
    if (conversationId !== null || autoSendHandledRef.current) {
      return;
    }
    const autoQuestion = searchParams.get("q");
    if (autoQuestion === null || autoQuestion.trim().length === 0) {
      return;
    }
    autoSendHandledRef.current = true;
    void handleAsk(autoQuestion).finally(() => {
      router.replace(pathname);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, searchParams]);

  // Re-runs whenever the URL's conversationId changes (including navigating directly from one
  // conversation to another via the Sidebar, which Next.js may reuse the same page component
  // instance for - a plain "load once on mount" effect would miss that transition entirely).
  useEffect(() => {
    setActiveConversationId(conversationId);
    setError(null);

    if (conversationId === null) {
      setMessages([]);
      setIsLoadingHistory(false);
      return;
    }

    if (pendingFreshConversationHandoff?.conversationId === conversationId) {
      // Already seeded via the lazy useState initializer above - this mount is the router.replace
      // landing right after this exact conversation was created locally, so there's nothing new
      // to fetch from the server (and fetching here is what causes the clobber race described
      // above).
      pendingFreshConversationHandoff = null;
      setIsLoadingHistory(false);
      return;
    }

    let cancelled = false;
    setIsLoadingHistory(true);
    setMessages([]);

    getConversationDetail(conversationId)
      .then((detail) => {
        if (cancelled) {
          return;
        }
        const loaded: ChatMessage[] = detail.turns.flatMap((turn) => [
          { id: createMessageId(), role: "user" as const, content: turn.question },
          { id: createMessageId(), role: "assistant" as const, content: turn.answer }
        ]);
        setMessages(loaded);
      })
      .catch((loadError: unknown) => {
        if (cancelled) {
          return;
        }
        const message =
          loadError instanceof ApiError ? loadError.message : "Không thể tải lại hội thoại này, vui lòng thử lại.";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingHistory(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  async function handleAsk(question: string): Promise<void> {
    const trimmed = question.trim();
    if (trimmed.length === 0 || isSending) {
      return;
    }

    // Keeps messagesRef synchronously in step with every update made in this function, so the
    // finally block below can hand the freshest array to pendingFreshConversationHandoff without
    // depending on the separate mirroring effect (which only flushes after a commit+paint cycle
    // - too late relative to this function's own synchronous "just finished streaming" instant).
    function updateMessages(updater: (current: ChatMessage[]) => ChatMessage[]): void {
      setMessages((current) => {
        const next = updater(current);
        messagesRef.current = next;
        return next;
      });
    }

    setError(null);
    setInput("");
    updateMessages((current) => [...current, { id: createMessageId(), role: "user", content: trimmed }]);
    setIsSending(true);

    const assistantMessageId = createMessageId();
    let assistantMessageStarted = false;
    // Bare /chat (conversationId prop null) never pushes the URL to /chat/[id] on its own, so a
    // conversation started there leaves pathname stuck at "/chat" for its whole lifetime. That
    // breaks the Sidebar "Hội thoại mới" Link (href="/chat"): navigating to the URL you're
    // already on is a no-op for Next.js, so nothing remounts and the reset effect above never
    // reruns. Once this first turn finishes, replace the URL to match the now-real
    // conversation_id so "/chat" stays free for that Link to actually navigate to.
    let newlyStartedConversationId: string | null = null;

    function ensureAssistantMessage(): void {
      if (assistantMessageStarted) {
        return;
      }
      assistantMessageStarted = true;
      setStreamingMessageId(assistantMessageId);
      updateMessages((current) => [
        ...current,
        { id: assistantMessageId, role: "assistant", content: "", citations: [] }
      ]);
    }

    try {
      await sendChatQuery(trimmed, activeConversationId, {
        onCitations: (event) => {
          setActiveConversationId(event.conversation_id);
          if (conversationId === null) {
            newlyStartedConversationId = event.conversation_id;
          }
          ensureAssistantMessage();
          updateMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId ? { ...message, citations: event.citations } : message
            )
          );
        },
        onDelta: (event) => {
          ensureAssistantMessage();
          updateMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId ? { ...message, content: message.content + event.delta } : message
            )
          );
        },
        onSuggestedFollowups: () => {
          // Not surfaced in this UI yet (no per-answer follow-up chip slot exists) - the top
          // static suggestion chips (GET /api/chat/suggestions) are unrelated and unaffected.
        }
      });
    } catch (submitError) {
      const message =
        submitError instanceof ApiError ? submitError.message : "Không thể lấy câu trả lời, vui lòng thử lại.";
      setError(message);
    } finally {
      setIsSending(false);
      setStreamingMessageId(null);
      if (newlyStartedConversationId !== null) {
        pendingFreshConversationHandoff = {
          conversationId: newlyStartedConversationId,
          messages: messagesRef.current
        };
        router.replace(`/chat/${newlyStartedConversationId}`);
      }
    }
  }

  // Copies message.content only - citations live in a separate field/UI block (CitationList),
  // never interpolated into content, so this is already "answer text without citation pill" with
  // no extra stripping needed.
  async function handleCopy(messageId: string, content: string): Promise<void> {
    await navigator.clipboard.writeText(content);
    setCopiedMessageId(messageId);
    setTimeout(() => {
      setCopiedMessageId((current) => (current === messageId ? null : current));
    }, COPY_FEEDBACK_DURATION_MS);
  }

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col px-6 py-6">
      <div className="flex-1 space-y-6 overflow-y-auto pr-1">
        {isLoadingHistory ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-muted-foreground">
            <span className="flex gap-1">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
            </span>
            <p className="text-sm">Đang tải lại hội thoại...</p>
          </div>
        ) : null}

        {!isLoadingHistory && messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Scale className="h-6 w-6" />
            </span>
            <div className="space-y-1.5">
              <p className="font-serif text-lg font-light tracking-tight text-foreground">
                Bắt đầu hỏi đáp về Luật Tố tụng Hình sự
              </p>
              <p className="max-w-md text-sm text-muted-foreground">
                Hỏi trực tiếp về 1 Điều luật, hoặc hỏi phân tích sâu, mọi câu trả lời đều có trích dẫn.
              </p>
            </div>

            {suggestions.length > 0 ? (
              <div className="flex max-w-lg flex-wrap items-center justify-center gap-2 pt-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion.id}
                    type="button"
                    onClick={() => void handleAsk(suggestion.text)}
                    className="inline-flex min-h-11 items-center justify-center rounded-full border border-border bg-secondary px-3.5 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent"
                  >
                    {suggestion.text}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {messages.map((message) =>
          message.role === "user" ? (
            <div key={message.id} className="flex justify-end">
              <div className="max-w-[75%] rounded-2xl bg-primary px-4 py-3 text-sm text-primary-foreground">
                {message.content}
              </div>
            </div>
          ) : (
            <div key={message.id} className="flex justify-start">
              <div className="w-full max-w-[85%] rounded-2xl border border-border bg-card px-4 py-4">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs font-medium text-muted-foreground">TTHS Buddy · AI</p>
                  {message.content.length > 0 ? (
                    <button
                      type="button"
                      onClick={() => void handleCopy(message.id, message.content)}
                      className="flex min-h-11 items-center gap-1 rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    >
                      {copiedMessageId === message.id ? (
                        <>
                          <Check className="h-3.5 w-3.5" />
                          Đã sao chép
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5" />
                          Sao chép
                        </>
                      )}
                    </button>
                  ) : null}
                </div>
                <FormattedAnswer text={message.content} />
                <CitationList citations={message.citations ?? []} />
              </div>
            </div>
          )
        )}

        {isSending && streamingMessageId === null ? (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
              <span className="flex gap-1">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
              </span>
              TTHS Buddy đang soạn câu trả lời...
            </div>
          </div>
        ) : null}

        {error !== null ? (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        ) : null}

        <div ref={scrollAnchorRef} />
      </div>

      {/* Once there are messages, the empty-state's centered chip block above is gone - keep
          the chips reachable here instead of only at the very start of the conversation. */}
      {suggestions.length > 0 && messages.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto pb-3 pt-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.id}
              type="button"
              onClick={() => void handleAsk(suggestion.text)}
              disabled={isSending}
              className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-full border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:opacity-50"
            >
              {suggestion.text}
            </button>
          ))}
        </div>
      ) : null}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void handleAsk(input);
        }}
        className="flex items-center gap-2 rounded-full border border-border bg-card px-2 py-2"
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Hỏi về Luật Tố tụng Hình sự..."
          className="flex-1 bg-transparent px-3 py-2 text-sm text-foreground outline-none"
          disabled={isSending}
        />
        <button
          type="submit"
          disabled={isSending || input.trim().length === 0}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-40"
        >
          <SendHorizontal className="h-4 w-4" />
        </button>
      </form>

      <p className="pt-3 text-center text-xs text-muted-foreground">
        TTHS Buddy · Chỉ dành cho mục đích học tập · Không thay thế tư vấn pháp lý chuyên nghiệp
      </p>
    </div>
  );
}
