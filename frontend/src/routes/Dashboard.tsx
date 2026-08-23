import { Link, Navigate } from "react-router-dom";

import {
  useDashboardSummary,
  type AdminDashboard,
  type EmployeeDashboard,
  type DashboardSummary,
} from "../api/dashboard";
import { useStoreInfo } from "../api/account";
import {
  ButtonLink,
  Card,
  ErrorState,
  KpiCard,
  KpiGrid,
  Loading,
  PageHeader,
  PageShell,
  Pill,
  Section,
  Table,
  TableSkeleton,
  fontSize,
  space,
  tokens,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";
import { getOpenStatus } from "../lib/datetime";
import { fmtNumber, fmtShortDate } from "../lib/formatters";

// Role-shaped dashboard. /api/v2/dashboard/summary returns one
// payload tagged by role; we render the matching panel.
//
// Owner sessions have no `store_id` on their JWT (they live across
// every store under their umbrella), so /api/v2/dashboard/summary
// 400s for them. The Flask /dashboard route already handles this
// by redirecting owners to /owner/dashboard; mirror that in the
// SPA so owners who hit /app/dashboard directly (post-login,
// bookmark, hard refresh) land on their own dashboard.
export default function Dashboard() {
  const identity = getCurrentIdentity();
  // Hooks must be called unconditionally before any early return —
  // the owner-redirect branch below uses `<Navigate>` to short-circuit
  // *render*, but the hook itself still fires. TanStack Query reads
  // the role from getCurrentIdentity() and skips the request when
  // owner-shaped JWTs are detected via its own `enabled` flag (see
  // useDashboardSummary in ../api/dashboard.ts).
  const { data, isLoading, isError, error, refetch } = useDashboardSummary();
  // Store-info lookup powers the "Open now" pill. Owners /
  // superadmin (no store_id on the JWT) are excluded; the hook
  // gates itself.
  const { data: storeInfo } = useStoreInfo();
  const openStatus = identity?.role !== "superadmin"
    ? getOpenStatus(
        storeInfo?.store?.store_hours,
        storeInfo?.store?.timezone,
      )
    : null;

  if (identity?.role === "owner") {
    return <Navigate to="/owner/dashboard" replace />;
  }

  if (identity?.role === "superadmin") {
    return <Navigate to="/superadmin/dashboard" replace />;
  }

  if (identity?.role === "support") {
    // Tickets-only platform role — the ticket queue IS its home.
    return <Navigate to="/superadmin/tickets" replace />;
  }

  const title =
    identity?.role === "superadmin"
      ? "Platform Dashboard"
      : identity?.role === "employee"
        ? "My Dashboard"
        : "Dashboard";

  return (
    <PageShell>

      <PageHeader
        title={title}
        actions={openStatus ? (
          <span
            title={
              openStatus.todayLabel
                ? `${openStatus.dayLabel}: ${openStatus.todayLabel}`
                : `${openStatus.dayLabel}: closed all day`
            }
          >
            <Pill tone={openStatus.open ? "accent" : "negative"}>
              {openStatus.open ? "Open now" : "Closed now"}
            </Pill>
          </span>
        ) : undefined}
      />

      {isLoading && (
        <Card>
          <Loading label="Loading dashboard…" />
          <div style={{ marginTop: space.md }}>
            <TableSkeleton rows={4} cols={3} />
          </div>
        </Card>
      )}

      {isError && (
        <ErrorState
          message={
            <>
              Couldn't load dashboard —{" "}
              {error instanceof Error ? error.message : "unknown error"}
            </>
          }
          onRetry={() => refetch()}
        />
      )}

      {data && <Body summary={data} />}
    </PageShell>
  );
}

function Body({ summary }: { summary: DashboardSummary }) {
  if (summary.role === "admin") return <AdminPanel d={summary} />;
  if (summary.role === "employee") return <EmployeePanel d={summary} />;
  if (summary.role === "superadmin") return <SuperadminPanel d={summary} />;
  return <ErrorState message="Unrecognised role." />;
}

// ── Admin ─────────────────────────────────────────────────────

function AdminPanel({ d }: { d: AdminDashboard }) {
  const monthName = monthShort(d.today);
  // Module-driven layout (P1-10): each enabled module contributes
  // its own KPIs/sections; disabled modules disappear entirely.
  const ms = d.modules.includes("module_money_services");
  return (
    <>
      <KpiGrid>
        {ms && (
          <>
            <KpiCard label="Total transfers" value={d.kpis.total_transfers.toLocaleString()} sub="All time" />
            <KpiCard
              label="Today's transfers"
              value={d.kpis.today_transfers.toLocaleString()}
              sub={fmtShortDate(d.today)}
              tone="positive"
            />
            <KpiCard
              label="Unreconciled ACH"
              value={d.kpis.pending_ach.toLocaleString()}
              sub={d.kpis.pending_ach > 0 ? "Needs attention" : "All clear"}
              tone={d.kpis.pending_ach > 0 ? "negative" : "positive"}
            />
          </>
        )}
        {d.day_close && (
          <>
            <KpiCard
              label={`Store sales (${shortDate(d.day_close.date)})`}
              value={`$${d.day_close.gross_sales.toLocaleString(undefined, {
                minimumFractionDigits: 2, maximumFractionDigits: 2,
              })}`}
              sub={
                <Link to="/day-close" className="ds-link" style={{ color: tokens.accent }}>
                  Open day close →
                </Link>
              }
              tone="positive"
            />
            <KpiCard
              label="Drawer over / short"
              value={
                d.day_close.over_short == null
                  ? "—"
                  : `$${d.day_close.over_short.toFixed(2)}`
              }
              sub={
                d.day_close.uncounted_drawers > 0
                  ? `${d.day_close.uncounted_drawers} drawer(s) uncounted`
                  : "All drawers counted"
              }
              tone={
                d.day_close.uncounted_drawers > 0
                || (d.day_close.over_short ?? 0) !== 0
                  ? "warning" : "positive"
              }
            />
          </>
        )}
        {d.lottery && (
          <KpiCard
            label={`Lottery (${shortDate(d.lottery.date)})`}
            value={`$${d.lottery.value.toLocaleString(undefined, {
              minimumFractionDigits: 2, maximumFractionDigits: 2,
            })}`}
            sub={
              d.lottery.uncounted_active_packs > 0
                ? `${d.lottery.uncounted_active_packs} pack(s) uncounted`
                : `${d.lottery.tickets_sold} tickets sold`
            }
            tone={
              d.lottery.uncounted_active_packs > 0 ? "warning" : "positive"
            }
          />
        )}
        <KpiCard
          label="Today's daily book"
          value={d.kpis.today_report_entered ? "Entered" : "Pending"}
          sub={
            <Link
              to={`/daily/edit?date=${d.today}`}
              className="ds-link"
              style={{ color: tokens.accent }}
            >
              {d.kpis.today_report_entered ? "Edit report" : "Enter now →"}
            </Link>
          }
          tone={d.kpis.today_report_entered ? "positive" : "warning"}
        />
        <KpiCard
          label="Bank sync"
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
              <Link to="/bank" className="ds-link" style={{ color: tokens.accent }}>
                Connect via Stripe →
              </Link>
            )
          }
          tone={d.stripe_accounts.length > 0 ? "positive" : "negative"}
        />
        {d.kpis.net_income_month != null && (
          <KpiCard
            label={`Net income (${monthName})`}
            value={`$${Math.round(d.kpis.net_income_month).toLocaleString()}`}
            sub={
              <Link to="/monthly" className="ds-link" style={{ color: tokens.accent }}>
                View P&amp;L →
              </Link>
            }
            tone={d.kpis.net_income_month >= 0 ? "positive" : "negative"}
          />
        )}
      </KpiGrid>

      {d.day_close && d.day_close.top_departments.length > 0 && (
        <Section title={`Department sales (${shortDate(d.day_close.date)})`}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: space.lg,
            }}
          >
            {d.day_close.top_departments.map((t) => (
              <Card key={t.name}>
                <div style={{ fontWeight: 600, marginBottom: space.sm }}>
                  {t.name}
                </div>
                <div style={{ fontFamily: tokens.fontMono, fontSize: "1.4rem" }}>
                  ${t.amount.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {ms && (
      <Section title="This month by company">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: space.lg,
          }}
        >
          {d.company_stats.map((c) => (
            <Card key={c.company}>
              <header
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: space.md,
                }}
              >
                <span style={{ fontWeight: 600 }}>{c.company}</span>
                <Pill>{c.count} transfers</Pill>
              </header>
              <div style={{ fontFamily: tokens.fontMono, fontSize: "1.6rem" }}>
                ${c.total.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
              <div style={{ color: tokens.textMuted, fontSize: fontSize.sm }}>
                Fees: ${c.fees.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
            </Card>
          ))}
          {d.company_stats.length === 0 && (
            <Card>
              <p style={{ color: tokens.textMuted, margin: 0 }}>
                No companies enabled for this store yet.
              </p>
            </Card>
          )}
        </div>
      </Section>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
          gap: space.lg,
        }}
      >
        {ms && (
        <Card>
          <header
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: space.md,
            }}
          >
            <span style={{ fontWeight: 600 }}>Recent Transfers</span>
            <ButtonLink href="/transfers" tone="secondary" size="sm">View all</ButtonLink>
          </header>
          <Table>
            <thead>
              <tr>
                {["Date", "Sender", "Company", "Amount", "Status"].map((h) => (
                  <th key={h} style={dashThStyle}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.recent_transfers.map((t) => (
                <tr key={t.id}>
                  <td style={dashTdStyle}>{shortDate(t.send_date)}</td>
                  <td style={dashTdStyle}>{t.sender_name}</td>
                  <td style={dashTdStyle}>{t.company}</td>
                  <td style={{ ...dashTdStyle, fontFamily: tokens.fontMono }}>
                    ${t.send_amount.toFixed(2)}
                  </td>
                  <td style={dashTdStyle}>
                    <StatusPill value={t.status} />
                  </td>
                </tr>
              ))}
              {d.recent_transfers.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    style={{
                      ...dashTdStyle,
                      textAlign: "center",
                      color: tokens.textMuted,
                    }}
                  >
                    No transfers yet
                  </td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: space.lg }}>
          {ms && (
          <Card>
            <header
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: space.md,
              }}
            >
              <span style={{ fontWeight: 600 }}>Recent ACH Batches</span>
              <ButtonLink href="/batches" tone="secondary" size="sm">View all</ButtonLink>
            </header>
            <Table>
              <thead>
                <tr>
                  {["Date", "Company", "ACH amount", "Variance", "Status"].map((h) => (
                    <th key={h} style={dashThStyle}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.recent_batches.map((b) => (
                  <tr key={b.id}>
                    <td style={dashTdStyle}>{shortDate(b.ach_date)}</td>
                    <td style={dashTdStyle}>{b.company}</td>
                    <td style={{ ...dashTdStyle, fontFamily: tokens.fontMono }}>
                      ${b.ach_amount.toFixed(2)}
                    </td>
                    <td style={dashTdStyle}>
                      {b.variance === 0 ? "✓ $0" : `$${b.variance.toFixed(2)}`}
                    </td>
                    <td style={dashTdStyle}>
                      <StatusPill value={b.status} />
                    </td>
                  </tr>
                ))}
                {d.recent_batches.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      style={{
                        ...dashTdStyle,
                        textAlign: "center",
                        color: tokens.textMuted,
                      }}
                    >
                      No batches yet
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>
          )}

          <Card>
            <header
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: space.md,
              }}
            >
              <span style={{ fontWeight: 600 }}>Bank Accounts</span>
              <ButtonLink href="/bank" tone="secondary" size="sm">View all</ButtonLink>
            </header>
            {d.stripe_accounts.length === 0 ? (
              <p style={{ color: tokens.textMuted, margin: 0 }}>
                No bank connected yet.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: space.sm }}>
                {d.stripe_accounts.map((a) => (
                  <div
                    key={a.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: `${space.sm} 0`,
                      borderBottom: `1px solid ${tokens.borderSubtle}`,
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600 }}>
                        {a.display_name || "Account"}
                        {a.last4 ? ` ••${a.last4}` : ""}
                      </div>
                      <div style={{ color: tokens.textMuted, fontSize: fontSize.sm }}>
                        {a.institution_name || "—"}
                      </div>
                    </div>
                    <div style={{ fontFamily: tokens.fontMono }}>
                      ${a.last_balance.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
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
  const ms = d.modules.includes("module_money_services");
  return (
    <>
      <KpiGrid>
        {ms && (
          <KpiCard
            label="Today's transfers"
            value={d.totals.count.toLocaleString()}
            sub={fmtShortDate(d.today)}
          />
        )}
        {d.day_close && (
          <KpiCard
            label={`Store sales (${shortDate(d.day_close.date)})`}
            value={`$${d.day_close.gross_sales.toLocaleString(undefined, {
              minimumFractionDigits: 2, maximumFractionDigits: 2,
            })}`}
            sub={
              <Link to="/day-close" className="ds-link" style={{ color: tokens.accent }}>
                Open day close →
              </Link>
            }
          />
        )}
        {d.lottery && (
          <KpiCard
            label="Lottery counts"
            value={
              d.lottery.uncounted_active_packs > 0
                ? `${d.lottery.uncounted_active_packs} pending`
                : "Done"
            }
            sub={
              <Link to="/lottery" className="ds-link" style={{ color: tokens.accent }}>
                Count packs →
              </Link>
            }
            tone={
              d.lottery.uncounted_active_packs > 0 ? "warning" : "positive"
            }
          />
        )}
      </KpiGrid>

      {ms && (
      <Section
        title="Today's transfers"
        actions={
          <ButtonLink href="/transfers/new" tone="primary" size="sm">
            + New transfer
          </ButtonLink>
        }
      >
        <Card>
          <Table>
            <thead>
              <tr>
                {[
                  "Time",
                  "Sender",
                  "Company",
                  "Amount",
                  "Fee",
                  "Recipient",
                  "Country",
                  "Confirmation #",
                  "Status",
                  "",
                ].map((h) => (
                  <th key={h} style={dashThStyle}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.today_transfers.map((t) => (
                <tr key={t.id}>
                  <td style={dashTdStyle}>
                    {t.created_at ? shortTime(t.created_at) : "—"}
                  </td>
                  <td style={dashTdStyle}>{t.sender_name}</td>
                  <td style={dashTdStyle}>{t.company}</td>
                  <td style={{ ...dashTdStyle, fontFamily: tokens.fontMono }}>
                    ${t.send_amount.toFixed(2)}
                  </td>
                  <td style={{ ...dashTdStyle, fontFamily: tokens.fontMono }}>
                    ${t.fee.toFixed(2)}
                  </td>
                  <td style={dashTdStyle}>{t.recipient_name || "—"}</td>
                  <td style={dashTdStyle}>{t.country || "—"}</td>
                  <td style={dashTdStyle}>{t.confirm_number || "—"}</td>
                  <td style={dashTdStyle}>
                    <StatusPill value={t.status} />
                  </td>
                  <td style={dashTdStyle}>
                    <Link
                      to={`/transfers/${t.id}/edit`}
                      className="ds-link"
                      style={{ color: tokens.accent, fontSize: fontSize.sm }}
                    >
                      Edit
                    </Link>
                  </td>
                </tr>
              ))}
              {d.today_transfers.length === 0 && (
                <tr>
                  <td
                    colSpan={10}
                    style={{
                      ...dashTdStyle,
                      textAlign: "center",
                      color: tokens.textMuted,
                      padding: `${space.xl} 0`,
                    }}
                  >
                    Nothing logged today — log the first one to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
      </Section>
      )}

      {ms && d.totals.count > 0 && (
        <Card>
          <div
            style={{
              display: "flex",
              gap: space["2xl"],
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <div>
              <span style={{ color: tokens.textMuted, fontSize: fontSize.sm }}>
                Today Total Sent:
              </span>{" "}
              <strong style={{ fontFamily: tokens.fontMono }}>
                ${d.totals.sent.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </strong>
            </div>
            <div>
              <span style={{ color: tokens.textMuted, fontSize: fontSize.sm }}>
                Fees Collected:
              </span>{" "}
              <strong style={{ fontFamily: tokens.fontMono }}>
                ${d.totals.fees.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </strong>
            </div>
            <div>
              <span style={{ color: tokens.textMuted, fontSize: fontSize.sm }}>
                Transfers:
              </span>{" "}
              <strong>{d.totals.count}</strong>
            </div>
          </div>
        </Card>
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
        <KpiCard label="Total Stores" value={fmtNumber(d.total_stores)} sub="All time" />
        <KpiCard label="Active" value={fmtNumber(d.active_stores)} tone="positive" />
        <KpiCard label="Trial" value={fmtNumber(d.trial_stores)} tone="warning" />
        <KpiCard label="Paid" value={fmtNumber(d.paid_stores)} tone="positive" />
        <KpiCard
          label="MRR"
          value={typeof d.mrr_total === "number" ? `$${d.mrr_total.toLocaleString()}` : "—"}
          tone="positive"
        />
        <KpiCard
          label="ARR"
          value={typeof d.arr_total === "number" ? `$${d.arr_total.toLocaleString()}` : "—"}
          tone="positive"
        />
        <KpiCard label="New (last 30 days)" value={fmtNumber(d.new_stores_30d)} tone="positive" />
        <KpiCard
          label="Cancellations (30d)"
          value={fmtNumber(d.cancellations_30d)}
          tone={
            typeof d.cancellations_30d === "number" && d.cancellations_30d > 0
              ? "negative"
              : "positive"
          }
        />
      </KpiGrid>

      <Section title="Quick links">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: space.md,
          }}
        >
          <QuickLink to="/superadmin/stores" title="Stores" desc="Browse, edit, impersonate." />
          <QuickLink to="/superadmin/audit-log" title="Audit log" desc="Every platform admin action." />
          <QuickLink to="/superadmin/announcements" title="Announcements" desc="Global banners + push." />
          <QuickLink to="/superadmin/reports" title="Platform Reports" desc="MRR/ARR, churn, adoption." />
        </div>
      </Section>
    </>
  );
}

function QuickLink({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} style={{ textDecoration: "none", color: "inherit" }}>
      <Card interactive padding={space.lg}>
        <div style={{ fontWeight: 600, marginBottom: space.xs }}>{title}</div>
        <div style={{ color: tokens.textMuted, fontSize: fontSize.sm }}>{desc}</div>
      </Card>
    </Link>
  );
}

// ── Helpers ───────────────────────────────────────────────────

function StatusPill({ value }: { value: string }) {
  const tone =
    ["Sent", "Cleared"].includes(value) ? "accent"
      : ["Pending"].includes(value) ? "warning"
        : ["Cancelled", "Rejected", "Returned", "Disputed"].includes(value) ? "negative"
          : ["Refunded", "Partial"].includes(value) ? "warning"
            : "neutral";
  return <Pill tone={tone as "accent" | "warning" | "negative" | "neutral"}>{value}</Pill>;
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
  return d.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "numeric",
    minute: "2-digit",
  });
}

function monthShort(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short" });
}

// Local table cell styles — extends the DS tokens with the dense
// table padding the dashboard tables use (sm vs md elsewhere).
const dashThStyle: React.CSSProperties = {
  textAlign: "left",
  padding: `${space.sm} ${space.md}`,
  borderBottom: `1px solid ${tokens.border}`,
  fontSize: fontSize.xs,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: tokens.textMuted,
  fontWeight: 500,
};

const dashTdStyle: React.CSSProperties = {
  padding: `${space.sm} ${space.md}`,
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};
