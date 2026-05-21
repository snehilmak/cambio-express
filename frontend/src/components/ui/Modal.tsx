import {
  useEffect, useId, useRef, type CSSProperties, type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { Button, type ButtonTone } from "./Button";

import styles from "./Modal.module.css";

/** Kit modal primitive.
 *
 *  Replaces the hand-rolled `.modalBackdrop` + `.modalCard`
 *  blocks scattered across Customers / AdminTimeClock / TVDisplay
 *  and the bare `window.confirm()` / `window.alert()` calls in
 *  the rest of the SPA.  Centralises:
 *
 *  - `createPortal` to body so `position: fixed` pins to the
 *    viewport (a `.ds-page` entry animation otherwise establishes
 *    a containing block and traps the modal inside the page flow).
 *  - `role="dialog"` + `aria-modal="true"` + `aria-labelledby`
 *    wired to the title for screen readers.
 *  - Escape-key dismissal + click-outside dismissal (both gated
 *    by `disabled` so a busy save doesn't get torn out).
 *  - Body-scroll lock while open — the page underneath shouldn't
 *    scroll when the user pulls down on the backdrop.
 *  - Focus management: focus lands on the modal card on open, the
 *    previously-focused element is restored on close.
 *  - Reduced-motion: the global `@media (prefers-reduced-motion:
 *    reduce)` rule in `src/styles.css` strips the fade-scale
 *    keyframes for users who asked for it.
 *
 *  When `open` is false the component renders nothing — the
 *  portal node + key listeners only exist while the modal is
 *  visible. */
export function Modal({
  open, onClose, title, children, actions, size = "md",
  closeOnBackdrop = true, closeOnEscape = true, disabled = false,
}: {
  open: boolean;
  /** Called when the user dismisses via Escape / backdrop click.
   *  Wrap your own close-button handler in this too. */
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Optional row of buttons rendered in a flex-end strip below
   *  the body.  Use `<Button>` from the kit so the focus ring +
   *  busy state come for free.  Pass null when the body itself
   *  is a form with its own submit row. */
  actions?: ReactNode;
  /** `sm` (24rem) for confirm dialogs, `md` (32rem) for short
   *  forms, `lg` (48rem) for long forms / tables / wizards. */
  size?: "sm" | "md" | "lg";
  /** Set false to keep the modal open when the user clicks the
   *  backdrop.  Default true. */
  closeOnBackdrop?: boolean;
  /** Set false to keep the modal open on Escape.  Default true. */
  closeOnEscape?: boolean;
  /** When true (e.g. mid-save), Escape + backdrop-click are
   *  suppressed so the user can't tear the modal out of a busy
   *  network round-trip. */
  disabled?: boolean;
}) {
  const titleId = useId();
  const cardRef = useRef<HTMLDivElement>(null);

  // Focus + body-scroll lock: open the modal → grab focus +
  // freeze body scroll; close → restore focus + unfreeze.
  // The cleanup function handles unmount-while-open too.
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    cardRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus?.();
    };
  }, [open]);

  // Escape dismissal — separate effect so toggling `closeOnEscape`
  // doesn't tear down focus / body-scroll.
  useEffect(() => {
    if (!open || !closeOnEscape) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !disabled) {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, closeOnEscape, disabled, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (!closeOnBackdrop || disabled) return;
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`${styles.card} ${sizeClass(size)}`}
      >
        <h2 id={titleId} className={styles.title}>{title}</h2>
        <div className={styles.body}>{children}</div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
    </div>,
    document.body,
  );
}

function sizeClass(size: "sm" | "md" | "lg"): string {
  if (size === "sm") return styles.sizeSm;
  if (size === "lg") return styles.sizeLg;
  return styles.sizeMd;
}


/** Confirm/Cancel dialog — the declarative replacement for
 *  `window.confirm(message)`.
 *
 *  Pattern at the call site:
 *
 *  ```tsx
 *  const [pending, setPending] = useState<Row | null>(null);
 *
 *  return (
 *    <>
 *      <Button onClick={() => setPending(row)}>Delete</Button>
 *      <ConfirmDialog
 *        open={pending != null}
 *        title="Delete row"
 *        message={`Delete "${pending?.name}"?`}
 *        confirmTone="danger"
 *        onConfirm={async () => {
 *          await api.delete(pending.id);
 *          setPending(null);
 *        }}
 *        onCancel={() => setPending(null)}
 *      />
 *    </>
 *  );
 *  ```
 *
 *  Keep the pending row in component state — it's what supplies
 *  the message + the action target.  When `pending` is null,
 *  `open` is false and the modal renders nothing. */
export function ConfirmDialog({
  open, title, message, onConfirm, onCancel, busy = false,
  confirmLabel = "Confirm", cancelLabel = "Cancel",
  confirmTone = "primary",
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  /** When true, both buttons disable + the primary shows the
   *  busy state.  Backdrop / Escape are also blocked so the
   *  user can't tear out a half-completed action. */
  busy?: boolean;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Use `danger` for destructive actions (delete, disconnect,
   *  revoke, deactivate).  Default `primary` for the typical
   *  Save/Confirm flow. */
  confirmTone?: Extract<ButtonTone, "primary" | "danger">;
}) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      disabled={busy}
      actions={
        <>
          <Button tone="secondary" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            tone={confirmTone}
            onClick={onConfirm}
            busy={busy}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p style={messageStyle}>{message}</p>
    </Modal>
  );
}

const messageStyle: CSSProperties = {
  margin: 0,
  lineHeight: 1.5,
};
