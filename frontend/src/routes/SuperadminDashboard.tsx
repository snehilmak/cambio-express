import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  BarElement,
  ArcElement,
} from "chart.js";
import { Bar, Doughnut, Line } from "react-chartjs-2";

import {
  useSuperadminDashboard,
  type ActivityEntry,
  type VolumeByCompany,
} from "../api/superadmin";
import { chartTokens, countChartOptions, moneyChartOptions } from "../lib/chartOptions";
import {
  Breadcrumbs,
  Card,
  ErrorState,
  KpiCard,
  KpiGrid,
  Loading,
  PageHeader,
  PageShell,
  Pill,
  Section,
} from "../components/ui";
import styles from "./SuperadminDashboard.module.css";

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Filler, Legend, Title, Tooltip,
);

function fmtMoney(n: number): string {
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtDate(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
    });
  } catch { return iso; }
}

function fmtDateTime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function SuperadminDashboard() {
  const { data, isLoading, isError, error, refetch } = useSuperadminDashboard();

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Dashboard" }]} />

      <PageHeader
        title="Platform Dashboard"
        subtitle="Real-time overview of all stores, revenue, and activity"
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load dashboard"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <KpiGrid>
            <KpiCard
              label="Total stores"
              value={data.total_stores.toLocaleString()}
            />
            <KpiCard
              label="Active stores"
              value={data.active_count.toLocaleString()}
              tone="accent"
            />
            <KpiCard
              label="Trial stores"
              value={data.trial_count.toLocaleString()}
              tone="warning"
            />
            <KpiCard
              label="Paid stores"
              value={data.paid_count.toLocaleString()}
              tone="accent"
            />
            <KpiCard
              label="MRR"
              value={fmtMoney(data.estimated_mrr)}
              tone="accent"
            />
            <KpiCard
              label="New (30d)"
              value={`${data.new_stores_30d}`}
              detail={
                data.new_stores_delta >= 0
                  ? `+${data.new_stores_delta} vs prior 30d`
                  : `${data.new_stores_delta} vs prior 30d`
              }
              tone={data.new_stores_delta >= 0 ? "accent" : "negative"}
            />
            <KpiCard
              label="Churn (30d)"
              value={`${data.churn_30d}`}
              detail={
                data.churn_delta <= 0
                  ? `${data.churn_delta} vs prior 30d`
                  : `+${data.churn_delta} vs prior 30d`
              }
              tone={data.churn_delta <= 0 ? "accent" : "negative"}
            />
            <KpiCard
              label="30d volume"
              value={fmtMoney(data.total_volume_30d)}
              detail={`${data.total_transfers_30d.toLocaleString()} transfers`}
            />
          </KpiGrid>

          <div className={styles.chartRow}>
            <Section title="Signup trend (90 days)">
              <Card>
                <div className={styles.chartWrap}>
                  <SignupChart
                    labels={data.signup_labels}
                    direct={data.signup_direct}
                    referral={data.signup_referral}
                  />
                </div>
              </Card>
            </Section>

            <Section title="Plan breakdown">
              <Card>
                <div className={styles.chartWrap}>
                  <PlanDoughnut
                    trial={data.trial_count}
                    basic={data.basic_count}
                    pro={data.pro_count}
                    inactive={data.inactive_count}
                  />
                </div>
              </Card>
            </Section>
          </div>

          <div className={styles.chartRow}>
            <Section title="Transfer volume by company (30d)">
              <Card>
                <div className={styles.chartWrap}>
                  <VolumeBar rows={data.volume_by_company} />
                </div>
              </Card>
            </Section>

            <Section title="MRR breakdown">
              <Card>
                <div className={styles.mrrGrid}>
                  <MrrRow label="Basic monthly" count={data.basic_monthly} mrr={data.basic_monthly_mrr} />
                  <MrrRow label="Basic yearly" count={data.basic_yearly} mrr={data.basic_yearly_mrr} />
                  <MrrRow label="Pro monthly" count={data.pro_monthly} mrr={data.pro_monthly_mrr} />
                  <MrrRow label="Pro yearly" count={data.pro_yearly} mrr={data.pro_yearly_mrr} />
                  <div className={styles.mrrTotal}>
                    <span>Total MRR</span>
                    <span className={styles.mrrTotalValue}>{fmtMoney(data.estimated_mrr)}</span>
                  </div>
                </div>
              </Card>
            </Section>
          </div>

          <Section title="Recent activity">
            <Card>
              {data.activity.length === 0 ? (
                <p className={styles.emptyText}>No recent activity.</p>
              ) : (
                <div className={styles.activityList}>
                  {data.activity.map((a, i) => (
                    <ActivityRow key={i} entry={a} />
                  ))}
                </div>
              )}
            </Card>
          </Section>
        </>
      )}
    </PageShell>
  );
}


