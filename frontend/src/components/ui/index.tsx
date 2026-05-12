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
//                   max-width + flex column. Mounts the .ds-page
//                   fade-up animation class.
//   <PageHeader>  — title + optional subtitle + slot for actions.
//   <Card>        — surface-2 panel with border + radius + padding.
//                   Hover lift via .ds-card when interactive.
//   <SectionTitle>— h2 with the Space Grotesk display family.
//   <Section>     — h2 + actions slot + body wrapper (cards stack).
//   <Field>       — label + children stacked, with optional
//                   highlight on validation error.
//   <Input>       — text input with the standard token styling
//                   + .ds-input focus glow.
//   <Empty>       — "no rows" / "loading" / "error" inline message.
//   <EmptyState>  — full empty-with-icon state (404 / no data).
//   <ErrorState>  — fetch-error block with retry button.
//   <Loading>     — text + spinner; for inline use.
//   <TableSkeleton> — shimmered placeholder rows.
//   <Table>       — surface-styled table with auto th/td.
//   <KpiCard>     — small stat tile (label / value / sub / accent).
//   <KpiGrid>     — auto-fit grid wrapper for KpiCards.
//   <Pager>       — prev/next pagination footer.
//   <Pill>        — small rounded badge with semantic palette.
//   <Button>      — primary / secondary / danger / ghost variants
//                   with scale-press + hover tint via .ds-btn.
//
// Motion: classNames in ui.css. Honors prefers-reduced-motion via
// the global rule at the bottom of static/content.css.
//
// Tokens (colors / spacing / type / monoStyle / inputStyle / th/tdStyle)
// live in `./tokens.ts` — kept separate so Vite fast-refresh isn't
// blocked by non-component exports. Re-exported below for callers
// that grab everything from `components/ui` directly.
import type { CSSProperties, ReactNode } from "react";

import "./ui.css";
import { fontSize, inputStyle, space, tokens } from "./tokens";

// Re-export non-component values from `./tokens` so consumers have
// a single `components/ui` import path. Fast-refresh complains
// because non-component exports on a file that also exports
// components prevent HMR for THIS file — but the actual values
// live in `./tokens.ts` (a non-component file that HMR handles
// fine), so the only practical downside is that this barrel
// module won't hot-reload its own component edits. Acceptable
// trade-off for the simpler import surface.
/* eslint-disable react-refresh/only-export-components -- public DS surface: re-export tokens from this barrel so consumers don't learn two import paths */
export {
  fontSize, inputStyle, monoStyle, space, tdStyle, thStyle, tokens,
} from "./tokens";
/* eslint-enable react-refresh/only-export-components */

// ── PageShell + PageHeader ────────────────────────────────────────────

export function PageShell({
  children, maxWidth = "78rem", gap = space.xl,
}: {
  children: ReactNode;
  /** Override the default max-width when the page wants a wider
   *  table (e.g. 82rem) or narrower form (e.g. 62rem). */
  maxWidth?: string | number;
  /** Vertical gap between top-level children (header / sections /
   *  cards). Defaults to `space.xl` (1.5rem). */
  gap?: string | number;
}) {
  return (
    <main
      className="ds-page"
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        // Slightly tighter horizontal padding + a more compact
        // top so PageHeader sits closer to the chrome and the
        // first card doesn't float in the middle of the screen.
        padding: "1.5rem 1.5rem 2.5rem",
        maxWidth,
        margin: "0 auto",
        width: "100%",
        boxSizing: "border-box",
        gap,
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
        // No extra marginBottom — PageShell's gap prop provides
        // the breathing room. Stops the cumulative spacing that
        // pushed the first content card down by ~3rem.
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
        flexWrap: "wrap",
        minHeight: "2.5rem",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <h1
          style={{
            fontFamily: tokens.fontDisplay,
            fontSize: "clamp(1.55rem, 3vw, 1.95rem)",
            fontWeight: 700,
            letterSpacing: "-0.015em",
            lineHeight: 1.15,
            margin: 0,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            style={{
              margin: "0.35rem 0 0",
              color: tokens.textMuted,
              fontSize: fontSize.sm,
              lineHeight: 1.3,
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {actions && (
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            flexWrap: "wrap",
          }}
        >
          {actions}
        </div>
      )}
    </header>
  );
}

// ── Card + SectionTitle ───────────────────────────────────────────────

export function Card({
  children, style, interactive, padding = "1.25rem", className,
}: {
  children: ReactNode;
  style?: CSSProperties;
  /** When true, applies hover-lift + accent-border affordance.
   *  Set on cards that wrap clickable content. */
  interactive?: boolean;
  /** Override padding. Use `space.sm` for dense rows, `space.xl`
   *  for full-page hero cards. */
  padding?: string | number;
  /** Extra className stacked on top of `ds-card`. */
  className?: string;
}) {
  const cls = ["ds-card"];
  if (interactive) cls.push("ds-card--interactive");
  if (className) cls.push(className);
  return (
    <section
      className={cls.join(" ")}
      style={{
        background: tokens.surface2,
        border: `1px solid ${tokens.border}`,
        borderRadius: "0.75rem",
        padding,
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
        fontSize: fontSize.lg,
        fontWeight: 600,
        margin: 0,
      }}
    >
      {children}
    </h2>
  );
}


export function Section({
  title, actions, children,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: space.md }}>
      {(title || actions) && (
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: space.lg,
            flexWrap: "wrap",
          }}
        >
          {title ? <SectionTitle>{title}</SectionTitle> : <span />}
          {actions}
        </header>
      )}
      {children}
    </section>
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


