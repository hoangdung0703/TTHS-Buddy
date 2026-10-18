"use client";

import { AlertCircle, RotateCcw, Sparkles } from "lucide-react";
import { forwardRef, useImperativeHandle, useRef, useState } from "react";

import { CitationList } from "@/components/chat/CitationList";
import { FormattedAnswer } from "@/components/chat/FormattedAnswer";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSlowRequestNotice } from "@/hooks/useSlowRequestNotice";
import { ApiError, askAboutPassage, NOTES_QUESTION_MAX_CHARS, PASSAGE_MAX_CHARS } from "@/lib/api";
import { SLOW_REQUEST_NOTICE } from "@/lib/serverWakeup";
import type { Citation } from "@/lib/types";

interface AskTurn {
  id: string;
  passage: string;
  question: string;
  answer: string;
  citations: Citation[];
  contextUnavailable: boolean;
}

export interface NotesAskPanelHandle {
  // Called by the page when the student presses "Hỏi AI về đoạn này". A new passage starts a new
  // conversation: follow-up questions are about the passage they were asked against.
  loadPassage: (passage: string) => void;
}

// How much of the passage each turn shows above its question - enough to recognise which
// selection the answer is about, not a second copy of the note.
const TURN_PASSAGE_PREVIEW_CHARS = 160;

function previewPassage(passage: string): string {
  const flat = passage.replace(/\s+/g, " ").trim();
  return flat.length > TURN_PASSAGE_PREVIEW_CHARS ? `${flat.slice(0, TURN_PASSAGE_PREVIEW_CHARS)}…` : flat;
}

function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) {
      return "Bạn đã hỏi 10 lần trong một phút. Đợi một chút rồi hỏi tiếp nhé.";
    }
    if (error.status === 422) {
      return `Đoạn chọn tối đa ${PASSAGE_MAX_CHARS.toLocaleString("vi-VN")} ký tự, câu hỏi tối đa ${NOTES_QUESTION_MAX_CHARS.toLocaleString("vi-VN")} ký tự.`;
    }
    if (error.status === 401) {
      return "Phiên đăng nhập đã hết hạn. Bạn tải lại trang và đăng nhập lại nhé.";
    }
  }
  return "Không thể lấy câu trả lời, vui lòng thử lại.";
}

let turnCounter = 0;
function createTurnId(): string {
  turnCounter += 1;
  return `ask-${Date.now()}-${turnCounter}`;
}

