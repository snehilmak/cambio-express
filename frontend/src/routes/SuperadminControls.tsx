import { Link } from "react-router-dom";

import { useDashboardSummary } from "../api/dashboard";
import {
  Breadcrumbs,
  ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell, Section,
} from "../components/ui";
import styles from "./SuperadminControls.module.css";

// /app/superadmin/controls — Platform hub. KPI tiles fed by the
// existing /api/v2/dashboard/summary (superadmin-shaped payload),
// plus quick links into the dedicated SPA routes that already
// exist for Stores, Audit Log, Announcements, and Reports.
//
// Discounts + Feature Flags + TV catalog curation tabs from the
// legacy Jinja page haven't been ported to dedicated SPA routes
// yet — their POST mutation endpoints stay live on Flask, but the
// edit UI is deferred to a follow-up. Discounts links to the
// legacy /superadmin/discounts (still on Flask) for now; same for
// /superadmin/features.

interface SuperadminLite {
  total_stores?: number;
  active_stores?: number;
  trial_stores?: number;
  paid_stores?: number;
  inactive_stores?: number;
  mrr_total?: number;
  arr_total?: number;
  new_stores_30d?: number;
  cancellations_30d?: number;
  retention_queue?: number;
  [key: string]: unknown;
}

export default function SuperadminControls() {
  const { data, isLoading, isError, refetch } = useDashboardSummary();
  const d = (data && (data as SuperadminLite & { role: string }).role === "superadmin"
    ? (data as SuperadminLite)
    : null);

  return (
    <PageShell gap="1.25rem">

      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Controls" }]} />

      <PageHeader
        title="Platform Controls"
        subtitle="Stores, billing, anomalies, audit log, announcements, reports."
      />

      {isLoading && <Loading label="Loading platform metrics…" />}
      {isError && (
        <ErrorState
          message="Couldn't load metrics for the overview."
          onRetry={() => { void refetch(); }}
        />
      )}

      {d && (
        <Section title="Overview">
          <KpiGrid minWidth="180px">
            <KpiCard
              label="Total Stores"
              value={fmt(d.total_stores)}
              tone="primary"
            />
            <KpiCard
              label="Active"
              value={fmt(d.active_stores)}
              tone="positive"
            />
            <KpiCard label="Trial" value={fmt(d.trial_stores)} tone="warning" />
            <KpiCard label="Paid" value={fmt(d.paid_stores)} tone="positive" />
            <KpiCard
              label="Inactive"
              value={fmt(d.inactive_stores)}
              tone={
                typeof d.inactive_stores === "number" && d.inactive_stores > 0
                  ? "negative"
                  : "primary"
              }
            />
            <KpiCard
              label="Retention queue"
              value={fmt(d.retention_queue)}
              tone={
                typeof d.retention_queue === "number" && d.retention_queue > 0
                  ? "warning"
                  : "primary"
              }
            />
            <KpiCard
              label="MRR"
              value={
                typeof d.mrr_total === "number"
                  ? `$${d.mrr_total.toLocaleString()}`
                  : "—"
              }
              tone="primary"
            />
            <KpiCard
              label="ARR"
              value={
                typeof d.arr_total === "number"
                  ? `$${d.arr_total.toLocaleString()}`
                  : "—"
              }
              tone="primary"
            />
            <KpiCard
              label="New (30d)"
              value={fmt(d.new_stores_30d)}
              tone="positive"
            />
            <KpiCard
              label="Cancellations (30d)"
              value={fmt(d.cancellations_30d)}
              tone={
                typeof d.cancellations_30d === "number" && d.cancellations_30d > 0
                  ? "negative"
                  : "primary"
              }
            />
          </KpiGrid>
        </Section>
      )}

      <Section title="Hubs">
        <div className={styles.quickLinkGrid}>
          <QuickLink
            to="/superadmin/stores"
            title="Stores"
            desc="Browse, filter, edit. Per-store impersonate / extend / toggle."
          />
          <QuickLink
            to="/superadmin/audit-log"
            title="Audit Log"
            desc="Every superadmin mutation. Filter by actor / target / action."
          />
          <QuickLink
            to="/superadmin/announcements"
            title="Announcements"
            desc="Global banners + push notifications across every store."
          />
          <QuickLink
            to="/superadmin/reports"
            title="Platform Reports"
            desc="MRR/ARR, churn cohorts, adoption, payouts."
          />
          <ComingSoon
            title="Discounts"
            desc="Coupon codes — issue, toggle, view redemptions. POST endpoints stay on Flask; SPA UI lands in a follow-up."
          />
          <ComingSoon
            title="Feature Flags"
            desc="Platform-wide flags + per-store overrides. POST endpoints stay on Flask; SPA UI lands in a follow-up."
          />
          <ComingSoon
            title="TV Catalogs"
            desc="Curate the company / bank picker for TV displays. POST endpoints stay on Flask; SPA UI lands in a follow-up."
          />
        </div>
      </Section>
    </PageShell>
  );
}

function fmt(n: number | undefined): React.ReactNode {
  return typeof n === "number" ? n.toLocaleString() : "—";
}

function ComingSoon({ title, desc }: { title: string; desc: string }) {
  return (
    <div className={styles.quickLinkDisabled}>
      <div className={styles.quickLinkTitleRow}>
        {title}
        <span className={styles.comingPill}>Coming soon</span>
      </div>
      <div className={styles.muted}>{desc}</div>
    </div>
  );
}

function QuickLink({
  to, title, desc,
}: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} className={styles.quickLink}>
      <div className={styles.quickLinkTitle}>{title}</div>
      <div className={styles.muted}>{desc}</div>
    </Link>
  );
}