/** Token-styled text/number/date input with the ds-input focus
 *  glow class applied. Forwards every standard input prop. */
export function Input({
  className, style, ...rest
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={["ds-input", className].filter(Boolean).join(" ")}
      style={{ ...inputStyle, ...style }}
    />
  );
}


/** Token-styled <select> with the same focus glow as Input. */
export function Select({
  className, style, children, ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={["ds-input", className].filter(Boolean).join(" ")}
      style={{ ...inputStyle, ...style }}
    >
      {children}
    </select>
  );
}


/** Token-styled <textarea>. */
export function Textarea({
  className, style, ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={["ds-input", className].filter(Boolean).join(" ")}
      style={{
        ...inputStyle,
        fontFamily: tokens.fontBody,
        minHeight: "5rem",
        resize: "vertical",
        ...style,
      }}
    />
  );
}

// ── KPI tiles ────────────────────────────────────────────────────────

export type KpiTone =
  | "neutral" | "positive" | "negative" | "warning" | "primary" | "neon" | "muted";

const kpiAccent: Record<KpiTone, string> = {
  neutral:  tokens.border,
  primary:  "#63a6ff",            // info-ish blue used in legacy
  neon:     tokens.accent,
  positive: tokens.accent,
  warning:  tokens.warning,
  negative: tokens.negative,
  muted:    tokens.border,
};

/** Single stat tile: label / value / sub. Top border accents by
 *  tone. Use mono on the value via the `.ds-kpi-value` class. */
