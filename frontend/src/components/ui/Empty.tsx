import type { ReactNode } from "react";

import { fontSize, space, tokens } from "./tokens";

/** Inline "no rows" / "loading" / "error" message centered in a
 *  small block. For richer states use ``<EmptyState>`` (icon +
 *  CTA) or ``<ErrorState>`` (retry button). */
export function Empty({
  children, error,
}: {
  children: ReactNode;
  /** Renders the message in `--db-negative` for failure cases. */
  error?: boolean;
}) {
  return (
    <p
      style={{
        margin: 0,
        padding: "2rem 0",
        textAlign: "center",
        color: error ? tokens.negative : tokens.textMuted,
        fontSize: fontSize.base,
      }}
    >
      {children}
    </p>
  );
}


/** Full block empty state with icon + title + body + optional CTA.
 *  Use when the WHOLE region (a table, a card body, a tab pane)
 *  has zero content, not for inline "Loading…" messages. */
export function EmptyState({
  icon, title, body, cta,
}: {
  /** Inline SVG node (24x24 ideally). Defaults to inbox glyph. */
  icon?: ReactNode;
  title: ReactNode;
  body?: ReactNode;
  /** Right-aligned action — usually a <Button> or <Link>. */
  cta?: ReactNode;
}) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "2.5rem 1.5rem",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: space.sm,
      }}
    >
      <span
        style={{
          width: "3rem", height: "3rem",
          borderRadius: "0.75rem",
          background: "rgba(63, 255, 0, 0.08)",
          border: "1px solid rgba(63, 255, 0, 0.25)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          color: tokens.accent,
          marginBottom: space.xs,
        }}
        aria-hidden
      >
        {icon ?? <DefaultEmptyIcon />}
      </span>
      <div style={{ fontWeight: 600, fontSize: fontSize.lg }}>{title}</div>
      {body && (
        <div style={{ color: tokens.textMuted, maxWidth: "32rem" }}>
          {body}
        </div>
      )}
      {cta && <div style={{ marginTop: space.sm }}>{cta}</div>}
    </div>
  );
}

function DefaultEmptyIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22"
         stroke="currentColor" fill="none" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>
    </svg>
  );
}
