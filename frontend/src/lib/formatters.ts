// Shared money + number formatting. Single source of truth so
// every table, KPI card, and detail row formats consistently.

/** Format a number as $X,XXX (no decimals). Good for KPI cards
 *  and summary stats where cents don't matter. */
export function fmtMoney(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "$0";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** Format a number as $X,XXX.XX (2 decimals). Good for line items,
 *  transfer amounts, fees — anywhere cents matter. */
export function fmtMoney2(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "$0.00";
  return `$${n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Format a number as a locale-aware integer with commas. */
export function fmtNumber(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "0";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** Short date: "May 7" or "May 7, 2026" — good for chart labels
 *  and compact table cells. */
export function fmtShortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
    });
  } catch { return iso; }
}

/** Date + time: "May 7, 12:50 AM" — good for activity feeds
 *  and logs where time matters. */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

/** Compact date: "05/26/26" (MM/DD/YY) — for dense report tables. */
export function fmtDateCompact(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "2-digit", day: "2-digit", year: "2-digit",
    });
  } catch { return iso ?? ""; }
}
