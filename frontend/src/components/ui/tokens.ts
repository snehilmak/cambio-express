// Design-system tokens — colors, spacing, type, mono helpers.
//
// Kept in a separate file from the component module so Vite's fast
// refresh can hot-reload the components in `./index.tsx` without
// being blocked by the non-component exports.
//
// Add to this file when introducing a new design token (a value
// that's referenced from more than one component), or when you'd
// otherwise be tempted to inline a hex / px / rem value in a
// route file.

import type { CSSProperties } from "react";

// ── Color + font tokens (resolve to the --db-* CSS vars set in
//    static/design-tokens.css). Fallbacks for if those vars are
//    ever stripped. ────────────────────────────────────────────

export const tokens = {
  surface:        "var(--db-surface, #0a0a0a)",
  surface2:       "var(--db-surface-2, #141414)",
  surface3:       "var(--db-surface-3, #1f1f1f)",
  border:         "var(--db-border, #262626)",
  borderSubtle:   "var(--db-border-subtle, #1f1f1f)",
  text:           "var(--db-text, #f5f5f5)",
  textMuted:      "var(--db-text-muted, #a3a3a3)",
  accent:         "var(--db-accent, #3fff00)",
  onAccent:       "var(--db-on-accent, #0a0a0a)",
  negative:       "var(--db-negative, #ff3b30)",
  warning:        "#ffb800",
  fontDisplay:    "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontBody:       "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontMono:       "var(--db-font-mono, 'JetBrains Mono', monospace)",
} as const;

export const monoStyle: CSSProperties = { fontFamily: tokens.fontMono };

// ── Spacing scale (4 / 8 / 12 / 16 / 24 / 32 / 48 rem-based) ─

export const space = {
  xs:    "0.25rem",
  sm:    "0.5rem",
  md:    "0.75rem",
  lg:    "1rem",
  xl:    "1.5rem",
  "2xl": "2rem",
  "3xl": "3rem",
} as const;

// ── Type scale ──────────────────────────────────────────────

export const fontSize = {
  xs:    "0.72rem",
  sm:    "0.82rem",
  base:  "0.95rem",
  lg:    "1.05rem",
  xl:    "1.25rem",
  "2xl": "1.5rem",
  "3xl": "2rem",
} as const;

// ── Input style block — shared by Input/Select/Textarea so
//    `style={inputStyle}` still works for anyone importing it
//    directly (e.g. legacy code we haven't migrated). ─────────

export const inputStyle: CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: tokens.text,
  fontFamily: tokens.fontBody,
  fontSize: fontSize.base,
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

// ── Table cell styles ───────────────────────────────────────

export const thStyle: CSSProperties = {
  textAlign: "left",
  padding: `${space.sm} ${space.md}`,
  borderBottom: `1px solid ${tokens.border}`,
  fontSize: fontSize.xs,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: tokens.textMuted,
  fontWeight: 500,
};

export const tdStyle: CSSProperties = {
  padding: `${space.sm} ${space.md}`,
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};
