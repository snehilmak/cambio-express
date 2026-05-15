import { useState } from "react";

import {
  useSuperadminStores,
  type SuperadminStoreRow,
} from "../api/superadmin";
import { getCurrentIdentity } from "../lib/auth";
import {
  Card, Empty, EmptyState, ErrorState, Input, PageHeader, PageShell, Pill,
  Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import styles from "./SuperadminStores.module.css";

// Platform-wide stores list at /app/superadmin/stores. Mirrors
// the legacy `/superadmin/stores` table — superadmin's primary
// "what's going on across all customers?" view.
//
// Subsequent PRs add filters (plan, status), the controls
// dashboard, anomaly feed, audit log, and impersonation hooks.

export default function SuperadminStores() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useSuperadminStores();
  const [q, setQ] = useState("");

  if (identity?.role !== "superadmin") {
    return (
      <PageShell>
        <PageHeader title="All stores" />
        <Empty>Superadmin scope required.</Empty>
      </PageShell>
    );
  }

  const filtered =
    data && q
      ? data.rows.filter((r) => {
          const needle = q.toLowerCase();
          return (
            r.name.toLowerCase().includes(needle) ||
            r.slug.toLowerCase().includes(needle) ||
            r.email.toLowerCase().includes(needle)
          );
        })
      : data?.rows;

  return (
    <PageShell>
      <PageHeader
        title="All stores"
        subtitle={data
          ? `${(filtered?.length ?? 0).toLocaleString()} of ${data.total.toLocaleString()}`
          : "—"}
        actions={(
          <Input
            type="search"
            value={q}
            placeholder="Search name, slug, email…"
            onChange={(e) => setQ(e.target.value)}
            style={{ maxWidth: "22rem" }}
          />
        )}
      />

      <Card>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {filtered && filtered.length === 0 && !isLoading && (
          <EmptyState title="No stores match these filters." />
        )}
        {filtered && filtered.length > 0 && <StoresTable rows={filtered} />}
      </Card>
    </PageShell>
  );
}

function StoresTable({ rows }: { rows: SuperadminStoreRow[] }) {
  return (
    <Table>
      <thead>
        <tr>
          {[
            "Store",
            "Plan",
            "Status",
            "Trial / retention",
            "Stripe",
            "Created",
          ].map((h, i) => (
            <th key={i} style={thStyle}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.store_id}>
            <td style={tdStyle}>
              <div className={styles.storeName}>{r.name}</div>
              <div className={styles.storeMeta}>
                {r.slug}
                {r.email ? ` · ${r.email}` : ""}
              </div>
            </td>
            <td style={tdStyle}>
              <PlanPill plan={r.plan} cycle={r.billing_cycle} />
            </td>
            <td style={tdStyle}>
              <Pill tone={r.is_active ? "accent" : "negative"}>
                {r.is_active ? "active" : "disabled"}
              </Pill>
            </td>
            <td style={tdStyle}>
              <TrialCell row={r} />
            </td>
            <td style={tdStyle}>
              {r.stripe_customer_id ? (
                <span className={styles.stripeId}>
                  {r.stripe_customer_id.slice(0, 14)}…
                </span>
              ) : (
                <span className={styles.dash}>—</span>
              )}
            </td>
            <td style={tdStyle}>
              <span className={styles.monoMuted}>{r.created_at.slice(0, 10)}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function PlanPill({ plan, cycle }: { plan: string; cycle: string }) {
  const palette: Record<string, { bg: string; fg: string }> = {
    trial:    { bg: "rgba(255,184,0,0.15)", fg: "#ffb800" },
    basic:    { bg: "rgba(63,255,0,0.12)",  fg: "#3fff00" },
    pro:      { bg: "rgba(63,255,0,0.20)",  fg: "#3fff00" },
    inactive: { bg: "rgba(255,59,48,0.15)", fg: "#ff3b30" },
  };
  const c = palette[plan] ?? { bg: "transparent", fg: "#a3a3a3" };
  return (
    <span
      className={styles.planPill}
      style={{ background: c.bg, color: c.fg }}
    >
      {plan}{cycle ? ` · ${cycle}` : ""}
    </span>
  );
}

function TrialCell({ row }: { row: SuperadminStoreRow }) {
  if (row.data_retention_until) {
    return (
      <span className={styles.trialRetention}>
        Purge {row.data_retention_until.slice(0, 10)}
      </span>
    );
  }
  if (row.plan === "trial" && row.trial_ends_at) {
    return (
      <span className={styles.trialEnds}>
        Trial ends {row.trial_ends_at.slice(0, 10)}
      </span>
    );
  }
  return <span className={styles.dash}>—</span>;
}
