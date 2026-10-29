"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getTrialNotes, putTrialNotes, TrialApiError } from "@/lib/api";
import { CLERK_NOTES_DEFAULT_MAX, messageForTrialError } from "@/lib/trialRules";

// Contract 3.8 / THIET-KE 11.3.7: save once the student has stopped typing for 2 seconds.
export const NOTES_SAVE_DELAY_MS = 2000;

export type NotesSaveStatus = "idle" | "pending" | "saving" | "saved" | "error";

export interface ClerkNotes {
  // GET /notes has answered; nothing is saved before that, so an empty box never overwrites notes.
  loaded: boolean;
  loadError: string | null;
  text: string;
  setText: (value: string) => void;
  status: NotesSaveStatus;
  saveError: string | null;
  updatedAt: string | null;
  maxChars: number;
  // Abandoned session (or the server said trial_not_active): shown, never saved.
  readOnly: boolean;
  retryLoad: () => void;
  saveNow: () => void;
}

/**
 * The clerk's notes of one session, held and saved from this one place. Every editor on the page
 * (side panel, phone drawer, record screen) is a controlled view of this hook, so two copies can
 * never save over each other. The text lives in page memory and on the server only (contract
 * Mục 9.1), and is never logged or sent anywhere but PUT /notes (Mục 9.13).
 *
 * One request at a time: edits made while a save is running are sent right after it. On unmount
 * (leaving for the record screen) unsaved text is sent without waiting for the answer.
 */
export function useClerkNotes(sessionId: string, enabled: boolean, readOnlyByState: boolean): ClerkNotes {
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [text, setTextState] = useState("");
  const [status, setStatus] = useState<NotesSaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [maxChars, setMaxChars] = useState(CLERK_NOTES_DEFAULT_MAX);
  const [readOnlyByServer, setReadOnlyByServer] = useState(false);
  const readOnly = readOnlyByState || readOnlyByServer;

  const textRef = useRef("");
  // The text the server last confirmed (as sent).
  const savedRef = useRef("");
  const loadedRef = useRef(false);
  const readOnlyRef = useRef(readOnly);
  const maxRef = useRef(CLERK_NOTES_DEFAULT_MAX);
  const inFlightRef = useRef(false);
  const againRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  readOnlyRef.current = readOnly;

  const clearTimer = (): void => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const flush = useCallback(async (): Promise<void> => {
    clearTimer();
    if (!loadedRef.current || readOnlyRef.current) {
      return;
    }
    if (inFlightRef.current) {
      againRef.current = true;
      return;
    }
    const sending = textRef.current;
    if (sending === savedRef.current) {
      setStatus((current) => (current === "pending" || current === "error" ? "saved" : current));
      return;
    }
    if (sending.length > maxRef.current) {
      setStatus("error");
      setSaveError(`Ghi chép dài quá ${maxRef.current.toLocaleString("vi-VN")} ký tự nên chưa lưu được. Bạn rút gọn bớt nhé.`);
      return;
    }
    inFlightRef.current = true;
    setStatus("saving");
    setSaveError(null);
    try {
      const result = await putTrialNotes(sessionId, sending);
      savedRef.current = sending;
      if (mountedRef.current) {
        setUpdatedAt(result.updated_at);
        if (textRef.current === sending) {
          setStatus("saved");
        } else {
          againRef.current = true;
        }
      }
    } catch (error) {
      if (!mountedRef.current || (error instanceof TrialApiError && error.featureDisabled)) {
        return;
      }
      setStatus("error");
      if (error instanceof TrialApiError && error.code === "trial_not_active") {
        setReadOnlyByServer(true);
        setSaveError("Phiên tòa đã bị bỏ nên ghi chép chỉ còn xem được, không lưu thêm.");
      } else if (error instanceof TrialApiError && error.status === 422) {
        setSaveError(`Ghi chép dài quá ${maxRef.current.toLocaleString("vi-VN")} ký tự nên chưa lưu được. Bạn rút gọn bớt nhé.`);
      } else {
        setSaveError(error instanceof TrialApiError ? messageForTrialError(error) : "Mất kết nối nên chưa lưu được ghi chép.");
      }
    } finally {
      inFlightRef.current = false;
      if (againRef.current && mountedRef.current) {
        againRef.current = false;
        void flush();
      }
    }
  }, [sessionId]);

  const load = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const result = await getTrialNotes(sessionId);
      if (!mountedRef.current) {
        return;
      }
      textRef.current = result.notes;
      savedRef.current = result.notes;
      maxRef.current = result.max_chars > 0 ? result.max_chars : CLERK_NOTES_DEFAULT_MAX;
      loadedRef.current = true;
      setTextState(result.notes);
      setUpdatedAt(result.updated_at);
      setMaxChars(maxRef.current);
      setStatus(result.updated_at ? "saved" : "idle");
      setLoaded(true);
    } catch (error) {
      if (!mountedRef.current || (error instanceof TrialApiError && error.featureDisabled)) {
        return;
      }
      setLoadError(error instanceof TrialApiError ? messageForTrialError(error) : "Không tải được ghi chép. Kiểm tra kết nối rồi thử lại.");
    }
  }, [sessionId]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) {
      void load();
    }
    return () => {
      mountedRef.current = false;
      clearTimer();
      // Leaving the page with unsaved notes: send them, without waiting for the answer.
      if (loadedRef.current && !readOnlyRef.current && textRef.current !== savedRef.current && textRef.current.length <= maxRef.current) {
        void putTrialNotes(sessionId, textRef.current).catch(() => undefined);
      }
    };
  }, [enabled, load, sessionId]);

  // A reload or tab close with unsaved notes asks first.
  useEffect(() => {
    if (!enabled) {
      return;
    }
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      if (loadedRef.current && !readOnlyRef.current && (textRef.current !== savedRef.current || inFlightRef.current)) {
        event.preventDefault();
      }
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [enabled]);

  const setText = useCallback(
    (value: string): void => {
      if (!loadedRef.current || readOnlyRef.current) {
        return;
      }
      textRef.current = value;
      setTextState(value);
      clearTimer();
      if (value === savedRef.current && !inFlightRef.current) {
        setStatus("saved");
        return;
      }
      setStatus((current) => (current === "saving" ? current : "pending"));
      timerRef.current = setTimeout(() => void flush(), NOTES_SAVE_DELAY_MS);
    },
    [flush]
  );

  return {
    loaded,
    loadError,
    text,
    setText,
    status,
    saveError,
    updatedAt,
    maxChars,
    readOnly,
    retryLoad: () => void load(),
    saveNow: () => void flush()
  };
}
