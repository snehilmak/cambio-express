import { tokens } from "./tokens";
import { Tooltip } from "./Tooltip";

/** Small (i) icon that reveals explanatory text on hover / focus.
 *
 *  THE standard for contextual help across the SPA: instead of a
 *  loose sentence under a box or input ("random texts across the
 *  software"), put an InfoTip beside the header or label and move
 *  the sentence into it. Keeps forms and cards visually quiet
 *  while the explanation stays one hover away — and keyboard
 *  users reach it by tabbing to the icon.
 *
 *  Composes the kit `Tooltip` in multiline mode, so sentence-
 *  length text wraps instead of stretching across the screen.
 *
 *  Usage:
 *    <span>Forward balance <InfoTip text="Auto-carried from
 *      yesterday's cash drops + safe balance." /></span>
 */
export function InfoTip({
  text, label = "More info",
}: {
  /** The explanatory sentence(s) shown in the tooltip. */
  text: string;
  /** Accessible name for the icon button. */
  label?: string;
}) {
  return (
    <Tooltip label={text} multiline placement="top" delayMs={150}>
      <button
        type="button"
        aria-label={label}
        // A button (not a bare span) so it's tabbable + announced;
        // it never submits (type="button") and never handles click —
        // hover/focus alone reveal the tip.
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          verticalAlign: "text-bottom",
          width: "1rem",
          height: "1rem",
          padding: 0,
          margin: "0 0 0 0.3rem",
          background: "none",
          border: "none",
          borderRadius: "50%",
          color: tokens.textMuted,
          cursor: "help",
        }}
      >
        <svg
          width="14" height="14" viewBox="0 0 24 24" fill="none"
          aria-hidden="true" focusable="false"
          stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="11" x2="12" y2="16" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      </button>
    </Tooltip>
  );
}
