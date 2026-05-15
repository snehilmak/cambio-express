import type { CSSProperties, ReactNode } from "react";

import { fontSize, space, tokens } from "./tokens";

/** Inline "Loading…" with optional label. For full-region
 *  loading states use ``<TableSkeleton>``. */
export function Loading({
  label = "Loading…", style,
}: {
  label?: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <p
      style={{
        margin: 0,
        padding: `${space.md} 0`,
        color: tokens.textMuted,
        fontSize: fontSize.base,
        display: "flex",
        alignItems: "center",
        gap: space.sm,
        ...style,
      }}
      aria-live="polite"
    >
      <Spinner />
      {label}
    </p>
  );
}

function Spinner() {
  return (
    <svg width="14" height="14" viewBox="0 0 50 50"
         style={{ animation: "ds-spin 0.9s linear infinite" }}
         aria-hidden>
      <style>{`@keyframes ds-spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="25" cy="25" r="20"
              stroke="currentColor" fill="none"
              strokeWidth="4" strokeLinecap="round"
              strokeDasharray="80 200" />
    </svg>
  );
}
