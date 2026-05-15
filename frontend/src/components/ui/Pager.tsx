import type { CSSProperties, ReactNode } from "react";

import { tokens } from "./tokens";

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
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          style={{
            ...pagerBtnStyle,
            opacity: page <= 1 ? 0.4 : 1,
            cursor: page <= 1 ? "not-allowed" : "pointer",
          }}
        >
          ← Prev
        </button>
        <span style={{ color: tokens.textMuted, fontSize: "0.85rem" }}>
          {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
          style={{
            ...pagerBtnStyle,
            opacity: page >= totalPages ? 0.4 : 1,
            cursor: page >= totalPages ? "not-allowed" : "pointer",
          }}
        >
          Next →
        </button>
      </div>
    </div>
  );
}


const pagerBtnStyle: CSSProperties = {
  background: "transparent",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.4rem 0.9rem",
  fontFamily: tokens.fontBody,
  fontSize: "0.85rem",
};
