"use client";

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Open layers, bottom to top. Only the top one answers Esc and Tab, so Esc in a law dialog opened
// from a drawer closes the dialog and leaves the drawer open.
const layers: object[] = [];
// Nested layers share one lock on the page behind; the first one in saves the style to put back.
let scrollLocks = 0;
let overflowBeforeLock = "";

interface ModalLayerOptions {
  open: boolean;
  // The dialog element: Tab cycles inside it.
  containerRef: RefObject<HTMLElement | null>;
  // Focused when the layer opens; the first focusable element otherwise.
  initialFocusRef?: RefObject<HTMLElement | null>;
  // The control that opened the layer, taken from the click's event.currentTarget and read once
  // when the layer opens. Never document.activeElement: Safari does not focus a button on click.
  returnFocusRef?: RefObject<HTMLElement | null>;
  onClose: () => void;
}

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => element.getClientRects().length > 0);
}

// A modal layer (dialog or drawer): locks the page scroll, moves focus in and keeps Tab inside, Esc
// closes the top layer only, and focus goes back to the opener on close (to <body> if it is gone).
export function useModalLayer({ open, containerRef, initialFocusRef, returnFocusRef, onClose }: ModalLayerOptions): void {
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const layer = {};
    layers.push(layer);
    const container = containerRef.current;
    const opener = returnFocusRef?.current ?? null;
    if (scrollLocks++ === 0) {
      overflowBeforeLock = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    (initialFocusRef?.current ?? (container !== null ? focusableIn(container)[0] : undefined))?.focus();

    // Capture phase on window: the top layer sees the key before anything inside the page.
    function handleKeyDown(event: KeyboardEvent): void {
      if (layers[layers.length - 1] !== layer) {
        return;
      }
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || container === null) {
        return;
      }
      const focusable = focusableIn(container);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !container.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !container.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown, true);

    return () => {
      window.removeEventListener("keydown", handleKeyDown, true);
      layers.splice(layers.indexOf(layer), 1);
      if (--scrollLocks === 0) {
        document.body.style.overflow = overflowBeforeLock;
      }
      // Focus already moved on purpose (e.g. "Tự soạn" focuses the composer): leave it there.
      const active = document.activeElement;
      const stranded = active === null || active === document.body || !active.isConnected || (container?.contains(active) ?? false);
      if (!stranded) {
        return;
      }
      if (opener?.isConnected) {
        // Without scrolling: closing a drawer must not move the transcript to the header button.
        opener.focus({ preventScroll: true });
      } else if (active instanceof HTMLElement && active !== document.body) {
        active.blur();
      }
    };
  }, [open, containerRef, initialFocusRef, returnFocusRef]);
}
