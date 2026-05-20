import type { ReactNode } from "react";

import { Button } from "./Button";
import { fontSize, space, toneTokens } from "./tokens";

/** Fetch / mutation error block with optional retry button.
 *  Use INSTEAD OF ``<Empty error>`` when there's a recoverable
 *  failure (user can retry). For permanent errors (404, 403)
 *  use ``<EmptyState>`` with a redirect CTA.
 *
 *  Visually a kissing cousin of ``<Alert tone="error">`` — same
 *  tone tokens, same leading glyph — with a wider footprint + a
 *  right-aligned retry CTA. */
export function ErrorState({
  message, onRetry, busy,
}: {
  message: ReactNode;
  onRetry?: () => void;
  busy?: boolean;
}) {
  const c = toneTokens.error;
  return (
    <div
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: "0.55rem",
        padding: `${space.md} ${space.lg}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: space.md,
        color: c.fg,
        flexWrap: "wrap",
      }}
      role="alert"
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.55rem",
          fontSize: fontSize.base,
          lineHeight: 1.4,
          minWidth: 0,
        }}
      >
        <ErrorIcon />
        <span>{message}</span>
      </div>
      {onRetry && (
        <Button tone="danger" busy={busy} onClick={onRetry}>
          {busy ? "Retrying…" : "Retry"}
        </Button>
      )}
    </div>
  );
}


function ErrorIcon() {
  return (
    <svg
      width={18} height={18} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden
      style={{ flexShrink: 0 }}
    >
      <circle cx={12} cy={12} r={10} />
      <line x1={12} y1={8}  x2={12} y2={12} />
      <line x1={12} y1={16} x2={12.01} y2={16} />
    </svg>
  );
}
