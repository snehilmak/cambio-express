import type { ReactNode } from "react";

import { tokens, toneTokens } from "./tokens";

export type PillTone =
  | "neutral" | "accent" | "negative" | "warning" | "info" | "success";

// Status pill colors.
// - `neutral` reads through `--db-fill-neutral` so it flips
//   white-on-dark ↔ black-on-light with the theme.
// - `accent` is the active / selected / "in-progress" pill, using the
//   shared `--db-neon-glow-15` so the neon tint matches the rest of
//   the SPA's active-state vocabulary.
// - `negative` / `warning` / `info` / `success` resolve to the
//   `--db-tone-*` tokens shared with Alert + ErrorState, so a "Failed"
//   pill matches the red of an error banner instead of drifting to a
//   slightly different rgba.
const pillPalette: Record<PillTone, { bg: string; fg: string }> = {
  neutral:  { bg: "var(--db-fill-neutral, rgba(255,255,255,0.06))", fg: tokens.text },
  accent:   { bg: "var(--db-neon-glow-15, rgba(63,255,0,0.15))",    fg: tokens.accent },
  negative: { bg: toneTokens.error.bg,                              fg: toneTokens.error.fg },
  warning:  { bg: toneTokens.warning.bg,                            fg: toneTokens.warning.fg },
  info:     { bg: toneTokens.info.bg,                               fg: toneTokens.info.fg },
  success:  { bg: toneTokens.success.bg,                            fg: toneTokens.success.fg },
};

/** Small rounded badge for status / category / plan tags.
 *
 *  Pass ``dot`` for status-style pills with a colored circle before
 *  the label (e.g. "● Active", "● Failed").  The dot uses the same
 *  saturated tone color as the text — no extra prop needed. */
export function Pill({
  children, tone = "neutral", mono = false, dot = false,
}: {
  children: ReactNode;
  tone?: PillTone;
  /** Use mono font (for category slugs / ref codes / etc). */
  mono?: boolean;
  /** Leading colored dot — switches the pill from a label tag to a
   *  status indicator without changing the surrounding code. */
  dot?: boolean;
}) {
  const c = pillPalette[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: dot ? "0.35rem" : 0,
        background: c.bg,
        color: c.fg,
        borderRadius: "999px",
        padding: "0.15rem 0.6rem",
        fontSize: "0.78rem",
        fontWeight: 600,
        fontFamily: mono ? tokens.fontMono : tokens.fontBody,
        lineHeight: 1.5,
        verticalAlign: "middle",
      }}
    >
      {dot && (
        <span
          aria-hidden
          style={{
            width: "0.42rem",
            height: "0.42rem",
            borderRadius: "999px",
            background: "currentColor",
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  );
}
