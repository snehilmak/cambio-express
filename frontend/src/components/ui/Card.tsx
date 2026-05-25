import type { CSSProperties, ReactNode } from "react";

import { tokens } from "./tokens";

/** Surface-2 panel with border + radius + padding. Hover lift via
 *  ``.ds-card`` when ``interactive``. */
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
  const cls = ["ds-card", "ds-fade-in"];
  if (interactive) cls.push("ds-card--interactive");
  if (className) cls.push(className);
  return (
    <section
      className={cls.join(" ")}
      style={{
        background: tokens.surface2,
        border: `1px solid ${tokens.border}`,
        // Slightly softer radius than the original 0.75rem so cards
        // feel modern without going so big they read as decorative.
        borderRadius: "0.875rem",
        padding,
        ...style,
      }}
    >
      {children}
    </section>
  );
}