export const NotesAskPanel = forwardRef<NotesAskPanelHandle>(function NotesAskPanel(_, ref) {
  const [passage, setPassage] = useState("");
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<AskTurn[]>([]);
  // The turn being answered right now, rendered live as answer_delta events arrive.
  const [pendingTurn, setPendingTurn] = useState<AskTurn | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedQuestion, setLastFailedQuestion] = useState<string | null>(null);
  const slowRequest = useSlowRequestNotice();
  const panelRef = useRef<HTMLElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    loadPassage: (nextPassage: string) => {
      setPassage(nextPassage);
      setTurns([]);
      setConversationId(null);
      setError(null);
      setLastFailedQuestion(null);
      // Below lg the panel sits under the notes, so bring it into view before focusing.
      panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      questionRef.current?.focus({ preventScroll: true });
    }
  }));

  const passageLength = passage.length;
  const passageTooLong = passageLength > PASSAGE_MAX_CHARS;
  const canSend = !isSending && passage.trim().length > 0 && !passageTooLong && question.trim().length > 0;

  async function send(questionText: string): Promise<void> {
    const trimmed = questionText.trim();
    if (isSending || trimmed.length === 0 || passage.trim().length === 0 || passageTooLong) {
      return;
    }

    setIsSending(true);
    setError(null);
    setLastFailedQuestion(null);
    setStatusMessage(null);
    slowRequest.start();

    const turn: AskTurn = {
      id: createTurnId(),
      passage,
      question: trimmed,
      answer: "",
      citations: [],
      contextUnavailable: false
    };
    let answered = false;
    let failed = false;

    try {
      await askAboutPassage(passage, trimmed, conversationId, {
        onStatus: (event) => {
          slowRequest.stop();
          setStatusMessage(event.message);
        },
        onDelta: (event) => {
          slowRequest.stop();
          setStatusMessage(null);
          answered = true;
          turn.answer += event.delta;
          setPendingTurn({ ...turn });
        },
        onCitations: (event) => {
          setConversationId(event.conversation_id);
          turn.citations = event.citations;
          turn.contextUnavailable = event.context_unavailable === true;
          setPendingTurn({ ...turn });
        },
        onError: (event) => {
          failed = true;
          setError(event.message);
        }
      });
      if (answered && !failed) {
        setTurns((current) => [...current, { ...turn }]);
        setQuestion("");
      } else if (!failed) {
        failed = true;
        setError("Không nhận được câu trả lời, vui lòng thử lại.");
      }
    } catch (askError) {
      failed = true;
      setError(messageForError(askError));
    } finally {
      if (failed) {
        setLastFailedQuestion(trimmed);
      }
      setPendingTurn(null);
      setIsSending(false);
      setStatusMessage(null);
      slowRequest.stop();
    }
  }

  function handleSubmit(event: React.FormEvent): void {
    event.preventDefault();
    void send(question);
  }

  function resetConversation(): void {
    setTurns([]);
    setConversationId(null);
    setError(null);
    setLastFailedQuestion(null);
  }

  return (
    <section
      ref={panelRef}
      aria-label="Hỏi AI về đoạn ghi chú"
      data-testid="notes-ask-panel"
      className="flex min-w-0 scroll-mt-20 flex-col gap-4 rounded-xl border border-primary/[0.08] bg-card p-5 shadow-[0_2px_20px_rgba(30,36,96,0.05)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Sparkles className="h-4 w-4 shrink-0 text-accent" />
            Hỏi AI về đoạn ghi chú
          </h2>
          <p className="mt-1 text-xs font-light text-muted-foreground">
            AI giải thích, đối chiếu với điều luật và gợi ý chỗ cần sửa, không viết lại hộ bạn.
          </p>
        </div>
        {turns.length > 0 ? (
          <button
            type="button"
            onClick={resetConversation}
            disabled={isSending}
            className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent/15 hover:text-foreground disabled:opacity-50"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Hỏi lại từ đầu
          </button>
        ) : null}
      </div>

      {passage.length === 0 ? (
        <p data-testid="notes-ask-empty" className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          Bôi chọn một đoạn trong ghi chú, rồi bấm &quot;Hỏi AI về đoạn này&quot;.
        </p>
      ) : (
        <>
          {[...turns, ...(pendingTurn ? [pendingTurn] : [])].map((turn) => (
            <article key={turn.id} data-testid="notes-ask-turn" className="flex min-w-0 flex-col gap-2 border-b border-border pb-4 last:border-b-0">
              <blockquote className="break-words border-l-2 border-accent/60 pl-3 text-xs italic text-muted-foreground">
                {previewPassage(turn.passage)}
              </blockquote>
              <p className="break-words text-sm font-medium text-foreground">{turn.question}</p>
              {turn.contextUnavailable ? (
                <p data-testid="notes-context-unavailable" className="text-xs italic text-muted-foreground">
                  Các câu hỏi trước về đoạn này tạm thời không đọc được, câu trả lời có thể thiếu ngữ cảnh.
                </p>
              ) : null}
              <div className="min-w-0 break-words text-sm">
                <FormattedAnswer text={turn.answer} />
              </div>
              <CitationList citations={turn.citations} />
            </article>
          ))}

          <form onSubmit={handleSubmit} className="flex flex-col gap-2">
            <label htmlFor="notes-ask-passage" className="text-xs font-medium text-muted-foreground">
              Đoạn bạn chọn
            </label>
            <Textarea
              id="notes-ask-passage"
              data-testid="notes-ask-passage"
              value={passage}
              onChange={(event) => setPassage(event.target.value)}
              disabled={isSending || turns.length > 0}
              className="min-h-[96px] resize-y break-words text-xs leading-relaxed"
            />
            <p
              data-testid="notes-ask-counter"
              className={`text-right text-xs tabular-nums ${passageTooLong ? "font-medium text-red-600" : "text-muted-foreground"}`}
            >
              {passageLength.toLocaleString("vi-VN")}/{PASSAGE_MAX_CHARS.toLocaleString("vi-VN")} ký tự
            </p>
            {passageTooLong ? (
              <p data-testid="notes-ask-too-long" className="text-xs text-red-600">
                Đoạn chọn dài quá {PASSAGE_MAX_CHARS.toLocaleString("vi-VN")} ký tự. Hãy chọn đoạn ngắn hơn hoặc xóa bớt phần không cần hỏi.
              </p>
            ) : null}

            <label htmlFor="notes-ask-question" className="mt-1 text-xs font-medium text-muted-foreground">
              {turns.length > 0 ? "Hỏi tiếp về đoạn này" : "Câu hỏi của bạn"}
            </label>
            <Textarea
              id="notes-ask-question"
              ref={questionRef}
              data-testid="notes-ask-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void send(question);
                }
              }}
              placeholder="Ví dụ: Đoạn này mình ghi có đúng với luật không?"
              maxLength={NOTES_QUESTION_MAX_CHARS}
              disabled={isSending}
              className="min-h-[72px] resize-y"
            />
            <Button type="submit" size="sm" disabled={!canSend} className="self-end rounded-full">
              {isSending ? "Đang hỏi..." : "Hỏi AI"}
            </Button>
          </form>
        </>
      )}

      {isSending && pendingTurn === null ? (
        <div data-testid="notes-ask-status" className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
          <span className="flex gap-1">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground" />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
          </span>
          {statusMessage ?? "TTHS Buddy đang soạn câu trả lời..."}
        </div>
      ) : null}

      {isSending && slowRequest.isSlow ? (
        <p data-testid="notes-ask-slow" className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          {SLOW_REQUEST_NOTICE}
        </p>
      ) : null}

      {error !== null ? (
        <div data-testid="notes-ask-error" className="flex flex-wrap items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1 break-words">{error}</span>
          {lastFailedQuestion !== null ? (
            <Button variant="outline" size="sm" onClick={() => void send(lastFailedQuestion)} disabled={isSending}>
              Thử lại
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
});
