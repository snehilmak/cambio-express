import { useState } from "react";
import { Link } from "react-router-dom";
import {
  CategoryScale, Chart as ChartJS, Filler, LinearScale, LineElement,
  PointElement, Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import { useOwnerDashboard } from "../api/owner";
import { ErrorState, Loading } from "../components/ui";
import { moneyChartOptions } from "../lib/chartOptions";

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip,
);

type Period = "today" | "month" | "year";

const PERIODS: Array<{ value: Period; label: string }> = [
  { value: "today", label: "Today" },
  { value: "month", label: "This Month" },
  { value: "year",  label: "This Year" },
];

export default function OwnerDashboard() {
  const [period, setPeriod] = useState<Period>("month");
  const { data, isLoading, isError, error, refetch } = useOwnerDashboard(period);

  return (
    <main style={pageStyle}>
      <header style={headerRow}>
        <h1 style={titleStyle}>Owner Dashboard</h1>
        <div style={tabBar}>
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setPeriod(p.value)}
              style={p.value === period ? tabActive : tab}
            >
              {p.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={`Couldn't load dashboard — ${error instanceof Error ? error.message : "unknown"}`}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <div style={kpiGrid}>
            <Kpi
              label="Total Transfers"
              value={data.agg_transfers.toLocaleString()}
              delta={data.agg_transfers_delta}
              deltaSuffix=""
            />
            <Kpi
              label="Total Volume"
              value={`$${Math.round(data.agg_volume).toLocaleString()}`}
              delta={data.agg_volume_delta}
              deltaPrefix="$"
            />
            <Kpi
              label="Net Over/Short"
              value={`${data.agg_over_short >= 0 ? "+" : "-"}$${Math.abs(Math.round(data.agg_over_short)).toLocaleString()}`}
              delta={data.agg_over_short_delta}
              deltaPrefix="$"
              negative={data.agg_over_short < 0}
            />
            <Kpi
              label="Stores"
              value={data.store_count.toLocaleString()}
            />
          </div>

          {data.series_labels.length > 0 && (
            <section style={cardStyle}>
              <h2 style={cardTitle}>Volume trend</h2>
              <div style={{ height: 280 }}>
                <Line
                  data={{
                    labels: data.series_labels,
                    datasets: [{
                      label: "Volume ($)",
                      data: data.series_volume,
                      borderColor: "#3fff00",
                      backgroundColor: "rgba(63,255,0,0.1)",
                      fill: true,
                      tension: 0.25,
                      pointRadius: 0,
                    }],
                  }}
                  options={moneyChartOptions("Volume")}
                />
              </div>
            </section>
          )}

          <section style={cardStyle}>
            <h2 style={cardTitle}>Stores</h2>
            <div style={storeGrid}>
              {data.stores.map((s) => (
                <Link key={s.id} to={`/owner/store/${s.id}`} style={storeCard}>
                  <div style={storeName}>{s.name}</div>
                  <div style={storeMeta}>
                    {s.count.toLocaleString()} transfers ·{" "}
                    ${Math.round(s.volume).toLocaleString()}
                  </div>
                  <div style={storeOver}>
                    {s.over_short >= 0 ? "+" : "-"}${Math.abs(s.over_short).toFixed(2)} over/short
                  </div>
                </Link>
              ))}
              {data.stores.length === 0 && (
                <p style={muted}>No stores linked yet.</p>
              )}
            </div>
          </section>

          {data.company_breakdown.length > 0 && (
            <section style={cardStyle}>
              <h2 style={cardTitle}>Company breakdown ({data.prev_label})</h2>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Company</th>
                    <th style={thStyleR}>Transfers</th>
                    <th style={thStyleR}>Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {data.company_breakdown.map((c) => (
                    <tr key={c.company}>
                      <td style={tdStyle}>{c.company}</td>
                      <td style={tdStyleR}>{c.count.toLocaleString()}</td>
                      <td style={tdStyleR}>${Math.round(c.volume).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </main>
  );
}

function Kpi({
  label, value, delta, deltaPrefix = "", deltaSuffix = "", negative,
}: {
  label: string;
  value: string;
  delta?: number;
  deltaPrefix?: string;
  deltaSuffix?: string;
  negative?: boolean;
}) {
  return (
    <div style={kpiCard}>
      <div style={kpiLabel}>{label}</div>
      <div style={{ ...kpiValue, color: negative ? "var(--db-negative, #ff3b30)" : "inherit" }}>
        {value}
      </div>
      {typeof delta === "number" && (
        <div style={{ ...kpiDelta, color: delta >= 0 ? "var(--db-positive, #3fff00)" : "var(--db-negative, #ff3b30)" }}>
          {delta >= 0 ? "▲" : "▼"} {deltaPrefix}
          {Math.abs(Math.round(delta)).toLocaleString()}{deltaSuffix}
        </div>
      )}
    </div>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1, padding: "2rem 1.5rem", maxWidth: "75rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: "1.25rem",
};
const headerRow: React.CSSProperties = {
  display: "flex", justifyContent: "space-between",
  alignItems: "center", gap: "1rem", flexWrap: "wrap",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)", fontWeight: 600, margin: 0,
};
const tabBar: React.CSSProperties = {
  display: "flex", border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", overflow: "hidden",
};
const tab: React.CSSProperties = {
  padding: "0.4rem 0.85rem", background: "transparent",
  color: "inherit", border: "none", cursor: "pointer", fontSize: "0.85rem",
};
const tabActive: React.CSSProperties = {
  ...tab, background: "var(--db-accent, #3fff00)", color: "#000", fontWeight: 600,
};
const kpiGrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "1rem",
};
const kpiCard: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1rem 1.25rem",
};
const kpiLabel: React.CSSProperties = {
  fontSize: "0.75rem", textTransform: "uppercase",
  letterSpacing: "0.05em", color: "var(--db-text-muted, #a3a3a3)",
};
const kpiValue: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "1.6rem", fontWeight: 700, marginTop: "0.5rem",
};
const kpiDelta: React.CSSProperties = {
  fontSize: "0.8rem", marginTop: "0.4rem",
};
const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1.25rem",
};
const cardTitle: React.CSSProperties = {
  margin: "0 0 1rem", fontSize: "1rem",
};
const storeGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.75rem",
};
const storeCard: React.CSSProperties = {
  background: "var(--db-surface-1, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", padding: "0.85rem 1rem",
  textDecoration: "none", color: "inherit",
};
const storeName: React.CSSProperties = { fontWeight: 600 };
const storeMeta: React.CSSProperties = {
  fontSize: "0.85rem", color: "var(--db-text-muted, #a3a3a3)",
  marginTop: "0.25rem",
};
const storeOver: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.85rem", marginTop: "0.4rem",
  color: "var(--db-text-muted, #a3a3a3)",
};
const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", fontSize: "0.9rem",
};
const thStyle: React.CSSProperties = {
  textAlign: "left", padding: "0.5rem 0.75rem",
  fontSize: "0.7rem", textTransform: "uppercase",
  color: "var(--db-text-muted, #a3a3a3)",
  borderBottom: "1px solid var(--db-border, #262626)",
};
const thStyleR: React.CSSProperties = { ...thStyle, textAlign: "right" };
const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};
const tdStyleR: React.CSSProperties = { ...tdStyle, textAlign: "right" };
const muted: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)", margin: 0,
};
