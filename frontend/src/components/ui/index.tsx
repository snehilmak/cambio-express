// Shared design-system primitives used across every authed page.
//
// Why these exist
// ---------------
// Every route file was redeclaring `cardStyle`, `inputStyle`,
// `pageStyle`, `pagerBtn`, etc. — about 200 lines of token
// boilerplate per route. That made changes to the design system
// (e.g. tweaking the card border radius or pill colors) require
// touching every file. These primitives consolidate the patterns
// so each route file is mostly app logic, not styling.
//
// Add to this module rather than re-implementing locally.
// Categories of primitives:
//   <PageShell>   — outer main element with consistent padding +
//                   max-width + flex column.
//   <PageHeader>  — title + optional subtitle + slot for actions.
//   <Card>        — surface-2 panel with border + radius + padding.
//   <SectionTitle>— h2 with the Space Grotesk display family.
//   <Field>       — label + children stacked, with optional
//                   highlight on validation error.
//   <Input>       — text input with the standard token styling.
//   <Empty>       — "no rows" / "loading" / "error" display block.
//   <Pager>       — prev/next pagination footer.
//   <Pill>        — small rounded badge with semantic palette.
//   <Button>      — primary / secondary / danger variants.
import type { CSSProperties, ReactNode } from "react";

// ── Tokens (colocated here so we touch one file per design tweak) ─────

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

// ── PageShell + PageHeader ────────────────────────────────────────────

export function PageShell({
  children, maxWidth = "78rem",
}: {
  children: ReactNode;
  /** Override the default max-width when the page wants a wider
   *  table (e.g. 82rem) or narrower form (e.g. 62rem). */
  maxWidth?: string | number;
}) {
  return (
    <main
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        padding: "2rem 1.5rem",
        maxWidth,
        margin: "0 auto",
        width: "100%",
        boxSizing: "border-box",
      }}
    >
      {children}
    </main>
  );
}


export function PageHeader({
  title, subtitle, actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header
      style={{
        marginBottom: "1.5rem",
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: "1rem",
        flexWrap: "wrap",
      }}
    >
      <div>
        <h1
          style={{
            fontFamily: tokens.fontDisplay,
            fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
            fontWeight: 600,
            margin: 0,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p style={{ margin: "0.35rem 0 0", color: tokens.textMuted }}>
            {subtitle}
          </p>
        )}
      </div>
      {actions}
    </header>
  );
}

// ── Card + SectionTitle ───────────────────────────────────────────────

export function Card({
  children, style,
}: {
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <section
      style={{
        background: tokens.surface2,
        border: `1px solid ${tokens.border}`,
        borderRadius: "0.75rem",
        padding: "1.25rem",
        ...style,
      }}
    >
      {children}
    </section>
  );
}


export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2
      style={{
        fontFamily: tokens.fontDisplay,
        fontSize: "1.1rem",
        fontWeight: 600,
        margin: 0,
      }}
    >
      {children}
    </h2>
  );
}

// ── Field + Input ─────────────────────────────────────────────────────

export function Field({
  label, highlight, children,
}: {
  label: ReactNode;
  /** Tints the label red when the server flagged a field-level
   *  validation error. */
  highlight?: boolean;
  children: ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span
        style={{
          fontSize: "0.78rem",
          color: highlight ? tokens.negative : tokens.textMuted,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}


export const inputStyle: CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: tokens.text,
  fontFamily: tokens.fontBody,
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

// ── Empty / loading / error block ─────────────────────────────────────

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
      }}
    >
      {children}
    </p>
  );
}

// ── Pager ─────────────────────────────────────────────────────────────

export function Pager({
  page, totalPages, onPage, leading,
}: {
  page: number;
  totalPages: number;
  onPage: (next: number) => void;
  /** Optional left-aligned content (e.g. "Page total: $123.45"). */
  leading?: ReactNode;
}) {
  if (totalPages <= 1 && !leading) return null;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: leading ? "space-between" : "flex-end",
        alignItems: "center",
        marginTop: "1rem",
        gap: "1rem",
      }}
    >
      {leading}
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          style={{
            ...pagerBtnStyle,
            opacity: page <= 1 ? 0.4 : 1,
            cursor: page <= 1 ? "not-allowed" : "pointer",
          }}
        >
          ← Prev
        </button>
        <span style={{ color: tokens.textMuted, fontSize: "0.85rem" }}>
          {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
          style={{
            ...pagerBtnStyle,
            opacity: page >= totalPages ? 0.4 : 1,
            cursor: page >= totalPages ? "not-allowed" : "pointer",
          }}
        >
          Next →
        </button>
      </div>
    </div>
  );
}


const pagerBtnStyle: CSSProperties = {
  background: "transparent",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.4rem 0.9rem",
  fontFamily: tokens.fontBody,
  fontSize: "0.85rem",
};

// ── Pill (status / category / plan badges) ────────────────────────────

export type PillTone =
  | "neutral" | "accent" | "negative" | "warning" | "info";

const pillPalette: Record<PillTone, { bg: string; fg: string }> = {
  neutral:  { bg: "rgba(255,255,255,0.06)",         fg: tokens.text },
  accent:   { bg: "rgba(63,255,0,0.15)",            fg: tokens.accent },
  negative: { bg: "rgba(255,59,48,0.15)",           fg: tokens.negative },
  warning:  { bg: "rgba(255,184,0,0.15)",           fg: tokens.warning },
  info:     { bg: "rgba(99,166,255,0.15)",          fg: "#63a6ff" },
};

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

// ── Button ────────────────────────────────────────────────────────────

export type ButtonTone = "primary" | "secondary" | "danger" | "ghost";

const buttonPalette: Record<ButtonTone, CSSProperties> = {
  primary: {
    background: tokens.accent,
    color: tokens.onAccent,
    border: "none",
  },
  secondary: {
    background: "transparent",
    color: tokens.text,
    border: `1px solid ${tokens.border}`,
  },
  danger: {
    background: "transparent",
    color: tokens.negative,
    border: `1px solid ${tokens.negative}`,
  },
  ghost: {
    background: "transparent",
    color: tokens.textMuted,
    border: "none",
    padding: 0,
    textDecoration: "underline",
  },
};

export function Button({
  tone = "primary", busy, children, style, type = "button", ...rest
}: {
  tone?: ButtonTone;
  busy?: boolean;
  children: ReactNode;
  style?: CSSProperties;
  type?: "button" | "submit" | "reset";
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>,
         "style" | "children" | "type">) {
  const palette = buttonPalette[tone];
  const dimmed = busy || rest.disabled;
  return (
    <button
      type={type}
      {...rest}
      style={{
        borderRadius: tone === "ghost" ? 0 : "0.5rem",
        padding: tone === "ghost" ? 0 : "0.55rem 1rem",
        fontFamily: tone === "primary" ? tokens.fontDisplay : tokens.fontBody,
        fontSize: tone === "ghost" ? "0.85rem" : "0.9rem",
        fontWeight: tone === "primary" || tone === "danger" ? 600 : 500,
        cursor: dimmed ? (busy ? "wait" : "not-allowed") : "pointer",
        opacity: dimmed ? 0.6 : 1,
        ...palette,
        ...style,
      }}
    >
      {children}
    </button>
  );
}