export function KpiCard({
  label, value, sub, tone = "neutral",
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: KpiTone;
}) {
  return (
    <div
      style={{
        background: tokens.surface2,
        border: `1px solid ${tokens.border}`,
        borderTop: `3px solid ${kpiAccent[tone]}`,
        borderRadius: "0.75rem",
        padding: `${space.md} ${space.lg}`,
      }}
    >
      <div
        style={{
          fontSize: fontSize.xs,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: tokens.textMuted,
        }}
      >
        {label}
      </div>
      <div
        className="ds-kpi-value"
        style={{
          fontFamily: tokens.fontMono,
          fontSize: fontSize.xl,
          fontWeight: 700,
          marginTop: space.sm,
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          style={{
            fontSize: fontSize.sm,
            color: tokens.textMuted,
            marginTop: space.xs,
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}


/** Auto-fit grid of KpiCards. */
export function KpiGrid({
  children, minWidth = "200px",
}: {
  children: ReactNode;
  /** Minimum tile width before wrapping. 200px default; smaller
   *  for dense tables of metrics. */
  minWidth?: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(auto-fit, minmax(${minWidth}, 1fr))`,
        gap: space.md,
      }}
    >
      {children}
    </div>
  );
}

// ── Tables ───────────────────────────────────────────────────────────
// `thStyle` + `tdStyle` are imported from ./tokens.ts and re-exported
// from this file's barrel.

/** Auto-styled <table> with DS th/td defaults. Children pattern
 *  is the standard `<thead>…<tbody>…`; this just sets borders +
 *  fonts uniformly. */
export function Table({
  children, style,
}: {
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: fontSize.base,
          ...style,
        }}
      >
        {children}
      </table>
    </div>
  );
}


/** Loading placeholder for a Table. Renders `rows` skeleton rows
 *  with `cols` shimmer cells each. */
export function TableSkeleton({
  rows = 5, cols = 4,
}: { rows?: number; cols?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: space.sm }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: space.md }}
        >
          {Array.from({ length: cols }).map((__, j) => (
            <div key={j} className="ds-skel" style={{ height: "1.2rem" }} />
          ))}
        </div>
      ))}
    </div>
  );
}

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
        fontSize: fontSize.base,
      }}
    >
      {children}
    </p>
  );
}


/** Full block empty state with icon + title + body + optional CTA.
 *  Use when the WHOLE region (a table, a card body, a tab pane)
 *  has zero content, not for inline "Loading…" messages. */
export function EmptyState({
  icon, title, body, cta,
}: {
  /** Inline SVG node (24x24 ideally). Defaults to inbox glyph. */
  icon?: ReactNode;
  title: ReactNode;
  body?: ReactNode;
  /** Right-aligned action — usually a <Button> or <Link>. */
  cta?: ReactNode;
}) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "2.5rem 1.5rem",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: space.sm,
      }}
    >
      <span
        style={{
          width: "3rem", height: "3rem",
          borderRadius: "0.75rem",
          background: "rgba(63, 255, 0, 0.08)",
          border: "1px solid rgba(63, 255, 0, 0.25)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          color: tokens.accent,
          marginBottom: space.xs,
        }}
        aria-hidden
      >
        {icon ?? <DefaultEmptyIcon />}
      </span>
      <div style={{ fontWeight: 600, fontSize: fontSize.lg }}>{title}</div>
      {body && (
        <div style={{ color: tokens.textMuted, maxWidth: "32rem" }}>
          {body}
        </div>
      )}
      {cta && <div style={{ marginTop: space.sm }}>{cta}</div>}
    </div>
  );
}

function DefaultEmptyIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22"
         stroke="currentColor" fill="none" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>
    </svg>
  );
}


/** Fetch / mutation error block with optional retry button.
 *  Use INSTEAD OF `<Empty error>` when there's a recoverable
 *  failure (user can retry). For permanent errors (404, 403)
 *  use <EmptyState> with a redirect CTA. */
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


/** Inline "Loading…" with optional label. For full-region
 *  loading states use <TableSkeleton>. */
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
  tone = "primary", busy, children, style, type = "button",
  className, size = "md", ...rest
}: {
  tone?: ButtonTone;
  busy?: boolean;
  children: ReactNode;
  style?: CSSProperties;
  type?: "button" | "submit" | "reset";
  className?: string;
  /** `sm` for inline-table buttons / compact toolbars,
   *  `md` (default) for most buttons,
   *  `lg` for primary CTAs in hero/empty states. */
  size?: "sm" | "md" | "lg";
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>,
         "style" | "children" | "type" | "className">) {
  const palette = buttonPalette[tone];
  const dimmed = busy || rest.disabled;
  const cls = ["ds-btn", `ds-btn--${tone}`];
  if (className) cls.push(className);
  const sizing = {
    sm: { padding: "0.35rem 0.75rem", fontSize: fontSize.sm,   minHeight: "2rem"   },
    md: { padding: "0.55rem 1rem",    fontSize: "0.9rem",      minHeight: "2.4rem" },
    lg: { padding: "0.75rem 1.4rem",  fontSize: fontSize.base, minHeight: "2.85rem"},
  }[size];
  return (
    <button
      type={type}
      {...rest}
      className={cls.join(" ")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.4rem",
        borderRadius: tone === "ghost" ? 0 : "0.5rem",
        padding: tone === "ghost" ? 0 : sizing.padding,
        minHeight: tone === "ghost" ? undefined : sizing.minHeight,
        fontFamily: tokens.fontBody,
        letterSpacing: tone === "primary" ? "-0.005em" : undefined,
        fontSize: tone === "ghost" ? fontSize.sm : sizing.fontSize,
        fontWeight: tone === "primary" || tone === "danger" ? 600 : 500,
        cursor: dimmed ? (busy ? "wait" : "not-allowed") : "pointer",
        opacity: dimmed ? 0.6 : 1,
        whiteSpace: "nowrap",
        ...palette,
        ...style,
      }}
    >
      {children}
    </button>
  );
}


/** Anchor styled like a Button. For internal navigation, prefer
 *  wrapping <Button> in a <Link> instead (gets client-side
 *  routing); reach for ButtonLink when you need an `href` for
 *  CSV downloads, external URLs, etc. */
export function ButtonLink({
  tone = "secondary", children, href, style, className, size = "md", ...rest
}: {
  tone?: ButtonTone;
  href: string;
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  size?: "sm" | "md" | "lg";
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>,
         "style" | "children" | "href" | "className">) {
  const palette = buttonPalette[tone];
  const sizing = {
    sm: { padding: "0.35rem 0.75rem", fontSize: fontSize.sm,   minHeight: "2rem"   },
    md: { padding: "0.55rem 1rem",    fontSize: "0.9rem",      minHeight: "2.4rem" },
    lg: { padding: "0.75rem 1.4rem",  fontSize: fontSize.base, minHeight: "2.85rem"},
  }[size];
  const cls = ["ds-btn", `ds-btn--${tone}`];
  if (className) cls.push(className);
  return (
    <a
      href={href}
      {...rest}
      className={cls.join(" ")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.4rem",
        textDecoration: "none",
        borderRadius: "0.5rem",
        padding: sizing.padding,
        minHeight: sizing.minHeight,
        fontFamily: tokens.fontBody,
        fontSize: sizing.fontSize,
        fontWeight: tone === "primary" || tone === "danger" ? 600 : 500,
        whiteSpace: "nowrap",
        ...palette,
        ...style,
      }}
    >
      {children}
    </a>
  );
}
