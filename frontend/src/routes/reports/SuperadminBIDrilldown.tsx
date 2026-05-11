import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../../lib/api";

// Generic React shell for all superadmin BI drilldowns. The legacy
// Jinja drilldowns shared the same shape (KPI strip + period filter
// + paginated row table); rather than build one TSX wrapper per
// report (20 reports → 20 files), this single component reads the
// `{rows, totals}` envelope from /api/v2/superadmin/reports/<slug>
// and auto-derives KPIs from totals and columns from the first row.
//
// Per-report title comes from `_SUPERADMIN_REPORT_TITLES`. Anything
// not in the lookup falls back to a humanized slug.

const _TITLES: Record<string, string> = {
  "active-stores-by-plan":   "Active Stores by Plan",
  "signup-funnel":           "Signup Funnel",
  "login-activity":          "Login Activity",
  "mrr-arr":                 "MRR & ARR",
  "churn-cohort":            "Churn Cohort",
  "conversion-rate":         "Conversion Rate",
  "time-to-convert":         "Time to Convert",
  "trial-expiry-timing":     "Trial Expiry Timing",
  "bank-sync-adoption":      "Bank Sync Adoption",
  "tv-display-adoption":     "TV Display Adoption",
  "owner-adoption":          "Multi-store Owner Adoption",
  "passkey-adoption":        "Passkey Adoption",
  "password-resets":         "Password Resets",
  "suspended-stores":        "Suspended Stores",
  "retention-queue":         "Retention Queue",
  "refunds":                 "Refunds",
  "failed-payments":         "Failed Payments",
  "payouts":                 "Payouts",
  "dau-mau":                 "DAU / MAU",
  "webhook-health":          "Webhook Health",
};

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1)
    .toISOString().slice(0, 10);
};

interface Envelope {
  rows: Array<Record<string, unknown>>;
  totals: Record<string, unknown>;
  [extra: string]: unknown;
}

export default function SuperadminBIDrilldown() {
  const { slug } = useParams<{ slug: string }>();
  const [params, setParams] = useSearchParams();
  const [from, setFrom] = useState(() => params.get("from") || monthStart());
  const [to, setTo] = useState(() => params.get("to") || today());
  const [data, setData] = useState<Envelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setLoading] = useState(true);

  useEffect(() => {
    const next = new URLSearchParams(params);
    next.set("from", from);
    next.set("to", to);
    setParams(next, { replace: true });
  }, [from, to]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!slug) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset loading/error before async fetch of superadmin BI report; result/error/loading get set in the resolved promise callbacks
    setLoading(true);
    setError(null);
    api<Envelope>(
      `/api/v2/superadmin/reports/${slug}?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    )
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : "load failed"))
      .finally(() => setLoading(false));
  }, [slug, from, to]);

  if (!slug) return null;

  const title = _TITLES[slug] || humanize(slug);
  const rows = data?.rows ?? [];
  const totals = data?.totals ?? {};
  const totalKeys = Object.keys(totals).filter(
    k => k !== "current_label" && k !== "prior_label",
  );
  const rowKeys = rows.length > 0 ? Object.keys(rows[0]) : [];

  const csvHref = `/superadmin/reports/${slug}.csv?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;

  return (
    <main style={pageStyle}>
      <header>
        <Link to="/superadmin/reports" style={backLink}>← Platform Reports</Link>
        <h1 style={titleStyle}>{title}</h1>
        <div style={actionRow}>
          <label style={inputLabel}>
            <span>From</span>
            <input
              type="date"
              value={from}
              onChange={e => setFrom(e.target.value)}
              style={dateInput}
            />
          </label>
          <label style={inputLabel}>
            <span>To</span>
            <input
              type="date"
              value={to}
              onChange={e => setTo(e.target.value)}
              style={dateInput}
            />
          </label>
          <a href={csvHref} style={btnOutline} download>Export CSV</a>
          <button type="button" style={btnOutline} onClick={() => window.print()}>
            Print / PDF
          </button>
        </div>
      </header>

      {isLoading && <p style={muted}>Loading…</p>}
      {error && (
        <p style={errorStyle}>Couldn't load report — {error}</p>
      )}

      {data && totalKeys.length > 0 && (
        <div style={kpiGrid}>
          {totalKeys.map(k => (
            <div key={k} style={kpiCard}>
              <div style={kpiLabel}>{humanize(k)}</div>
              <div style={kpiValue}>{fmtValue(totals[k])}</div>
            </div>
          ))}
        </div>
      )}

      <div style={filterRow}>
        <span style={muted}>{fmtDate(from)} – {fmtDate(to)}</span>
        {data && (
          <span style={muted}>{rows.length.toLocaleString()} {rows.length === 1 ? "row" : "rows"}</span>
        )}
      </div>

      {data && rows.length === 0 && (
        <p style={muted}>No data in this period.</p>
      )}

      {data && rows.length > 0 && (
        <table style={tableStyle}>
          <thead>
            <tr>
              {rowKeys.map(k => (
                <th key={k} style={{
                  ...thStyle,
                  textAlign: isNumericKey(k, rows[0]) ? "right" : "left",
                }}>
                  {humanize(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {rowKeys.map(k => {
                  const numeric = isNumericKey(k, r);
                  return (
                    <td key={k} style={{
                      ...tdStyle,
                      textAlign: numeric ? "right" : "left",
                      fontFamily: numeric
                        ? "var(--db-font-mono, 'JetBrains Mono', monospace)"
                        : undefined,
                    }}>
                      {fmtCell(k, r[k])}
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

function isNumericKey(key: string, sample: Record<string, unknown>): boolean {
  // Treat as numeric if the sample value is a number or any cell
  // matches /\d/. Lets fallback string "—" co-exist with floats.
  const v = sample?.[key];
  return typeof v === "number";
}

function fmtValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    // Money-ish — single number; print 2-decimal if non-integer.
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  }
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function fmtCell(key: string, v: unknown): React.ReactNode {
  if (v == null) return "—";
  if (typeof v === "number") {
    // Detect money keys by name and prepend $.
    const looksMoney = /amount|sent|revenue|fee|mrr|arr|payout|refund/i.test(key);
    const isPercent  = /pct|percent|rate|fraction/i.test(key);
    const formatted = Number.isInteger(v)
      ? v.toLocaleString()
      : v.toLocaleString(undefined, {
          minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
    if (looksMoney) return `$${formatted}`;
    if (isPercent) return `${(v * (v <= 1 ? 100 : 1)).toFixed(1)}%`;
    return formatted;
  }
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function humanize(s: string): string {
  return s
    .replace(/[_-]/g, " ")
    .replace(/\bmrr\b/gi, "MRR")
    .replace(/\barr\b/gi, "ARR")
    .replace(/\bdau\b/gi, "DAU")
    .replace(/\bmau\b/gi, "MAU")
    .replace(/\b\w/g, c => c.toUpperCase());
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

const pageStyle: React.CSSProperties = {
  flex: 1, padding: "2rem 1.5rem", maxWidth: "75rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: "1.25rem",
};
const backLink: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem",
  textDecoration: "none",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)", fontWeight: 600,
  margin: "0.25rem 0 0",
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
  padding: "0.4rem 0.85rem", borderRadius: "0.5rem",
  fontSize: "0.85rem", cursor: "pointer",
  textDecoration: "none", display: "inline-block",
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
