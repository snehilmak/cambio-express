import type { ReactNode } from "react";

import { tokens } from "./tokens";

// Inline banner for form errors, success confirmations, and
// neutral notices. Replaces the ``alertErrorStyle`` /
// ``serverError`` blocks that were duplicated across ~10 routes
// (AdminUserForm, SuperadminStoreForm, AccountProfile, etc.).
// Use for in-form messaging; for global cross-page announcements
// ``<AnnouncementBanner>`` (mounted inside ``AppShell``) is the
// right surface.

export type AlertTone = "error" | "warning" | "success" | "info";

const alertPalette: Record<AlertTone, { bg: string; border: string; fg: string }> = {
  error:   { bg: "rgba(255,59,48,0.08)",  border: "rgba(255,59,48,0.3)",  fg: tokens.negative },
  warning: { bg: "rgba(255,184,0,0.08)",  border: "rgba(255,184,0,0.3)",  fg: tokens.warning },
  success: { bg: "rgba(63,255,0,0.08)",   border: "rgba(63,255,0,0.3)",   fg: tokens.accent },
  info:    { bg: "rgba(99,166,255,0.08)", border: "rgba(99,166,255,0.3)", fg: "#63a6ff" },
};

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
  const c = alertPalette[tone];
  const resolvedRole =
    role ?? (tone === "error" || tone === "warning" ? "alert" : "status");
  return (
    <div
      role={resolvedRole}
      style={{
        padding: "0.6rem 0.85rem",
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: "0.5rem",
        color: c.fg,
        fontSize: "0.88rem",
      }}
    >
      {children}
    </div>
  );
}
