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
  negative:       "var(--db-negative, #ff4d6d)",
  warning:        "var(--db-warning, #ffb020)",
  info:           "var(--db-info, #5ea9ff)",
  positive:       "var(--db-positive, #3fff00)",
  fontDisplay:    "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontBody:       "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontMono:       "var(--db-font-mono, 'JetBrains Mono', monospace)",
} as const;

// Tone palette — shared by Alert, ErrorState, Pill, Field error
// surfaces.  Each tone resolves to three layered colors (background
// tint + border + foreground saturation) defined in
// `static/design-tokens.css`.  Adding a new tone means adding the
// three `--db-tone-<name>-{bg,border,fg}` tokens there + extending
// this map.
export const toneTokens = {
  error: {
    bg:     "var(--db-tone-error-bg, rgba(255,77,109,0.08))",
    border: "var(--db-tone-error-border, rgba(255,77,109,0.32))",
    fg:     "var(--db-tone-error-fg, #ff4d6d)",
  },
  warning: {
    bg:     "var(--db-tone-warning-bg, rgba(255,176,32,0.08))",
    border: "var(--db-tone-warning-border, rgba(255,176,32,0.32))",
    fg:     "var(--db-tone-warning-fg, #ffb020)",
  },
  success: {
    bg:     "var(--db-tone-success-bg, rgba(63,255,0,0.08))",
    border: "var(--db-tone-success-border, rgba(63,255,0,0.32))",
    fg:     "var(--db-tone-success-fg, #3fff00)",
  },
  info: {
    bg:     "var(--db-tone-info-bg, rgba(94,169,255,0.08))",
    border: "var(--db-tone-info-border, rgba(94,169,255,0.32))",
    fg:     "var(--db-tone-info-fg, #5ea9ff)",
  },
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
  // Slightly more vertical breathing room. Pre: 0.55rem felt
  // cramped especially next to the heavier <Button> primitive
  // (which has minHeight 2.4rem). Post: inputs match button
  // visual weight in toolbars + forms.
  borderRadius: "0.55rem",
  padding: "0.65rem 0.85rem",
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
  // More vertical padding so header rows don't sit right on top
  // of the first data row, and there's enough room for the bold
  // weight to breathe.
  padding: "0.75rem 0.9rem",
  borderBottom: `1px solid ${tokens.border}`,
  fontSize: fontSize.xs,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: tokens.textMuted,
  fontWeight: 600,
  background: tokens.surface,
  position: "sticky",
  top: 0,
};

export const tdStyle: CSSProperties = {
  padding: "0.7rem 0.9rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
  fontSize: fontSize.sm,
};
