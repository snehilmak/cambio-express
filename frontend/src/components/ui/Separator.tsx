import type { CSSProperties } from "react";

import { tokens } from "./tokens";

/** Visual divider — horizontal by default, vertical when
 *  `orientation="vertical"`.  Replaces the various `<hr>` /
 *  inline-border-top patterns scattered across the SPA.
 *
 *  Renders as `role="separator"` (the implicit role of `<hr>`)
 *  so screen readers announce the grouping.  Set
 *  `decorative` if the visual is purely cosmetic and shouldn't
 *  be announced.
 */
export function Separator({
  orientation = "horizontal", decorative = false, style,
}: {
  orientation?: "horizontal" | "vertical";
  /** Set true for purely-cosmetic dividers (e.g. between two
   *  inline items in a header).  Screen readers will skip it. */
  decorative?: boolean;
  style?: CSSProperties;
}) {
  const isVertical = orientation === "vertical";
  return (
    <div
      role={decorative ? "none" : "separator"}
      aria-orientation={isVertical ? "vertical" : "horizontal"}
      style={{
        background: tokens.border,
        flexShrink: 0,
        ...(isVertical
          ? { width: 1, height: "auto", alignSelf: "stretch" }
          : { width: "100%", height: 1, margin: "0.5rem 0" }),
        ...style,
      }}
    />
  );
}
