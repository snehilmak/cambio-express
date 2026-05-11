import { Link } from "react-router-dom";

import { useDashboardSummary } from "../api/dashboard";
import { ErrorState, Loading } from "../components/ui";

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
    <main style={pageStyle}>
      <header>
        <h1 style={titleStyle}>Platform Controls</h1>
        <p style={muted}>
          Stores, billing, anomalies, audit log, announcements, reports.
        </p>
      </header>

      {isLoading && <Loading label="Loading platform metrics…" />}
      {isError && (
        <ErrorState
          message="Couldn't load metrics for the overview."
          onRetry={() => { void refetch(); }}
        />
      )}

      {d && (
        <section style={cardStyle}>
          <h2 style={cardTitle}>Overview</h2>
          <div style={kpiGrid}>
            <Kpi label="Total Stores" value={d.total_stores ?? "—"} />
            <Kpi
              label="Active"
              value={d.active_stores ?? "—"}
              accent="positive"
            />
            <Kpi label="Trial" value={d.trial_stores ?? "—"} accent="warning" />
            <Kpi label="Paid" value={d.paid_stores ?? "—"} accent="positive" />
            <Kpi
              label="Inactive"
              value={d.inactive_stores ?? "—"}
              accent={
                typeof d.inactive_stores === "number" && d.inactive_stores > 0
                  ? "negative"
                  : undefined
              }
            />
            <Kpi
              label="Retention queue"
              value={d.retention_queue ?? "—"}
              accent={
                typeof d.retention_queue === "number" && d.retention_queue > 0
                  ? "warning"
                  : undefined
              }
            />
            <Kpi
              label="MRR"
              value={
                typeof d.mrr_total === "number"
                  ? `$${d.mrr_total.toLocaleString()}`
                  : "—"
              }
            />
            <Kpi
              label="ARR"
              value={
                typeof d.arr_total === "number"
                  ? `$${d.arr_total.toLocaleString()}`
                  : "—"
              }
            />
            <Kpi
              label="New (30d)"
              value={d.new_stores_30d ?? "—"}
              accent="positive"
            />
            <Kpi
              label="Cancellations (30d)"
              value={d.cancellations_30d ?? "—"}
              accent={
                typeof d.cancellations_30d === "number" && d.cancellations_30d > 0
                  ? "negative"
                  : undefined
              }
            />
          </div>
        </section>
      )}

      <section style={cardStyle}>
        <h2 style={cardTitle}>Hubs</h2>
        <div style={quickLinkGrid}>
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
      </section>
    </main>
  );
}

function ComingSoon({ title, desc }: { title: string; desc: string }) {
  return (
    <div style={{ ...quickLink, opacity: 0.6, cursor: "default" }}>
      <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "0.5rem" }}>
        {title}
        <span style={{
          fontSize: "0.65rem", padding: "0.1rem 0.4rem",
          borderRadius: "999px", background: "rgba(255,204,0,0.15)",
          color: "var(--db-warning, #ffcc00)",
        }}>
          Coming soon
        </span>
      </div>
      <div style={muted}>{desc}</div>
    </div>
  );
}

function Kpi({
  label,
  value,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  accent?: "positive" | "negative" | "warning";
}) {
  const color =
    accent === "positive"
      ? "var(--db-positive, #3fff00)"
      : accent === "negative"
        ? "var(--db-negative, #ff3b30)"
        : accent === "warning"
          ? "var(--db-warning, #ffcc00)"
          : "var(--db-info, #5ac8fa)";
  return (
    <div style={{ ...kpiCard, borderTop: `3px solid ${color}` }}>
      <div style={kpiLabel}>{label}</div>
      <div style={kpiValue}>{value}</div>
    </div>
  );
}

function QuickLink({
  to, title, desc,
}: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} style={quickLink}>
      <div style={{ fontWeight: 600 }}>{title}</div>
      <div style={muted}>{desc}</div>
    </Link>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1, padding: "2rem 1.5rem", maxWidth: "75rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: "1.25rem",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)", fontWeight: 600, margin: 0,
};
const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1.25rem",
};
const cardTitle: React.CSSProperties = {
  margin: "0 0 1rem", fontSize: "1rem",
};
const kpiGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "0.75rem",
};
const kpiCard: React.CSSProperties = {
  background: "var(--db-surface-1, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", padding: "0.75rem 1rem",
};
const kpiLabel: React.CSSProperties = {
  fontSize: "0.7rem", textTransform: "uppercase",
  letterSpacing: "0.05em", color: "var(--db-text-muted, #a3a3a3)",
};
const kpiValue: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "1.4rem", fontWeight: 700, marginTop: "0.4rem",
};
const quickLinkGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.75rem",
};
const quickLink: React.CSSProperties = {
  display: "block", padding: "1rem",
  background: "var(--db-surface-1, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", textDecoration: "none", color: "inherit",
};
const muted: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem", margin: 0,
};
