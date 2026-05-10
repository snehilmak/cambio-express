import { Link } from "react-router-dom";

import {
  useDashboardSummary,
  type AdminDashboard,
  type EmployeeDashboard,
  type DashboardSummary,
} from "../api/dashboard";
import { getCurrentIdentity } from "../lib/auth";

// Role-shaped dashboard. /api/v2/dashboard/summary returns one
// payload tagged by role; we render the matching panel.
export default function Dashboard() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error } = useDashboardSummary();

  return (
    <main style={pageStyle}>
      <header>
        <h1 style={titleStyle}>
          {identity?.role === "superadmin"
            ? "Platform Dashboard"
            : identity?.role === "employee"
              ? "My Dashboard"
              : "Admin Dashboard"}
        </h1>
      </header>

      {isLoading && <Empty>Loading dashboard…</Empty>}
      {isError && (
        <Empty error>
          Couldn't load dashboard —{" "}
          {error instanceof Error ? error.message : "unknown error"}
        </Empty>
      )}
      {data && <Body summary={data} />}
    </main>
  );
}

function Body({ summary }: { summary: DashboardSummary }) {
  if (summary.role === "admin") return <AdminPanel d={summary} />;
  if (summary.role === "employee") return <EmployeePanel d={summary} />;
  if (summary.role === "superadmin") return <SuperadminPanel d={summary} />;
  return <Empty>Unrecognised role.</Empty>;
}

// ── Admin ─────────────────────────────────────────────────────

