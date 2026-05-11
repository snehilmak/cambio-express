import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  defaultStoreIds, useReportDrilldown,
  type AggregatedRow, type AggregatedTotals,
} from "../api/reportDrilldown";

export interface KpiSpec {
  label: string;
  tone?: "primary" | "neon" | "muted" | "warning" | "negative";
  // Extracted from totals.
  value: (totals: AggregatedTotals) => React.ReactNode;
}

export interface ColumnSpec {
  label: string;
  // Field name on the row OR a render function.
  field: keyof AggregatedRow | ((r: AggregatedRow) => React.ReactNode);
  align?: "left" | "right";
  mono?: boolean;
}

interface ReportDrilldownProps {
  // API path slug ("sales-by-company", "cashier-productivity", …).
  apiSlug: string;
  // Page title.
  title: string;
  // "company" / "companies", "row" / "rows" — used in the result count.
  resultUnit: [string, string];
  // KPI strip across the top.
  kpis: KpiSpec[];
  // Column config for the row table.
  columns: ColumnSpec[];
  // CSV export URL (Flask). Caller passes the resolved URL so each
  // drilldown can point at /reports/<slug>.csv or
  // /owner/reports/<slug>.csv.
  csvUrl: string;
  // Back link target — /app/reports or /app/owner/reports.
  backTo: string;
  // Extra query params for the API (e.g. `{sort_by: "count"}`).
  // The CSV link receives them too so the export matches the view.
  extraParams?: Record<string, string>;
}

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1)
    .toISOString().slice(0, 10);
};

