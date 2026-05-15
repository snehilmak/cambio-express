import type { ReactNode } from "react";

import { fontSize, space, tokens } from "./tokens";

/** Section header — h2 in the display font. Used standalone or
 *  inside ``<Section>``. */
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


/** Wrapper for a labelled section: optional title + right-aligned
 *  actions slot + a body. Children stack with ``space.md`` gap. */
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
