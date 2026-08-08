import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  CategoryScale, Chart as ChartJS, Filler, LinearScale, LineElement,
  PointElement, Tooltip, BarElement,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";

import { unlinkStore, useOwnerStoreDetail } from "../api/owner";
import { ApiError } from "../lib/api";
import {
  Breadcrumbs, Button,
  Card, ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  Section, TabsBar, TabsButton, Table, tdStyle, thStyle,
} from "../components/ui";
import { chartSeries, chartTokens, moneyChartOptions, seriesFill } from "../lib/chartOptions";
import styles from "./OwnerStoreDetail.module.css";

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

const thStyleR: React.CSSProperties = { ...thStyle, textAlign: "right" };
const tdStyleR: React.CSSProperties = { ...tdStyle, textAlign: "right" };

export default function OwnerStoreDetail() {
  const { storeId } = useParams<{ storeId: string }>();
  const sid = Number(storeId);
  const navigate = useNavigate();
  const [period, setPeriod] = useState<Period>("month");
  const { data, isLoading, isError, error, refetch } = useOwnerStoreDetail(sid, period);

  async function handleUnlink() {
    const name = data?.store?.name ?? `store ${sid}`;
    if (!confirm(`Disconnect "${name}" from your umbrella? The store keeps all its data but you will no longer see it.`)) return;
    try {
      await unlinkStore(sid);
      navigate("/owner/locations");
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Could not unlink store.");
    }
  }

  return (
    <PageShell gap="1.25rem">
      <div>
        <Link to="/owner/locations" className={styles.backLink}>← All locations</Link>

        <Breadcrumbs crumbs={[{ label: "Locations", to: "/owner/locations" }, { label: "Store detail" }]} />

        <PageHeader
          title={data?.store.name || "Store"}
          actions={(
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
              <TabsBar>
                {PERIODS.map((p) => (
                  <TabsButton
                    key={p.value}
                    active={p.value === period}
                    onClick={() => setPeriod(p.value)}
                  >
                    {p.label}
                  </TabsButton>
                ))}
              </TabsBar>
              <Link to={`/owner/store/${sid}/permissions`}>
                <Button size="sm" tone="secondary" type="button">
                  Permissions
                </Button>
              </Link>
              <Button size="sm" tone="secondary" onClick={() => { void handleUnlink(); }}>
                Disconnect store
              </Button>
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
            <Card>
              <div className={styles.chartHost}>
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
                        borderColor: chartSeries().accent,
                        backgroundColor: seriesFill("positive", 0.1),
                        fill: true,
                        tension: 0.25,
                        pointRadius: 0,
                        yAxisID: "y",
                      },
                      {
                        label: "Over/Short ($)",
                        data: data.over_short_data,
                        borderColor: chartSeries().warning,
                        backgroundColor: seriesFill("warning", 0.1),
                        tension: 0.25,
                        pointRadius: 0,
                        yAxisID: "y1",
                      },
                    ],
                  }}
                  options={(() => {
                    // Inline IIFE so the chart tokens are resolved on
                    // every render — picks up theme flips without
                    // re-mounting the route.
                    const t = chartTokens();
                    return {
                      responsive: true,
                      maintainAspectRatio: false,
                      interaction: { mode: "index", intersect: false },
                      plugins: {
                        legend: { labels: { color: t.textMuted } },
                        tooltip: {
                          mode: "index",
                          intersect: false,
                          backgroundColor: t.surface2,
                          titleColor: t.text,
                          bodyColor: t.text,
                          borderColor: t.border,
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
                            color: t.textMuted,
                            callback: (v) => `$${(typeof v === "number" ? v : Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                          },
                          grid: { color: t.borderSubtle },
                        },
                        y1: {
                          position: "right",
                          beginAtZero: true,
                          ticks: {
                            color: t.textMuted,
                            callback: (v) => `$${(typeof v === "number" ? v : Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
                          },
                          grid: { drawOnChartArea: false },
                        },
                        x: {
                          ticks: { color: t.textMuted, maxRotation: 0, autoSkip: true },
                          grid: { color: t.borderSubtle },
                        },
                      },
                    };
                  })()}
                />
              </div>
            </Card>
          </Section>

          {data.company_rows.length > 0 && (
            <Section title="Company breakdown">
              <Card>
                <div className={styles.chartHostShort}>
                  <Bar
                    data={{
                      labels: data.company_rows.map((c) => c.company),
                      datasets: [{
                        label: "Volume ($)",
                        data: data.company_rows.map((c) => c.volume),
                        backgroundColor: seriesFill("positive", 0.5),
                      }],
                    }}
                    options={moneyChartOptions("Volume")}
                  />
                </div>
                <Table>
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
                </Table>
              </Card>
            </Section>
          )}

          <Section title="Recent transfers">
            <Card>
              {data.recent_transfers.length === 0 ? (
                <p className={styles.muted}>No transfers yet for this store.</p>
              ) : (
                <Table>
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
                </Table>
              )}
            </Card>
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
    <span className={delta >= 0 ? styles.deltaPos : styles.deltaNeg}>
      {sign} {prefix}{Math.abs(Math.round(delta)).toLocaleString()}{suffix}
    </span>
  );
}