export function ReportDrilldown({
  apiSlug, title, resultUnit, kpis, columns, csvUrl, backTo,
  extraParams,
}: ReportDrilldownProps) {
  const [params, setParams] = useSearchParams();
  const [from, setFrom] = useState(() => params.get("from") || monthStart());
  const [to, setTo] = useState(() => params.get("to") || today());

  // Sync `from`/`to` back into the URL so the report is shareable.
  useEffect(() => {
    const next = new URLSearchParams(params);
    next.set("from", from);
    next.set("to", to);
    setParams(next, { replace: true });
  }, [from, to]);  // eslint-disable-line react-hooks/exhaustive-deps

  const storeIds = defaultStoreIds();
  const { data, isLoading, isError, error } = useReportDrilldown({
    apiSlug, from, to, storeIds, extraParams,
  });

  const rowCount = data?.rows.length ?? 0;
  const unit = rowCount === 1 ? resultUnit[0] : resultUnit[1];

  // Append the period (and any extraParams) to the CSV URL so the
  // download matches the visible filter. The Flask endpoint reads
  // the same query params.
  const csvParams = new URLSearchParams({ from, to, ...(extraParams ?? {}) });
  const csvHref = `${csvUrl}?${csvParams.toString()}`;

  return (
    <main style={pageStyle}>
      <header style={headerRow}>
        <Link to={backTo} style={backLink}>← Reports</Link>
        <h1 style={titleStyle}>{title}</h1>
        <div style={actionRow}>
          <form
            style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}
            onSubmit={(e) => {
              e.preventDefault();
              // useEffect already syncs to URL — submitting is a noop.
            }}
          >
            <label style={inputLabel}>
              <span>From</span>
              <input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                style={dateInput}
              />
            </label>
            <label style={inputLabel}>
              <span>To</span>
              <input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                style={dateInput}
              />
            </label>
          </form>
          <a href={csvHref} style={btnOutline} download>Export CSV</a>
          <button
            type="button"
            style={btnOutline}
            onClick={() => window.print()}
          >
            Print / PDF
          </button>
        </div>
      </header>

      {storeIds.length === 0 && (
        <p style={muted}>
          Sign in to a store to see this report. (Owner-umbrella multi-store
          rollup ships in a follow-up.)
        </p>
      )}

      {data && (
        <div style={kpiGrid}>
          {kpis.map((k) => (
            <div
              key={k.label}
              style={{
                ...kpiCard,
                borderTop: `3px solid ${toneToColor(k.tone)}`,
              }}
            >
              <div style={kpiLabel}>{k.label}</div>
              <div style={kpiValue}>{k.value(data.totals)}</div>
            </div>
          ))}
        </div>
      )}

      <div style={filterRow}>
        <span style={muted}>
          {fmtDate(from)} – {fmtDate(to)}
        </span>
        {data && (
          <span style={muted}>
            {rowCount.toLocaleString()} {unit}
          </span>
        )}
      </div>

      {isLoading && <p style={muted}>Loading…</p>}
      {isError && (
        <p style={errorStyle}>
          Couldn't load report — {error instanceof Error ? error.message : "unknown error"}
        </p>
      )}

      {data && data.rows.length === 0 && (
        <p style={muted}>No data in this period.</p>
      )}

      {data && data.rows.length > 0 && (
        <table style={tableStyle}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.label}
                  style={{
                    ...thStyle,
                    textAlign: c.align ?? (c.mono ? "right" : "left"),
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                {columns.map((c) => {
                  const value =
                    typeof c.field === "function"
                      ? c.field(r)
                      : r[c.field];
                  return (
                    <td
                      key={c.label}
                      style={{
                        ...tdStyle,
                        textAlign: c.align ?? (c.mono ? "right" : "left"),
                        fontFamily: c.mono
                          ? "var(--db-font-mono, 'JetBrains Mono', monospace)"
                          : undefined,
                      }}
                    >
                      {value as React.ReactNode}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

function toneToColor(tone?: string): string {
  switch (tone) {
    case "primary": return "var(--db-info, #5ac8fa)";
    case "neon": return "var(--db-accent, #3fff00)";
    case "warning": return "var(--db-warning, #ffcc00)";
    case "negative": return "var(--db-negative, #ff3b30)";
    default: return "var(--db-border, #262626)";
  }
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

// Helper for the per-report TSX wrappers in routes/reports/*. Lives
// alongside the component so the wrappers only need one import path.
// eslint-disable-next-line react-refresh/only-export-components -- adjacent helper used by every drilldown wrapper
export const fmtMoney = (n: number) =>
  `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const pageStyle: React.CSSProperties = {
  flex: 1, padding: "2rem 1.5rem", maxWidth: "75rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: "1.25rem",
};
const headerRow: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: "0.5rem",
};
const backLink: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem",
  textDecoration: "none",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)", fontWeight: 600, margin: 0,
};
const actionRow: React.CSSProperties = {
  display: "flex", flexWrap: "wrap", gap: "0.5rem",
  alignItems: "center", marginTop: "0.5rem",
};
const inputLabel: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: "0.15rem",
  fontSize: "0.7rem", color: "var(--db-text-muted, #a3a3a3)",
  textTransform: "uppercase", letterSpacing: "0.05em",
};
const dateInput: React.CSSProperties = {
  padding: "0.35rem 0.5rem",
  background: "var(--db-surface-1, #0a0a0a)", color: "inherit",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.4rem", fontSize: "0.85rem",
  fontFamily: "inherit",
};
const btnOutline: React.CSSProperties = {
  background: "transparent", color: "inherit",
  border: "1px solid var(--db-border, #262626)",
  padding: "0.4rem 0.85rem",
  borderRadius: "0.5rem", fontSize: "0.85rem",
  cursor: "pointer", textDecoration: "none",
  display: "inline-block",
};
const kpiGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "0.75rem",
};
const kpiCard: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "0.75rem 1rem",
};
const kpiLabel: React.CSSProperties = {
  fontSize: "0.7rem", textTransform: "uppercase",
  letterSpacing: "0.05em", color: "var(--db-text-muted, #a3a3a3)",
};
const kpiValue: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "1.4rem", fontWeight: 700, marginTop: "0.4rem",
};
const filterRow: React.CSSProperties = {
  display: "flex", justifyContent: "space-between",
  padding: "0.5rem 0",
  borderTop: "1px solid var(--db-border, #262626)",
  borderBottom: "1px solid var(--db-border, #262626)",
};
const muted: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem", margin: 0,
};
const errorStyle: React.CSSProperties = {
  color: "var(--db-negative, #ff3b30)",
  background: "rgba(255,59,48,0.08)",
  border: "1px solid rgba(255,59,48,0.4)",
  padding: "0.75rem 1rem", borderRadius: "0.5rem",
};
const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", fontSize: "0.9rem",
};
const thStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--db-border, #262626)",
  fontSize: "0.7rem", textTransform: "uppercase",
  color: "var(--db-text-muted, #a3a3a3)", fontWeight: 500,
};
const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};
