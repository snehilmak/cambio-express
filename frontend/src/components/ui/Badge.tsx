import type { CSSProperties, ReactNode } from "react";

import { toneTokens } from "./tokens";

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "error";

/** Count / status badge.  Smaller and rounder than `<Pill>`; meant
 *  to overlay on a nav item or sit next to a label as a "3 new"
 *  / "2" indicator.
 *
 *  `dot` mode renders a 6px circle with no text — for indicating
 *  "there's something new here" without a specific count.  Use
 *  it on nav items where the exact number isn't the point.
 *
 *  For richer status pills (rounded rectangles with longer text),
 *  reach for `<Pill>` instead.
 */
export function Badge({
  children, tone = "neutral", dot, style,
}: {
  children?: ReactNode;
  tone?: BadgeTone;
  /** Render a 6px dot with no children — for "has unread"
   *  indicators that don't need a number. */
  dot?: boolean;
  style?: CSSProperties;
}) {
  const palette = bgFg(tone);
  if (dot) {
    return (
      <span
        aria-hidden="true"
        style={{
          display: "inline-block",
          width: 6,
          height: 6,
          borderRadius: 999,
          background: palette.fg,
          ...style,
        }}
      />
    );
  }
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: "1.1rem",
        height: "1.1rem",
        padding: "0 0.4rem",
        borderRadius: 999,
        background: palette.bg,
        color: palette.fg,
        fontSize: "0.7rem",
        fontWeight: 600,
        lineHeight: 1,
        fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

function bgFg(tone: BadgeTone): { bg: string; fg: string } {
  if (tone === "info")    return { bg: toneTokens.info.bg,    fg: toneTokens.info.fg    };
  if (tone === "success") return { bg: toneTokens.success.bg, fg: toneTokens.success.fg };
  if (tone === "warning") return { bg: toneTokens.warning.bg, fg: toneTokens.warning.fg };
  if (tone === "error")   return { bg: toneTokens.error.bg,   fg: toneTokens.error.fg   };
  // neutral falls back to a generic muted treatment
  return { bg: "var(--db-surface-3, #1f1f1f)", fg: "var(--db-text-muted, #a3a3a3)" };
}
