"use client";

import { AlertCircle, Scale, SendHorizontal } from "lucide-react";
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

function createMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

interface ChatViewProps {
  // The conversation_id segment from the URL (/chat/[conversationId]), or null on the bare
  // /chat route - null means "start a brand new conversation", matching the pre-existing
  // "Hoi thoai moi" behavior exactly (see requirements.md Phase 4 Extension 2).
  conversationId: string | null;
}

export function ChatView({ conversationId }: ChatViewProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<ChatSuggestion[]>([]);
  const [input, setInput] = useState<string>("");
  const [isSending, setIsSending] = useState<boolean>(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(conversationId !== null);
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
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void getChatSuggestions().then(setSuggestions);
  }, []);

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

    setError(null);
    setInput("");
    setMessages((current) => [...current, { id: createMessageId(), role: "user", content: trimmed }]);
    setIsSending(true);

    const assistantMessageId = createMessageId();
    let assistantMessageStarted = false;

    function ensureAssistantMessage(): void {
      if (assistantMessageStarted) {
        return;
      }
      assistantMessageStarted = true;
      setStreamingMessageId(assistantMessageId);
      setMessages((current) => [
        ...current,
        { id: assistantMessageId, role: "assistant", content: "", citations: [] }
      ]);
    }

    try {
      await sendChatQuery(trimmed, activeConversationId, {
        onCitations: (event) => {
          setActiveConversationId(event.conversation_id);
          ensureAssistantMessage();
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantMessageId ? { ...message, citations: event.citations } : message
            )
          );
        },
        onDelta: (event) => {
          ensureAssistantMessage();
          setMessages((current) =>
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
    }
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
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-center text-muted-foreground">
            <Scale className="h-8 w-8" />
            <p className="text-sm">Đặt câu hỏi về Luật Tố tụng Hình sự để bắt đầu.</p>
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
                <p className="mb-2 text-xs font-medium text-muted-foreground">TTHS Buddy · AI</p>
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

      {suggestions.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto pb-3 pt-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.id}
              type="button"
              onClick={() => void handleAsk(suggestion.text)}
              disabled={isSending}
              className="shrink-0 rounded-full border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent disabled:opacity-50"
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
          className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-40"
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
