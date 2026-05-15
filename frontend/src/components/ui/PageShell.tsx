import type { ReactNode } from "react";

import { space } from "./tokens";

/** Outer ``<main>`` element with consistent padding + max-width +
 *  flex column. Mounts the ``.ds-page`` fade-up animation class. */
export function PageShell({
  children, maxWidth = "100rem", gap = space.xl,
}: {
  children: ReactNode;
  /** Override the default max-width. Most pages take the full
   *  100rem default; narrow forms (50-65rem) should set this
   *  explicitly so the inputs don't stretch awkwardly wide. */
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
