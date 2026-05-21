import type { ReactNode } from "react";

import { toneTokens } from "./tokens";

// Inline banner for form errors, success confirmations, and
// neutral notices.  Replaces the ``alertErrorStyle`` /
// ``serverError`` blocks that were duplicated across ~10 routes
// (AdminUserForm, SuperadminStoreForm, Settings, etc.).
// Use for in-form messaging; for global cross-page announcements
// ``<AnnouncementBanner>`` (mounted inside ``AppShell``) is the
// right surface.
//
// Phase-2 polish (Linear / shadcn vocabulary): each tone now leads
// with a glyph so the alert's intent is readable at a glance
// (without having to parse the color first), and the colors come
// from the shared `--db-tone-*` palette so Alert, ErrorState, Pill,
// and the field-error states stay in lock-step.

export type AlertTone = "error" | "warning" | "success" | "info";

export function Alert({
  tone = "error", children, role,
}: {
  tone?: AlertTone;
  children: ReactNode;
  /** Forwarded to the wrapper element. Defaults to ``alert`` for
   *  ``error`` and ``warning`` so screen readers announce them; the
   *  ``success`` / ``info`` variants default to ``status`` which is
   *  less interruptive. */
  role?: string;
}) {
  const c = toneTokens[tone];
  const resolvedRole =
    role ?? (tone === "error" || tone === "warning" ? "alert" : "status");
  return (
    <div
      role={resolvedRole}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "0.55rem",
        padding: "0.65rem 0.85rem",
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: "0.55rem",
        color: c.fg,
        fontSize: "0.88rem",
        lineHeight: 1.45,
      }}
    >
      <ToneIcon tone={tone} />
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
    </div>
  );
}


function ToneIcon({ tone }: { tone: AlertTone }) {
  // 1rem stroke glyphs — same vocabulary the slim sidebar uses, so
  // the chrome reads as one component family.  `aria-hidden` because
  // the surrounding `role="alert"` / `role="status"` is what screen
  // readers announce; the icon is decorative.
  const sharedProps = {
    width: 16, height: 16, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", strokeWidth: 2,
    strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
    "aria-hidden": true,
    style: { flexShrink: 0, marginTop: "0.1rem" },
  };
  switch (tone) {
    case "error":
      return (
        <svg {...sharedProps}>
          <circle cx={12} cy={12} r={10} />
          <line x1={12} y1={8}  x2={12} y2={12} />
          <line x1={12} y1={16} x2={12.01} y2={16} />
        </svg>
      );
    case "warning":
      return (
        <svg {...sharedProps}>
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1={12} y1={9}  x2={12} y2={13} />
          <line x1={12} y1={17} x2={12.01} y2={17} />
        </svg>
      );
    case "success":
      return (
        <svg {...sharedProps}>
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      );
    case "info":
      return (
        <svg {...sharedProps}>
          <circle cx={12} cy={12} r={10} />
          <line x1={12} y1={16} x2={12} y2={12} />
          <line x1={12} y1={8}  x2={12.01} y2={8} />
        </svg>
      );
  }
}
