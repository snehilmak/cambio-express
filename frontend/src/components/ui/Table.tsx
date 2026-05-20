import type { CSSProperties, ReactNode } from "react";

import { fontSize, space } from "./tokens";
import styles from "./Table.module.css";

// `thStyle` + `tdStyle` are imported from ./tokens.ts directly by
// route callers (re-exported from the ./index.tsx barrel).

/** Auto-styled ``<table>`` with DS th/td defaults. Children pattern
 *  is the standard ``<thead>…<tbody>…``; this just sets borders +
 *  fonts uniformly.
 *
 *  The wrapper applies a `tbody tr:hover` rule so rows respond
 *  visibly when the cursor passes over them — same vocabulary as
 *  the sidebar's hover rows (background tint only, no transform).
 *  Routes that want a row to feel "active" (e.g. a selected
 *  transfer) can add an `.is-active` class to the `<tr>` itself
 *  — see Table.module.css for the hook. */
export function Table({
  children, style,
}: {
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div className={styles.wrap} style={{ overflowX: "auto" }}>
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


/** Loading placeholder for a ``<Table>``. Renders ``rows`` skeleton
 *  rows with ``cols`` shimmer cells each. */
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
