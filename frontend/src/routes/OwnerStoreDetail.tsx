import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CategoryScale, Chart as ChartJS, Filler, LinearScale, LineElement,
  PointElement, Tooltip, BarElement,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

import { useOwnerStoreDetail } from "../api/owner";

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip,
  BarElement,
);

type Period = "today" | "month" | "year";

const PERIODS: Array<{ value: Period; label: string }> = [
  { value: "today", label: "Today" },
  { value: "month", label: "This Month" },
  { value: "year",  label: "This Year" },
];

export default function OwnerStoreDetail() {
  const { storeId } = useParams<{ storeId: string }>();
  const sid = Number(storeId);
  const [period, setPeriod] = useState<Period>("month");
  const { data, isLoading, isError, error } = useOwnerStoreDetail(sid, period);

  return (
    <main style={pageStyle}>
      <header style={headerRow}>
        <div>
          <Link to="/owner/locations" style={backLink}>← All locations</Link>
          <h1 style={titleStyle}>{data?.store.name || "Store"}</h1>
        </div>
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

      {isLoading && <p style={muted}>Loading…</p>}
      {isError && (
        <p style={errorStyle}>
          Couldn't load store — {error instanceof Error ? error.message : "unknown"}
        </p>
      )}

      {data && (
        <>
          <div style={kpiGrid}>
            <Kpi
              label="Transfers"
              value={data.period_count.toLocaleString()}
              delta={data.period_count - data.prev_count}
              deltaSuffix=" vs prior"
            />
            <Kpi
              label="Volume"
              value={`$${Math.round(data.period_volume).toLocaleString()}`}
              delta={data.period_volume - data.prev_volume}
              deltaPrefix="$"
              deltaSuffix=" vs prior"
            />
            <Kpi label="Fees" value={`$${data.period_fees.toFixed(2)}`} />
            <Kpi label="Federal Tax" value={`$${data.period_tax.toFixed(2)}`} />
            <Kpi
              label="Over/Short"
              value={`${data.period_over_short >= 0 ? "+" : "-"}$${Math.abs(data.period_over_short).toFixed(2)}`}
              negative={data.period_over_short < 0}
            />
          </div>

          <section style={cardStyle}>
            <h2 style={cardTitle}>30-day daily receipts vs over/short</h2>
            <div style={{ height: 280 }}>
              <Line
                data={{
                  labels: data.daily_labels.map((d) =>
                    new Date(d + "T00:00:00").toLocaleDateString(undefined, {
                      month: "numeric", day: "numeric",
                    }),
                  ),
                  datasets: [
                    {
                      label: "Receipts ($)",
                      data: data.receipts_data,
                      borderColor: "#3fff00",
                      backgroundColor: "rgba(63,255,0,0.1)",
                      fill: true,
                      tension: 0.25,
                      pointRadius: 0,
                      yAxisID: "y",
                    },
                    {
                      label: "Over/Short ($)",
                      data: data.over_short_data,
                      borderColor: "#ff9500",
                      backgroundColor: "rgba(255,149,0,0.1)",
                      tension: 0.25,
                      pointRadius: 0,
                      yAxisID: "y1",
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { labels: { color: "#a3a3a3" } },
                    tooltip: { mode: "index" },
                  },
                  scales: {
                    y: { ticks: { color: "#a3a3a3" }, grid: { color: "#1f1f1f" } },
                    y1: {
                      position: "right",
                      ticks: { color: "#a3a3a3" },
                      grid: { drawOnChartArea: false },
                    },
                    x: { ticks: { color: "#a3a3a3" }, grid: { color: "#1f1f1f" } },
                  },
                }}
              />
            </div>
          </section>

          {data.company_rows.length > 0 && (
            <section style={cardStyle}>
              <h2 style={cardTitle}>Company breakdown</h2>
              <div style={{ height: 220, marginBottom: "1rem" }}>
                <Bar
                  data={{
                    labels: data.company_rows.map((c) => c.company),
                    datasets: [{
                      label: "Volume ($)",
                      data: data.company_rows.map((c) => c.volume),
                      backgroundColor: "rgba(63,255,0,0.5)",
                    }],
                  }}
                  options={{
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                      y: { ticks: { color: "#a3a3a3" }, grid: { color: "#1f1f1f" } },
                      x: { ticks: { color: "#a3a3a3" }, grid: { color: "#1f1f1f" } },
                    },
                  }}
                />
              </div>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Company</th>
                    <th style={thStyleR}>Transfers</th>
                    <th style={thStyleR}>Volume</th>
                    <th style={thStyleR}>Fees</th>
                    <th style={thStyleR}>Tax</th>
                  </tr>
                </thead>
                <tbody>
                  {data.company_rows.map((c) => (
                    <tr key={c.company}>
                      <td style={tdStyle}>{c.company}</td>
                      <td style={tdStyleR}>{c.count.toLocaleString()}</td>
                      <td style={tdStyleR}>${c.volume.toFixed(2)}</td>
                      <td style={tdStyleR}>${c.fees.toFixed(2)}</td>
                      <td style={tdStyleR}>${c.tax.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section style={cardStyle}>
            <h2 style={cardTitle}>Recent transfers</h2>
            {data.recent_transfers.length === 0 ? (
              <p style={muted}>No transfers yet for this store.</p>
            ) : (
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Date</th>
                    <th style={thStyle}>Sender</th>
                    <th style={thStyle}>Recipient</th>
                    <th style={thStyle}>Co.</th>
                    <th style={thStyleR}>Amount</th>
                    <th style={thStyle}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_transfers.map((t) => (
                    <tr key={t.id}>
                      <td style={tdStyle}>
                        {new Date(t.send_date + "T00:00:00").toLocaleDateString(undefined, { month: "2-digit", day: "2-digit" })}
                      </td>
                      <td style={tdStyle}>{t.sender_name || "—"}</td>
                      <td style={tdStyle}>{t.recipient_name || "—"}</td>
                      <td style={tdStyle}>{t.company || "—"}</td>
                      <td style={tdStyleR}>${t.send_amount.toFixed(2)}</td>
                      <td style={tdStyle}>{t.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
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
          {delta >= 0 ? "▲" : "▼"} {deltaPrefix}{Math.abs(Math.round(delta)).toLocaleString()}{deltaSuffix}
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
  alignItems: "flex-start", gap: "1rem", flexWrap: "wrap",
};
const backLink: React.CSSProperties = {
  fontSize: "0.85rem", color: "var(--db-text-muted, #a3a3a3)",
  textDecoration: "none", display: "block", marginBottom: "0.5rem",
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
  padding: "0.4rem 0.85rem", background: "transparent", color: "inherit",
  border: "none", cursor: "pointer", fontSize: "0.85rem",
};
const tabActive: React.CSSProperties = {
  ...tab, background: "var(--db-accent, #3fff00)", color: "#000", fontWeight: 600,
};
const kpiGrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
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
  fontSize: "1.5rem", fontWeight: 700, marginTop: "0.5rem",
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
const errorStyle: React.CSSProperties = {
  color: "var(--db-negative, #ff3b30)",
  background: "rgba(255,59,48,0.08)",
  border: "1px solid rgba(255,59,48,0.4)",
  padding: "0.75rem 1rem", borderRadius: "0.5rem",
};
