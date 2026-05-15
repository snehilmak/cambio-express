import type { ReactNode } from "react";

import { tokens } from "./tokens";

export type PillTone =
  | "neutral" | "accent" | "negative" | "warning" | "info";

const pillPalette: Record<PillTone, { bg: string; fg: string }> = {
  neutral:  { bg: "rgba(255,255,255,0.06)",         fg: tokens.text },
  accent:   { bg: "rgba(63,255,0,0.15)",            fg: tokens.accent },
  negative: { bg: "rgba(255,59,48,0.15)",           fg: tokens.negative },
  warning:  { bg: "rgba(255,184,0,0.15)",           fg: tokens.warning },
  info:     { bg: "rgba(99,166,255,0.15)",          fg: "#63a6ff" },
};

/** Small rounded badge for status / category / plan tags. */
export function Pill({
  children, tone = "neutral", mono = false,
}: {
  children: ReactNode;
  tone?: PillTone;
  /** Use mono font (for category slugs / ref codes / etc). */
  mono?: boolean;
}) {
  const c = pillPalette[tone];
  return (
    <span
      style={{
        display: "inline-block",
        background: c.bg,
        color: c.fg,
        borderRadius: "999px",
        padding: "0.15rem 0.55rem",
        fontSize: "0.78rem",
        fontWeight: 600,
        fontFamily: mono ? tokens.fontMono : tokens.fontBody,
      }}
    >
      {children}
    </span>
  );
}
