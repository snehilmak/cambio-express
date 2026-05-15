import type { ReactNode } from "react";

import { Button } from "./Button";
import { fontSize, space, tokens } from "./tokens";

/** Fetch / mutation error block with optional retry button.
 *  Use INSTEAD OF ``<Empty error>`` when there's a recoverable
 *  failure (user can retry). For permanent errors (404, 403)
 *  use ``<EmptyState>`` with a redirect CTA. */
export function ErrorState({
  message, onRetry, busy,
}: {
  message: ReactNode;
  onRetry?: () => void;
  busy?: boolean;
}) {
  return (
    <div
      style={{
        background: "rgba(255, 59, 48, 0.08)",
        border: "1px solid rgba(255, 59, 48, 0.4)",
        borderRadius: "0.5rem",
        padding: `${space.md} ${space.lg}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: space.md,
        color: tokens.negative,
        flexWrap: "wrap",
      }}
      role="alert"
    >
      <div style={{ fontSize: fontSize.base }}>{message}</div>
      {onRetry && (
        <Button tone="danger" busy={busy} onClick={onRetry}>
          {busy ? "Retrying…" : "Retry"}
        </Button>
      )}
    </div>
  );
}
