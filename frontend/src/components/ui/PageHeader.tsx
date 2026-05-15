import type { ReactNode } from "react";

import { fontSize, tokens } from "./tokens";

/** Top-of-page header — h1 title + optional subtitle + slot for
 *  right-aligned actions. Use as the first child of ``<PageShell>``. */
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
