import type { CSSProperties } from "react";

import { tokens } from "./tokens";

/** Circular initial / image badge.  Used in the topbar user menu,
 *  team-member rows, audit-log "actor" columns.
 *
 *  Initials are derived from `name` (first character, uppercased)
 *  if no `src` is provided.  Pass `aria-label={fullName}` for
 *  screen reader context — the initial itself is `aria-hidden`.
 *
 *  Sizes: `sm` (1.5rem, inline-with-text), `md` (2rem, default),
 *  `lg` (2.75rem, profile cards).
 */
export function Avatar({
  name = "", src, size = "md", "aria-label": ariaLabel, style,
}: {
  name?: string;
  src?: string;
  size?: "sm" | "md" | "lg";
  "aria-label"?: string;
  style?: CSSProperties;
}) {
  const initial = (name[0] || "·").toUpperCase();
  const dim = sizeRem(size);
  const fontSize = fontRem(size);
  return (
    <span
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: dim,
        height: dim,
        borderRadius: 999,
        background: src
          ? `center / cover no-repeat url(${JSON.stringify(src)})`
          : `linear-gradient(135deg, ${tokens.accent}, var(--db-neon-dim, #2fcc00))`,
        color: src ? undefined : "var(--db-on-accent, #0a0a0a)",
        fontFamily: tokens.fontDisplay,
        fontWeight: 700,
        fontSize,
        lineHeight: 1,
        flexShrink: 0,
        ...style,
      }}
    >
      {!src && (
        <span aria-hidden="true">{initial}</span>
      )}
    </span>
  );
}

function sizeRem(size: "sm" | "md" | "lg"): string {
  if (size === "sm") return "1.5rem";
  if (size === "lg") return "2.75rem";
  return "2rem";
}

function fontRem(size: "sm" | "md" | "lg"): string {
  if (size === "sm") return "0.7rem";
  if (size === "lg") return "1.15rem";
  return "0.85rem";
}
