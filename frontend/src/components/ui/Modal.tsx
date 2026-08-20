import { type CSSProperties, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";

import { Button, type ButtonTone } from "./Button";

import styles from "./Modal.module.css";

/** Kit modal primitive — Radix Dialog under the hood, same API.
 *
 *  Replaces the hand-rolled `.modalBackdrop` + `.modalCard`
 *  blocks scattered across Customers / AdminTimeClock / TVDisplay
 *  and the bare `window.confirm()` / `window.alert()` calls in
 *  the rest of the SPA.  Radix supplies the hard parts we used to
 *  hand-roll (and the one we never had):
 *
 *  - Portal to body so `position: fixed` pins to the viewport
 *    (a `.ds-page` entry animation otherwise establishes a
 *    containing block and traps the modal inside the page flow).
 *  - `role="dialog"` + `aria-modal="true"` + `aria-labelledby`
 *    wired to the title for screen readers.
 *  - A REAL focus trap: Tab / Shift-Tab cycle inside the dialog
 *    instead of escaping into the page behind it. Focus lands in
 *    the card on open and returns to the trigger on close.
 *  - Escape-key + click-outside dismissal (both gated by
 *    `disabled` so a busy save doesn't get torn out).
 *  - Body-scroll lock while open.
 *  - Reduced-motion: the global `@media (prefers-reduced-motion:
 *    reduce)` rule in `src/styles.css` strips the fade-scale
 *    keyframes for users who asked for it.
 *
 *  The Content nests inside the Overlay (the Radix "scrollable
 *  overlay" pattern) so the existing flex-centering CSS keeps
 *  working unchanged.
 *
 *  When `open` is false the component renders nothing. */
export function Modal({
  open, onClose, title, children, actions, size = "md",
  closeOnBackdrop = true, closeOnEscape = true, disabled = false,
}: {
  open: boolean;
  /** Called when the user dismisses via Escape / backdrop click.
   *  Wrap your own close-button handler in this too. */
  onClose: () => void;
  /** Heading text — a ReactNode so callers can append an
   *  `<InfoTip>` per the contextual-help standard. */
  title: ReactNode;
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
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next && !disabled) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className={styles.backdrop}>
          <Dialog.Content
            className={`${styles.card} ${sizeClass(size)}`}
            // The body is free-form content, not a single
            // description — suppress Radix's aria-describedby
            // wiring (and its dev warning) explicitly.
            aria-describedby={undefined}
            onEscapeKeyDown={(e) => {
              if (!closeOnEscape || disabled) e.preventDefault();
            }}
            onPointerDownOutside={(e) => {
              if (!closeOnBackdrop || disabled) e.preventDefault();
            }}
            onInteractOutside={(e) => {
              if (!closeOnBackdrop || disabled) e.preventDefault();
            }}
          >
            <Dialog.Title asChild>
              <h2 className={styles.title}>{title}</h2>
            </Dialog.Title>
            <div className={styles.body}>{children}</div>
            {actions && <div className={styles.actions}>{actions}</div>}
          </Dialog.Content>
        </Dialog.Overlay>
      </Dialog.Portal>
    </Dialog.Root>
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
