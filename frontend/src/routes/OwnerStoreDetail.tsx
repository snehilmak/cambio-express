import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CategoryScale, Chart as ChartJS, Filler, LinearScale, LineElement,
  PointElement, Tooltip, BarElement,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

import { useOwnerStoreDetail } from "../api/owner";
import {
  ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  Section, tdStyle, thStyle, tokens,
} from "../components/ui";
import { moneyChartOptions } from "../lib/chartOptions";

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
  const { data, isLoading, isError, error, refetch } = useOwnerStoreDetail(sid, period);

  return (
    <PageShell maxWidth="75rem" gap="1.25rem">
      <div>
        <Link to="/owner/locations" style={backLink}>← All locations</Link>
        <PageHeader
          title={data?.store.name || "Store"}
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
      </div>

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={`Couldn't load store — ${error instanceof Error ? error.message : "unknown"}`}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <KpiGrid minWidth="180px">
            <KpiCard
              label="Transfers"
              value={data.period_count.toLocaleString()}
              sub={fmtDelta(data.period_count - data.prev_count, "", " vs prior")}
            />
            <KpiCard
              label="Volume"
              value={`$${Math.round(data.period_volume).toLocaleString()}`}
              sub={fmtDelta(data.period_volume - data.prev_volume, "$", " vs prior")}
            />
            <KpiCard label="Fees" value={`$${data.period_fees.toFixed(2)}`} />
            <KpiCard label="Federal Tax" value={`$${data.period_tax.toFixed(2)}`} />
            <KpiCard
              label="Over/Short"
              value={`${data.period_over_short >= 0 ? "+" : "-"}$${Math.abs(data.period_over_short).toFixed(2)}`}
              tone={data.period_over_short < 0 ? "negative" : "neutral"}
            />
          </KpiGrid>

          <Section title="30-day daily receipts vs over/short">
            <div style={chartCard}>
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
                    interaction: { mode: "index", intersect: false },
                    plugins: {
                      legend: { labels: { color: "#a3a3a3" } },
                      tooltip: {
                        mode: "index",
                        intersect: false,
                        backgroundColor: "#141414",
                        titleColor: "#f5f5f5",
                        bodyColor: "#f5f5f5",
                        borderColor: "#262626",
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 8,
                        callbacks: {
                          label: (ctx) => {
                            const y = (ctx.parsed as { y?: number | null }).y ?? 0;
                            const lbl = ctx.dataset.label || "";
                            return `${lbl}: $${y.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
                          },
                        },
                      },
                    },
                    scales: {
                      y: {
                        beginAtZero: true,
                        ticks: {
                          color: "#a3a3a3",
                          callback: (v) => `$${(typeof v === "number" ? v : Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                        },
                        grid: { color: "#1f1f1f" },
                      },
                      y1: {
                        position: "right",
                        beginAtZero: true,
                        ticks: {
                          color: "#a3a3a3",
                          callback: (v) => `$${(typeof v === "number" ? v : Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                        },
                        grid: { drawOnChartArea: false },
                      },
                      x: {
                        ticks: { color: "#a3a3a3", maxRotation: 0, autoSkip: true },
                        grid: { color: "#1f1f1f" },
                      },
                    },
                  }}
                />
              </div>
            </div>
          </Section>

          {data.company_rows.length > 0 && (
            <Section title="Company breakdown">
              <div style={chartCard}>
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
                    options={moneyChartOptions("Volume")}
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
              </div>
            </Section>
          )}

          <Section title="Recent transfers">
            <div style={chartCard}>
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
            </div>
          </Section>
        </>
      )}
    </PageShell>
  );
}

function fmtDelta(
  delta: number,
  prefix: string,
  suffix: string,
): React.ReactNode {
  const sign = delta >= 0 ? "▲" : "▼";
  return (
    <span style={{ color: delta >= 0 ? tokens.accent : tokens.negative }}>
      {sign} {prefix}{Math.abs(Math.round(delta)).toLocaleString()}{suffix}
    </span>
  );
}

const backLink: React.CSSProperties = {
  fontSize: "0.85rem", color: tokens.textMuted,
  textDecoration: "none", display: "block", marginBottom: "0.5rem",
};
const tabBar: React.CSSProperties = {
  display: "flex", border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem", overflow: "hidden",
};
const tab: React.CSSProperties = {
  padding: "0.4rem 0.85rem", background: "transparent", color: "inherit",
  border: "none", cursor: "pointer", fontSize: "0.85rem",
};
const tabActive: React.CSSProperties = {
  ...tab, background: tokens.accent, color: "#000", fontWeight: 600,
};
const chartCard: React.CSSProperties = {
  background: tokens.surface2,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.75rem", padding: "1.25rem",
};
const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", fontSize: "0.9rem",
};
const thStyleR: React.CSSProperties = { ...thStyle, textAlign: "right" };
const tdStyleR: React.CSSProperties = { ...tdStyle, textAlign: "right" };
const muted: React.CSSProperties = {
  color: tokens.textMuted, margin: 0,
};