function SignupChart({
  labels, direct, referral,
}: {
  labels: string[];
  direct: number[];
  referral: number[];
}) {
  const t = chartTokens();
  const shortLabels = labels.map((l) => fmtDate(l));
  return (
    <Line
      data={{
        labels: shortLabels,
        datasets: [
          {
            label: "Direct",
            data: direct,
            borderColor: "#3fff00",
            backgroundColor: "rgba(63, 255, 0, 0.1)",
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
          {
            label: "Referral",
            data: referral,
            borderColor: "#00bfff",
            backgroundColor: "rgba(0, 191, 255, 0.08)",
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
        ],
      }}
      options={{
        ...countChartOptions("Signups"),
        plugins: {
          ...countChartOptions("Signups").plugins,
          legend: {
            display: true,
            labels: { color: t.textMuted, boxWidth: 12 },
          },
        },
      }}
    />
  );
}


function PlanDoughnut({
  trial, basic, pro, inactive,
}: {
  trial: number; basic: number; pro: number; inactive: number;
}) {
  const t = chartTokens();
  return (
    <Doughnut
      data={{
        labels: ["Trial", "Basic", "Pro", "Inactive"],
        datasets: [{
          data: [trial, basic, pro, inactive],
          backgroundColor: [
            "#f59e0b",
            "#3fff00",
            "#00bfff",
            "#6b7280",
          ],
          borderColor: "transparent",
          borderWidth: 0,
        }],
      }}
      options={{
        responsive: true,
        maintainAspectRatio: false,
        cutout: "60%",
        plugins: {
          legend: {
            display: true,
            position: "bottom",
            labels: { color: t.textMuted, padding: 16 },
          },
          tooltip: {
            backgroundColor: t.surface2,
            titleColor: t.text,
            bodyColor: t.text,
            borderColor: t.border,
            borderWidth: 1,
          },
        },
      }}
    />
  );
}


function VolumeBar({ rows }: { rows: VolumeByCompany[] }) {
  const t = chartTokens();
  return (
    <Bar
      data={{
        labels: rows.map((r) => r.company),
        datasets: [{
          label: "Volume",
          data: rows.map((r) => r.total),
          backgroundColor: "rgba(63, 255, 0, 0.6)",
          borderColor: "#3fff00",
          borderWidth: 1,
          borderRadius: 4,
        }],
      }}
      options={{
        ...moneyChartOptions<"bar">("Volume"),
        plugins: {
          ...moneyChartOptions<"bar">("Volume").plugins,
          legend: {
            display: false,
            labels: { color: t.textMuted },
          },
        },
      }}
    />
  );
}


function MrrRow({ label, count, mrr }: { label: string; count: number; mrr: number }) {
  return (
    <div className={styles.mrrRow}>
      <span className={styles.mrrLabel}>{label}</span>
      <span className={styles.mrrCount}>{count} stores</span>
      <span className={styles.mrrValue}>{fmtMoney(mrr)}/mo</span>
    </div>
  );
}


function ActivityRow({ entry: a }: { entry: ActivityEntry }) {
  return (
    <div className={styles.activityRow}>
      <Pill tone={a.kind === "signup" ? "accent" : "negative"}>
        {a.kind}
      </Pill>
      <span className={styles.activityStore}>{a.store_name}</span>
      <span className={styles.activityDetail}>{a.detail}</span>
      <span className={styles.activityTime}>{fmtDateTime(a.when)}</span>
    </div>
  );
}
