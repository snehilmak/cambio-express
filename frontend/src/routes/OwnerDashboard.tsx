import { useState } from "react";
import { Link } from "react-router-dom";
import {
  CategoryScale, Chart as ChartJS, Filler, LinearScale, LineElement,
  PointElement, Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import { useOwnerDashboard } from "../api/owner";
import {
  Breadcrumbs,
  Card, ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  Section, TabsBar, TabsButton, Table, tdStyle, thStyle,
  Empty,
} from "../components/ui";
import { chartSeries, moneyChartOptions, seriesFill } from "../lib/chartOptions";
import { fmtMoney2 } from "../lib/formatters";
import styles from "./OwnerDashboard.module.css";

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip,
);

type Period = "today" | "month" | "year";

const PERIODS: Array<{ value: Period; label: string }> = [
  { value: "today", label: "Today" },
  { value: "month", label: "This Month" },
  { value: "year",  label: "This Year" },
];

const thStyleR: React.CSSProperties = { ...thStyle, textAlign: "right" };
const tdStyleR: React.CSSProperties = { ...tdStyle, textAlign: "right" };

export default function OwnerDashboard() {
  const [period, setPeriod] = useState<Period>("month");
  const { data, isLoading, isError, error, refetch } = useOwnerDashboard(period);

  return (
    <PageShell gap="1.25rem">

      <Breadcrumbs crumbs={[{ label: "Owner dashboard" }]} />

      <PageHeader
        title="Owner Dashboard"
        actions={(
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
              <Card>
                <div className={styles.chartHost}>
                  <Line
                    data={{
                      labels: data.series_labels,
                      datasets: [{
                        label: "Volume ($)",
                        data: data.series_volume,
                        borderColor: chartSeries().accent,
                        backgroundColor: seriesFill("positive", 0.1),
                        fill: true,
                        tension: 0.25,
                        pointRadius: 0,
                      }],
                    }}
                    options={moneyChartOptions("Volume")}
                  />
                </div>
              </Card>
            </Section>
          )}

          <Section title="Stores">
            <div className={styles.storeGrid}>
              {data.stores.map((s) => (
                <Link key={s.id} to={`/owner/store/${s.id}`} className={styles.storeCard}>
                  <div className={styles.storeName}>{s.name}</div>
                  <div className={styles.storeMeta}>
                    {s.count.toLocaleString()} transfers ·{" "}
                    ${Math.round(s.volume).toLocaleString()}
                  </div>
                  <div className={styles.storeOver}>
                    {s.over_short >= 0 ? "+" : "-"}{fmtMoney2(Math.abs(s.over_short))} over/short
                  </div>
                </Link>
              ))}
              {data.stores.length === 0 && (
                <Empty>No stores linked yet.</Empty>
              )}
            </div>
          </Section>

          {data.company_breakdown.length > 0 && (
            <Section title={`Company breakdown (${data.prev_label})`}>
              <Table>
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
              </Table>
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
    <span className={delta >= 0 ? styles.deltaPos : styles.deltaNeg}>
      {sign} {prefix}{Math.abs(Math.round(delta)).toLocaleString()}{suffix}
    </span>
  );
}
