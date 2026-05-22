import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type CSSProperties, type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { toneTokens } from "./tokens";

// ── Public types ─────────────────────────────────────────────

export type ToastTone = "success" | "info" | "warning" | "error";

export interface ToastInput {
  message: ReactNode;
  /** Visual treatment — defaults to "success" since the most
   *  common use is "Saved." / "Copied." confirmations. */
  tone?: ToastTone;
  /** Auto-dismiss delay in ms.  Default 3500.  Pass 0 to make
   *  the toast sticky until manually dismissed. */
  duration?: number;
}

interface ToastRecord extends ToastInput {
  id: number;
}

// ── Context ──────────────────────────────────────────────────

interface ToastContextValue {
  push: (input: ToastInput) => void;
}

// Throw-on-missing-provider is the cleanest way to surface
// "you forgot to mount <ToastProvider>" at the call site.
const ToastContext = createContext<ToastContextValue | null>(null);

/** Push a toast.  Must be called from inside a `<ToastProvider>`.
 *
 *  ```tsx
 *  const toast = useToast();
 *  // ...
 *  await api.save();
 *  toast({ message: "Profile saved.", tone: "success" });
 *  ```
 */
// eslint-disable-next-line react-refresh/only-export-components -- hook + provider are a tight unit, splitting them across files makes the public surface awkward; fast-refresh skip is acceptable for this single file
export function useToast(): (input: ToastInput) => void {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error(
      "useToast() requires <ToastProvider> in the tree.  Mount it once "
      + "near the app root (typically inside <RequireAuth> in App.tsx).",
    );
  }
  return ctx.push;
}

// ── Provider ─────────────────────────────────────────────────

/** Mount once near the app root.  Owns the queue + renders the
 *  toast region (top-right of the viewport, via createPortal so
 *  it floats above modals + the slim sidebar). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastRecord[]>([]);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((input: ToastInput) => {
    // Monotonic-ish id — sufficient for keys, not crypto.
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setItems((prev) => [...prev, { ...input, id }]);
  }, []);

  // One context value, stable across renders.  Memoise to avoid
  // every consumer re-rendering on every toast push.
  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext value={value}>
      {children}
      {typeof document !== "undefined" && createPortal(
        <div
          role="region"
          aria-label="Notifications"
          style={regionStyle}
        >
          {items.map((t) => (
            <ToastItem key={t.id} record={t} onDismiss={dismiss} />
          ))}
        </div>,
        document.body,
      )}
    </ToastContext>
  );
}

function ToastItem({
  record, onDismiss,
}: {
  record: ToastRecord;
  onDismiss: (id: number) => void;
}) {
  const duration = record.duration ?? 3500;

  // Auto-dismiss timer.  duration:0 means sticky.
  useEffect(() => {
    if (duration === 0) return;
    const t = setTimeout(() => onDismiss(record.id), duration);
    return () => clearTimeout(t);
  }, [duration, record.id, onDismiss]);

  const tone = record.tone ?? "success";
  const palette = toneTokens[tone];

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        ...itemStyle,
        background: palette.bg,
        border: `1px solid ${palette.border}`,
        color: palette.fg,
      }}
    >
      <span style={{ flex: 1 }}>{record.message}</span>
      <button
        type="button"
        onClick={() => onDismiss(record.id)}
        aria-label="Dismiss"
        style={dismissBtnStyle}
      >
        ×
      </button>
    </div>
  );
}

const regionStyle: CSSProperties = {
  position: "fixed",
  top: "1rem",
  right: "1rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
  zIndex: 300,
  pointerEvents: "none",
  // Pin width so long messages wrap nicely on the right edge.
  maxWidth: "min(22rem, calc(100vw - 2rem))",
};

const itemStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: "0.6rem",
  padding: "0.7rem 0.85rem",
  borderRadius: "0.55rem",
  fontSize: "0.9rem",
  lineHeight: 1.4,
  boxShadow: "0 12px 32px rgba(0, 0, 0, 0.4)",
  // Re-enable pointer events on each item — the region itself
  // is pointer-events:none so toasts don't block clicks behind
  // them, but each toast needs to receive its own dismiss click.
  pointerEvents: "auto",
};

const dismissBtnStyle: CSSProperties = {
  appearance: "none",
  background: "transparent",
  border: "none",
  color: "inherit",
  cursor: "pointer",
  fontSize: "1.1rem",
  lineHeight: 1,
  padding: "0 0.15rem",
  opacity: 0.7,
};
