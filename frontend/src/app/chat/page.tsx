"use client";

import { AlertCircle, Scale, SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { CitationList } from "@/components/chat/CitationList";
import { FormattedAnswer } from "@/components/chat/FormattedAnswer";
import { ApiError, getChatSuggestions, sendChatQuery } from "@/lib/api";
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

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<ChatSuggestion[]>([]);
  const [input, setInput] = useState<string>("");
  const [isSending, setIsSending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void getChatSuggestions().then(setSuggestions);
  }, []);

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

    try {
      const response = await sendChatQuery(trimmed);
      setMessages((current) => [
        ...current,
        { id: createMessageId(), role: "assistant", content: response.answer, citations: response.citations }
      ]);
    } catch (submitError) {
      const message =
        submitError instanceof ApiError ? submitError.message : "Không thể lấy câu trả lời, vui lòng thử lại.";
      setError(message);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <AuthenticatedLayout title="Trợ lý AI">
      <div className="mx-auto flex h-full max-w-4xl flex-col px-6 py-6">
        <div className="flex-1 space-y-6 overflow-y-auto pr-1">
          {messages.length === 0 ? (
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

          {isSending ? (
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
    </AuthenticatedLayout>
  );
}