function AdminPanel({ d }: { d: AdminDashboard }) {
  return (
    <>
      <KpiGrid>
        <Kpi label="Total Transfers" value={d.kpis.total_transfers} sub="All time" />
        <Kpi
          label="Today's Transfers"
          value={d.kpis.today_transfers}
          sub={fmtDate(d.today)}
          accent="positive"
        />
        <Kpi
          label="Unreconciled ACH"
          value={d.kpis.pending_ach}
          sub={d.kpis.pending_ach > 0 ? "Needs attention" : "All clear"}
          accent={d.kpis.pending_ach > 0 ? "negative" : "positive"}
        />
        <Kpi
          label="Today's Daily Book"
          value={d.kpis.today_report_entered ? "Entered" : "Pending"}
          sub={
            <Link to="/daily/edit" style={subLink}>
              {d.kpis.today_report_entered ? "Edit report" : "Enter now →"}
            </Link>
          }
          accent={d.kpis.today_report_entered ? "positive" : "warning"}
        />
        <Kpi
          label="Bank Sync"
          value={
            d.stripe_accounts.length > 0
              ? `Stripe · ${d.stripe_accounts.length}`
              : "Not connected"
          }
          sub={
            d.stripe_accounts.length > 0 ? (
              d.stripe_accounts[0].last_balance_as_of ? (
                `Last sync: ${fmtTime(d.stripe_accounts[0].last_balance_as_of)}`
              ) : (
                "—"
              )
            ) : (
              <Link to="/bank-transactions" style={subLink}>Connect via Stripe →</Link>
            )
          }
          accent={d.stripe_accounts.length > 0 ? "positive" : "negative"}
        />
        {d.kpis.net_income_month != null && (
          <Kpi
            label={`Net Income (${monthShort(d.today)})`}
            value={`$${Math.round(d.kpis.net_income_month).toLocaleString()}`}
            sub={
              <Link to="/monthly" style={subLink}>
                View P&amp;L →
              </Link>
            }
            accent={d.kpis.net_income_month >= 0 ? "positive" : "negative"}
          />
        )}
      </KpiGrid>

      <Section title="This Month by Company">
        <div style={gridThree}>
          {d.company_stats.map((c) => (
            <Card key={c.company}>
              <header style={cardHeader}>
                <span style={{ fontWeight: 600 }}>{c.company}</span>
                <span style={badgeNavy}>{c.count} transfers</span>
              </header>
              <div style={{ ...moneyValue, fontSize: "1.6rem" }}>
                ${c.total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div style={textMuted}>
                Fees: ${c.fees.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </Card>
          ))}
          {d.company_stats.length === 0 && (
            <Empty>No companies enabled for this store yet.</Empty>
          )}
        </div>
      </Section>

      <div style={gridTwo}>
        <Card>
          <header style={cardHeader}>
            <span style={{ fontWeight: 600 }}>Recent Transfers</span>
            <Link to="/transfers" style={btnOutline}>View All</Link>
          </header>
          <Table
            head={["Date", "Sender", "Co.", "Amount", "Status"]}
            rows={d.recent_transfers.map((t) => [
              shortDate(t.send_date),
              t.sender_name,
              t.company.slice(0, 5),
              `$${t.send_amount.toFixed(2)}`,
              <StatusBadge key={t.id} value={t.status} />,
            ])}
            empty="No transfers yet"
          />
        </Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <Card>
            <header style={cardHeader}>
              <span style={{ fontWeight: 600 }}>Recent ACH Batches</span>
              <Link to="/batches" style={btnOutline}>View All</Link>
            </header>
            <Table
              head={["Date", "Co.", "ACH Amt", "Variance", "Status"]}
              rows={d.recent_batches.map((b) => [
                shortDate(b.ach_date),
                b.company.slice(0, 5),
                `$${b.ach_amount.toFixed(2)}`,
                b.variance === 0 ? "✓ $0" : `$${b.variance.toFixed(2)}`,
                <StatusBadge key={b.id} value={b.status} />,
              ])}
              empty="No batches yet"
            />
          </Card>
          <Card>
            <header style={cardHeader}>
              <span style={{ fontWeight: 600 }}>Bank Accounts</span>
              <Link to="/bank-transactions" style={btnOutline}>Full View</Link>
            </header>
            {d.stripe_accounts.length === 0 ? (
              <Empty>No bank connected yet.</Empty>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {d.stripe_accounts.map((a) => (
                  <div key={a.id} style={bankRow}>
                    <div>
                      <div style={{ fontWeight: 600 }}>
                        {a.display_name || "Account"}
                        {a.last4 ? ` ••${a.last4}` : ""}
                      </div>
                      <div style={textMuted}>{a.institution_name || "—"}</div>
                    </div>
                    <div style={moneyValue}>
                      ${a.last_balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

// ── Employee ──────────────────────────────────────────────────

function EmployeePanel({ d }: { d: EmployeeDashboard }) {
  return (
    <>
      <KpiGrid>
        <Kpi
          label="Today's Transfers"
          value={d.totals.count}
          sub={fmtDate(d.today)}
        />
      </KpiGrid>

      <Section title="Today's Transfers" right={
        <Link to="/transfers/new" style={btnPrimary}>＋ Log New Transfer</Link>
      }>
        <Card>
          <Table
            head={["Time", "Sender", "Company", "Amount", "Fee", "Recipient", "Country", "Confirm #", "Status", ""]}
            rows={d.today_transfers.map((t) => [
              t.created_at ? shortTime(t.created_at) : "—",
              t.sender_name,
              t.company,
              `$${t.send_amount.toFixed(2)}`,
              `$${t.fee.toFixed(2)}`,
              t.recipient_name || "—",
              t.country || "—",
              t.confirm_number || "—",
              <StatusBadge key={t.id} value={t.status} />,
              <Link key={`edit-${t.id}`} to={`/transfers/${t.id}/edit`} style={btnSm}>Edit</Link>,
            ])}
            empty="Nothing logged today — log the first one to get started."
          />
        </Card>
      </Section>

      {d.totals.count > 0 && (
        <div style={{ ...rowSummary }}>
          <div>
            <span style={textMuted}>Today Total Sent: </span>
            <strong style={moneyValue}>
              ${d.totals.sent.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </strong>
          </div>
          <div>
            <span style={textMuted}>Fees Collected: </span>
            <strong style={moneyValue}>
              ${d.totals.fees.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </strong>
          </div>
          <div>
            <span style={textMuted}>Transfers: </span>
            <strong>{d.totals.count}</strong>
          </div>
        </div>
      )}
    </>
  );
}

// ── Superadmin ────────────────────────────────────────────────

interface SuperadminContextLite {
  total_stores?: number;
  active_stores?: number;
  trial_stores?: number;
  paid_stores?: number;
  inactive_stores?: number;
  mrr_total?: number;
  arr_total?: number;
  new_stores_30d?: number;
  cancellations_30d?: number;
  [key: string]: unknown;
}

function SuperadminPanel({ d }: { d: SuperadminContextLite & { role: string } }) {
  return (
    <>
      <KpiGrid>
        <Kpi label="Total Stores" value={d.total_stores ?? "—"} sub="All time" />
        <Kpi label="Active" value={d.active_stores ?? "—"} accent="positive" />
        <Kpi label="Trial" value={d.trial_stores ?? "—"} accent="warning" />
        <Kpi label="Paid" value={d.paid_stores ?? "—"} accent="positive" />
        <Kpi
          label="MRR"
          value={
            typeof d.mrr_total === "number"
              ? `$${d.mrr_total.toLocaleString()}`
              : "—"
          }
          accent="positive"
        />
        <Kpi
          label="ARR"
          value={
            typeof d.arr_total === "number"
              ? `$${d.arr_total.toLocaleString()}`
              : "—"
          }
          accent="positive"
        />
        <Kpi label="New (30d)" value={d.new_stores_30d ?? "—"} accent="positive" />
        <Kpi
          label="Cancellations (30d)"
          value={d.cancellations_30d ?? "—"}
          accent={
            typeof d.cancellations_30d === "number" && d.cancellations_30d > 0
              ? "negative"
              : "positive"
          }
        />
      </KpiGrid>
      <Section title="Quick links">
        <div style={gridThree}>
          <QuickLink to="/superadmin/stores" title="Stores" desc="Browse, edit, impersonate." />
          <QuickLink to="/superadmin/audit-log" title="Audit Log" desc="Every superadmin mutation." />
          <QuickLink to="/superadmin/announcements" title="Announcements" desc="Global banners + push." />
          <QuickLink to="/superadmin/reports" title="Platform Reports" desc="MRR/ARR, churn, adoption." />
        </div>
      </Section>
    </>
  );
}

function QuickLink({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} style={{ ...quickLink, textDecoration: "none" }}>
      <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>{title}</div>
      <div style={textMuted}>{desc}</div>
    </Link>
  );
}

// ── Generic UI ────────────────────────────────────────────────

function KpiGrid({ children }: { children: React.ReactNode }) {
  return <div style={kpiGrid}>{children}</div>;
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
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
      {sub && <div style={kpiSub}>{sub}</div>}
    </div>
  );
}

function Section({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "0.75rem",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 600 }}>{title}</h2>
        {right}
      </header>
      {children}
    </section>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <div style={cardStyle}>{children}</div>;
}

function Table({
  head,
  rows,
  empty,
}: {
  head: string[];
  rows: React.ReactNode[][];
  empty: string;
}) {
  if (rows.length === 0) {
    return <Empty>{empty}</Empty>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} style={thStyle}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, i) => (
            <tr key={i}>
              {cells.map((c, j) => (
                <td key={j} style={tdStyle}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const palette: Record<string, string> = {
    Sent: "#3fff00",
    Cleared: "#3fff00",
    Pending: "#ffcc00",
    Canceled: "#ff3b30",
    Rejected: "#ff3b30",
    Refunded: "#ff9500",
    Partial: "#ff9500",
    Returned: "#ff3b30",
    Disputed: "#ff3b30",
  };
  const color = palette[value] || "#a3a3a3";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.15rem 0.55rem",
        borderRadius: "999px",
        background: "rgba(255,255,255,0.04)",
        color,
        fontSize: "0.8rem",
        fontWeight: 600,
      }}
    >
      {value}
    </span>
  );
}

function Empty({ children, error }: { children: React.ReactNode; error?: boolean }) {
  return (
    <p
      style={{
        margin: 0,
        padding: "1.25rem 0",
        textAlign: "center",
        color: error ? "var(--db-negative, #ff3b30)" : "var(--db-text-muted, #a3a3a3)",
      }}
    >
      {children}
    </p>
  );
}

// ── Helpers ───────────────────────────────────────────────────

function fmtDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function shortDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "2-digit", day: "2-digit" });
}

function shortTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "numeric", minute: "2-digit" });
}

function monthShort(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short" });
}

// ── Styles ────────────────────────────────────────────────────

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "80rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
  gap: "1.5rem",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};
const kpiGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "1rem",
};
const kpiCard: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1rem 1.25rem",
};
const kpiLabel: React.CSSProperties = {
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--db-text-muted, #a3a3a3)",
};
const kpiValue: React.CSSProperties = {
  fontSize: "1.75rem",
  fontWeight: 700,
  marginTop: "0.5rem",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};
