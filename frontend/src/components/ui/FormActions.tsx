import type { CSSProperties, ReactNode } from "react";

import { space, tokens } from "./tokens";

// The Save / Cancel button bar at the bottom of every form. Inline
// styles for this row were duplicated across ~20 route files
// (BatchForm, EditTransfer, NewTransfer, EditMonthly, …) with
// near-identical shape: flex row, gap, right-aligned, top border,
// some top margin.
//
// Use as the last child of a form (or anywhere a fixed action
// strip belongs):
//
//     <FormActions>
//       <Button tone="secondary" onClick={onCancel}>Cancel</Button>
//       <Button type="submit" busy={saving}>Save changes</Button>
//     </FormActions>
//
// The "save" button conventionally goes LAST (right-most position)
// — match the rest of the SPA so muscle memory stays consistent.
export function FormActions({
  children, style, align = "end",
}: {
  children: ReactNode;
  style?: CSSProperties;
  /** Where the buttons land. ``end`` (default) right-aligns the
   *  cluster; ``between`` spreads the leftmost button to the left
   *  edge (useful for "Delete … Save" forms where deletion is
   *  intentionally far from the primary action). */
  align?: "end" | "between";
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: space.sm,
        justifyContent: align === "between" ? "space-between" : "flex-end",
        flexWrap: "wrap",
        paddingTop: space.lg,
        marginTop: space.md,
        borderTop: `1px solid ${tokens.border}`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
