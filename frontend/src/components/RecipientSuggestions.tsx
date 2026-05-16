import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { components } from "../api/openapi";

// Recipient suggestion chips above the recipient_name input on
// the transfer form.
//
// Behavior:
//   * Hidden when no sender is picked yet (``customerId`` null) —
//     the lookup has nothing to filter on.
//   * Hidden when the picked customer has no transfer history —
//     show nothing rather than an empty "no suggestions" placeholder.
//   * Otherwise renders up to N chip buttons, newest-first. Clicking
//     a chip fires ``onPick(row)`` so the parent form can fill the
//     recipient name / phone / country fields in one go.
//
// Data source: ``GET /api/v2/customers/{id}/recent-recipients?
// store_id={sid}``. Fetched on-demand when ``customerId`` changes —
// no TanStack Query wrapping because the data is per-form-instance,
// invalidates on sender change, and doesn't need to be shared with
// any other surface.

type RecentRecipientRow =
  components["schemas"]["RecentRecipientRow"];
type RecentRecipientsResponse =
  components["schemas"]["RecentRecipientsResponse"];

interface Props {
  customerId: number | null;
  storeId: number;
  onPick: (row: RecentRecipientRow) => void;
}

export default function RecipientSuggestions({
  customerId, storeId, onPick,
}: Props) {
  const [rows, setRows] = useState<RecentRecipientRow[]>([]);

  useEffect(() => {
    if (customerId == null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- sync to upstream sender selection; clearing rows when sender clears is the whole point of the effect
      setRows([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = await api<RecentRecipientsResponse>(
          `/api/v2/customers/${customerId}/recent-recipients`
          + `?store_id=${storeId}&limit=5`,
        );
        if (!cancelled) setRows(resp.rows);
      } catch {
        // Suggestions are a UX nicety — a network blip shouldn't
        // surface an error here. Silently drop and let the cashier
        // type the recipient manually.
        if (!cancelled) setRows([]);
      }
    })();
    return () => { cancelled = true; };
  }, [customerId, storeId]);

  if (rows.length === 0) return null;

  return (
    <div style={containerStyle} role="group" aria-label="Recent recipients">
      <span style={labelStyle}>Recent:</span>
      {rows.map((r, i) => (
        <button
          key={`${r.name}-${r.country}-${r.phone}-${i}`}
          type="button"
          onClick={() => onPick(r)}
          style={chipStyle}
          title={`${r.name} · ${r.country} · ${r.phone || "no phone"}`}
        >
          {r.name}
        </button>
      ))}
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.4rem",
  alignItems: "center",
  marginBottom: "0.5rem",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "var(--db-text-muted, #a3a3a3)",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
};

const chipStyle: React.CSSProperties = {
  appearance: "none",
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  color: "var(--db-text, #f5f5f5)",
  borderRadius: "999px",
  padding: "0.3rem 0.75rem",
  fontSize: "0.85rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  cursor: "pointer",
};
