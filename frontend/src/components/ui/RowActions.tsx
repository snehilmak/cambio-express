import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button, type ButtonTone } from "./Button";
import styles from "./RowActions.module.css";

/** One entry in a RowActions list. ``tone`` controls both the
 *  desktop ``Button`` tone and the mobile bottom-sheet tint —
 *  ``"primary"`` for the affirmative action, ``"warning"`` for
 *  amber, ``"info"`` for purple, ``"logs"`` for orange (mirrors
 *  the inspiration palette), ``"danger"`` for destructive
 *  actions. Defaults to ``"secondary"``. */
export type RowActionTone =
  | "secondary" | "primary" | "warning" | "info" | "logs" | "danger";

export interface RowActionItem {
  label:    string;
  onClick:  () => void | Promise<void>;
  tone?:    RowActionTone;
  busy?:    boolean;
  disabled?: boolean;
  /** Hidden but kept in the list — useful when an action is
   *  conditional (e.g. "Approve" only when status=pending) but
   *  the caller wants the slot reserved for layout consistency.
   *  Defaults to false. */
  hidden?:  boolean;
}

/** Per-row action row that collapses into a bottom-sheet on
 *  narrow viewports. Use anywhere a table or list has 2+ row
 *  actions — keeps mobile UX consistent across the SPA.
 *
 *  Desktop: inline ``<Button size="sm">`` row.
 *  Mobile (≤36rem): single "Actions" button that opens a
 *  bottom sheet rendered through ``createPortal(..., document.body)``
 *  so ``position: fixed`` pins to the viewport even when the
 *  parent ``<PageShell>`` (with its ``.ds-page`` transform)
 *  would otherwise establish a containing block.
 *
 *  Optional ``label`` overrides the mobile trigger text
 *  (defaults to "Actions"). Optional ``title`` shows above
 *  the sheet — useful when the row identity isn't obvious
 *  ("Entry on May 15 09:00").
 */
export function RowActions({
  actions, label = "Actions", title, mobileTriggerTone = "secondary",
}: {
  actions: RowActionItem[];
  label?: string;
  title?: ReactNode;
  /** Tone of the mobile "Actions" trigger button. */
  mobileTriggerTone?: ButtonTone;
}) {
  const [open, setOpen] = useState(false);
  const visible = actions.filter((a) => !a.hidden);
  if (visible.length === 0) return null;

  return (
    <>
      <div className={styles.desktopRow}>
        {visible.map((a) => (
          <Button
            key={a.label}
            size="sm"
            tone={_desktopTone(a.tone)}
            busy={a.busy}
            disabled={a.disabled || a.busy}
            onClick={() => { void a.onClick(); }}
          >
            {a.label}
          </Button>
        ))}
      </div>

      <div className={styles.mobileTrigger}>
        <Button
          size="sm" tone={mobileTriggerTone}
          onClick={() => setOpen(true)}
        >
          <span className={styles.triggerIcon}>···</span>
          {" "}
          {label}
        </Button>
      </div>

      {open && createPortal(
        <div
          className={styles.sheetBackdrop}
          onClick={() => setOpen(false)}
        >
          <div
            className={styles.sheetCard}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.sheetGrip} />
            {title && (
              <div className={styles.sheetHeader}>{title}</div>
            )}
            {visible.map((a) => (
              <button
                key={a.label}
                type="button"
                className={`${styles.sheetItem} ${_sheetToneClass(a.tone)}`}
                disabled={a.disabled || a.busy}
                onClick={() => {
                  setOpen(false);
                  void a.onClick();
                }}
              >
                {a.busy ? `${a.label}…` : a.label}
              </button>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}


function _desktopTone(tone?: RowActionTone): ButtonTone {
  if (tone === "primary") return "primary";
  if (tone === "danger")  return "danger";
  // Inline buttons for warning / info / logs use the
  // ``secondary`` outline; the tint difference is mobile-only
  // (where the bottom-sheet's color-coding matters more).
  return "secondary";
}


function _sheetToneClass(tone?: RowActionTone): string {
  if (tone === "primary") return styles.sheetTone_primary;
  if (tone === "warning") return styles.sheetTone_warning;
  if (tone === "info")    return styles.sheetTone_info;
  if (tone === "logs")    return styles.sheetTone_logs;
  if (tone === "danger")  return styles.sheetTone_danger;
  return "";
}
