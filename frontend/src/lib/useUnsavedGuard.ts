import { useCallback, useState } from "react";

import { useUnsavedChangesGuard } from "./useUnsavedChangesGuard";

// Standard unsaved-changes guard for edit forms.
//
// Composes the two layers a form needs to protect in-flight edits:
//   1. `beforeunload` — the browser's native "Leave site?" prompt on
//      tab close / refresh / external navigation (via
//      useUnsavedChangesGuard).
//   2. In-app leave confirm — a <ConfirmDialog> shown when the user
//      hits the form's own Cancel / Back control while dirty.
//
// Before this hook, layer 2 was hand-rolled identically in
// ReturnCheckForm / EditTransfer / EditDailyBook (a `pendingLeave`
// state + a duplicated ConfirmDialog + an onCancel that branched on
// dirtiness). This centralises it so every form guards leaves the
// same way.
//
// Usage:
//   const guard = useUnsavedGuard(isDirty);
//   // Cancel / Back handler — runs `proceed` now if clean, else prompts:
//   <Button onClick={() => guard.confirmLeave(() => navigate("/x"))}/>
//   // Render the shared discard prompt (never opens unless confirmLeave
//   // was called while dirty):
//   <ConfirmDialog {...guard.dialogProps} />
//
// Note on scope (inherited from useUnsavedChangesGuard): this app uses
// react-router's declarative <BrowserRouter>, so sidebar-link
// navigations aren't intercepted — guard the form's explicit leave
// controls with `confirmLeave` and rely on `beforeunload` for hard
// navigations.

export interface UnsavedGuardDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  confirmTone: "danger";
  onConfirm: () => void;
  onCancel: () => void;
}

export interface UnsavedGuard {
  /** Run `proceed` immediately when the form is clean; otherwise stage
   *  the discard confirm and run `proceed` only if the user confirms. */
  confirmLeave: (proceed: () => void) => void;
  /** Spread onto the kit <ConfirmDialog>. */
  dialogProps: UnsavedGuardDialogProps;
}

export function useUnsavedGuard(
  dirty: boolean,
  opts: { title?: string; message?: string } = {},
): UnsavedGuard {
  // Layer 1: browser-native prompt on hard navigations.
  useUnsavedChangesGuard(dirty);

  // Layer 2: staged in-app leave. `pending` holds the deferred
  // navigation; storing a function in state needs the updater form so
  // React doesn't call it as a reducer.
  const [pending, setPending] = useState<{ proceed: () => void } | null>(null);

  const confirmLeave = useCallback(
    (proceed: () => void) => {
      if (dirty) setPending({ proceed });
      else proceed();
    },
    [dirty],
  );

  return {
    confirmLeave,
    dialogProps: {
      open: pending !== null,
      title: opts.title ?? "Discard unsaved changes?",
      message:
        opts.message ??
        "You have unsaved edits on this page. Leave without saving?",
      confirmLabel: "Leave",
      cancelLabel: "Keep editing",
      confirmTone: "danger",
      onConfirm: () => {
        pending?.proceed();
        setPending(null);
      },
      onCancel: () => setPending(null),
    },
  };
}
