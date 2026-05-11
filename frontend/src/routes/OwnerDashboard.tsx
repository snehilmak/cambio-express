import { useState } from "react";
import { Link } from "react-router-dom";
import {
  CategoryScale, Chart as ChartJS, Filler, LinearScale, LineElement,
  PointElement, Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import { useOwnerDashboard } from "../api/owner";
import {
  ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  Section, tdStyle, thStyle, tokens,
} from "../components/ui";
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
    <PageShell maxWidth="75rem" gap="1.25rem">
      <PageHeader
        title="Owner Dashboard"
        actions={(
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
        )}
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={`Couldn't load dashboard — ${error instanceof Error ? error.message : "unknown"}`}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <KpiGrid>
            <KpiCard
              label="Total Transfers"
              value={data.agg_transfers.toLocaleString()}
              sub={fmtDelta(data.agg_transfers_delta, "", "")}
            />
            <KpiCard
              label="Total Volume"
              value={`$${Math.round(data.agg_volume).toLocaleString()}`}
              sub={fmtDelta(data.agg_volume_delta, "$", "")}
            />
            <KpiCard
              label="Net Over/Short"
              value={`${data.agg_over_short >= 0 ? "+" : "-"}$${Math.abs(Math.round(data.agg_over_short)).toLocaleString()}`}
              sub={fmtDelta(data.agg_over_short_delta, "$", "")}
              tone={data.agg_over_short < 0 ? "negative" : "neutral"}
            />
            <KpiCard
              label="Stores"
              value={data.store_count.toLocaleString()}
            />
          </KpiGrid>

          {data.series_labels.length > 0 && (
            <Section title="Volume trend">
              <div style={chartCard}>
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
              </div>
            </Section>
          )}

          <Section title="Stores">
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
          </Section>

          {data.company_breakdown.length > 0 && (
            <Section title={`Company breakdown (${data.prev_label})`}>
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
            </Section>
          )}
        </>
      )}
    </PageShell>
  );
}

function fmtDelta(
  delta: number | undefined,
  prefix: string,
  suffix: string,
): React.ReactNode {
  if (typeof delta !== "number") return undefined;
  const sign = delta >= 0 ? "▲" : "▼";
  return (
    <span style={{ color: delta >= 0 ? tokens.accent : tokens.negative }}>
      {sign} {prefix}{Math.abs(Math.round(delta)).toLocaleString()}{suffix}
    </span>
  );
}

const tabBar: React.CSSProperties = {
  display: "flex", border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem", overflow: "hidden",
};
const tab: React.CSSProperties = {
  padding: "0.4rem 0.85rem", background: "transparent",
  color: "inherit", border: "none", cursor: "pointer", fontSize: "0.85rem",
};
const tabActive: React.CSSProperties = {
  ...tab, background: tokens.accent, color: "#000", fontWeight: 600,
};
const chartCard: React.CSSProperties = {
  background: tokens.surface2,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.75rem", padding: "1.25rem",
};
const storeGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.75rem",
};
const storeCard: React.CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem", padding: "0.85rem 1rem",
  textDecoration: "none", color: "inherit",
};
const storeName: React.CSSProperties = { fontWeight: 600 };
const storeMeta: React.CSSProperties = {
  fontSize: "0.85rem", color: tokens.textMuted,
  marginTop: "0.25rem",
};
const storeOver: React.CSSProperties = {
  fontFamily: tokens.fontMono,
  fontSize: "0.85rem", marginTop: "0.4rem",
  color: tokens.textMuted,
};
const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", fontSize: "0.9rem",
};
const thStyleR: React.CSSProperties = { ...thStyle, textAlign: "right" };
const tdStyleR: React.CSSProperties = { ...tdStyle, textAlign: "right" };
const muted: React.CSSProperties = {
  color: tokens.textMuted, margin: 0,
};
