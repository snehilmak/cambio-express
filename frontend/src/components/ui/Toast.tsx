import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { toneTokens } from "./tokens";
import styles from "./Toast.module.css";

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
  /** Toggles to "exit" once the auto-dismiss / click-dismiss
   *  fires.  CSS animates the slide-out, then `onDismiss` runs
   *  on `animationend` to actually remove the row.  Without this
   *  two-phase pattern the toast just pops out instantly. */
  state: "enter" | "exit";
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
 *  toast region (bottom-right of the viewport, via createPortal
 *  so it floats above modals + the slim sidebar).
 *
 *  Visual language follows shadcn/sonner: solid dark card with
 *  a tone-colored left border, slide-in from the right, stack
 *  up from the bottom.  Toasts dismiss via auto-timer or the ×
 *  button; both trigger an exit animation before the row drops
 *  from the queue. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastRecord[]>([]);

  // Two-phase dismiss: flip to "exit" so CSS runs the slide-out
  // animation, then drop the row from state when the animation
  // finishes.
  const startDismiss = useCallback((id: number) => {
    setItems((prev) => prev.map(
      (t) => (t.id === id ? { ...t, state: "exit" } : t),
    ));
  }, []);

  const finalize = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((input: ToastInput) => {
    // Monotonic-ish id — sufficient for keys, not crypto.
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setItems((prev) => [...prev, { ...input, id, state: "enter" }]);
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
          className={styles.region}
        >
          {items.map((t) => (
            <ToastItem
              key={t.id}
              record={t}
              onStartDismiss={startDismiss}
              onFinalize={finalize}
            />
          ))}
        </div>,
        document.body,
      )}
    </ToastContext>
  );
}

function ToastItem({
  record, onStartDismiss, onFinalize,
}: {
  record: ToastRecord;
  onStartDismiss: (id: number) => void;
  onFinalize: (id: number) => void;
}) {
  const duration = record.duration ?? 3500;

  // Auto-dismiss timer.  duration:0 means sticky.
  // Only runs while the toast is in its "enter" state; once a
  // manual dismiss flips it to "exit", the exit-finalize effect
  // below removes the row.
  useEffect(() => {
    if (duration === 0 || record.state !== "enter") return;
    const t = setTimeout(() => onStartDismiss(record.id), duration);
    return () => clearTimeout(t);
  }, [duration, record.id, record.state, onStartDismiss]);

  // Exit-phase finalize.  Once `state === "exit"`, schedule the
  // actual queue-removal to match the CSS slide-out animation
  // (180ms in Toast.module.css).  Pure-setTimeout source of
  // truth — animationend doesn't fire in jsdom (tests would
  // stall) and gets suppressed under `prefers-reduced-motion`.
  useEffect(() => {
    if (record.state !== "exit") return;
    const t = setTimeout(() => onFinalize(record.id), 200);
    return () => clearTimeout(t);
  }, [record.state, record.id, onFinalize]);

  const tone = record.tone ?? "success";
  const palette = toneTokens[tone];

  return (
    <div
      role={tone === "error" || tone === "warning" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      className={`${styles.item} ${record.state === "exit" ? styles.exit : styles.enter}`}
      style={{
        // Tone shown ONLY via the left accent + the icon.  The
        // surface stays solid neutral so contrast against the
        // page chrome is reliable.
        ["--toast-accent" as string]: palette.fg,
      }}
    >
      <ToneIcon tone={tone} />
      <span className={styles.message}>{record.message}</span>
      <button
        type="button"
        onClick={() => onStartDismiss(record.id)}
        aria-label="Dismiss"
        className={styles.dismissBtn}
      >
        ×
      </button>
    </div>
  );
}

/** Tone glyph — small inline SVG matching the design system
 *  (stroke-width 2, currentColor, no fill).  Drawn in the
 *  tone's accent color via the parent's `--toast-accent` CSS
 *  custom prop so the surface itself stays neutral. */
function ToneIcon({ tone }: { tone: ToastTone }) {
  const common = {
    width: 18, height: 18, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", strokeWidth: 2,
    strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
    "aria-hidden": true, className: styles.toneIcon,
  };
  if (tone === "success") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="10" />
        <polyline points="8 12 11 15 16 9" />
      </svg>
    );
  }
  if (tone === "warning") {
    return (
      <svg {...common}>
        <path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    );
  }
  if (tone === "error") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="10" />
        <line x1="15" y1="9" x2="9" y2="15" />
        <line x1="9" y1="9" x2="15" y2="15" />
      </svg>
    );
  }
  // info
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}
