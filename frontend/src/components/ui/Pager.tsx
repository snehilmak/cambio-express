import type { ReactNode } from "react";

import { tokens } from "./tokens";
import { Button } from "./Button";

/** Prev/next pagination footer. ``leading`` is for an optional
 *  left-aligned label (e.g. "Page total: $123.45"). */
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
        <Button
          tone="secondary"
          size="sm"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
        >
          ← Prev
        </Button>
        <span style={{ color: tokens.textMuted, fontSize: "0.85rem" }}>
          {page} / {totalPages}
        </span>
        <Button
          tone="secondary"
          size="sm"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