const kpiSub: React.CSSProperties = {
  fontSize: "0.85rem",
  marginTop: "0.5rem",
  color: "var(--db-text-muted, #a3a3a3)",
};
const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
};
const cardHeader: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "0.75rem",
};
const moneyValue: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};
const textMuted: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.85rem",
};
const subLink: React.CSSProperties = {
  color: "var(--db-accent, #3fff00)",
  textDecoration: "none",
};
const btnOutline: React.CSSProperties = {
  border: "1px solid var(--db-border, #262626)",
  padding: "0.25rem 0.65rem",
  borderRadius: "0.5rem",
  fontSize: "0.85rem",
  textDecoration: "none",
  color: "inherit",
};
const btnPrimary: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "#000",
  padding: "0.4rem 0.9rem",
  borderRadius: "0.5rem",
  fontSize: "0.9rem",
  fontWeight: 600,
  textDecoration: "none",
};
const btnSm: React.CSSProperties = {
  ...btnOutline,
  padding: "0.15rem 0.5rem",
  fontSize: "0.8rem",
};
const badgeNavy: React.CSSProperties = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid var(--db-border, #262626)",
  padding: "0.15rem 0.55rem",
  borderRadius: "999px",
  fontSize: "0.75rem",
};
const gridTwo: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
  gap: "1rem",
};
const gridThree: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
  gap: "1rem",
};
const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.6rem 0.75rem",
  color: "var(--db-text-muted, #a3a3a3)",
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--db-border, #262626)",
};
const tdStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};
const bankRow: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "0.5rem 0",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};
const rowSummary: React.CSSProperties = {
  display: "flex",
  gap: "2rem",
  flexWrap: "wrap",
  padding: "1rem 1.25rem",
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
};
const quickLink: React.CSSProperties = {
  display: "block",
  padding: "1rem",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  background: "var(--db-surface-2, #141414)",
  color: "inherit",
};
