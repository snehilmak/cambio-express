import { useState } from "react";

import {
  useSuperadminStores,
  type SuperadminStoreRow,
} from "../api/superadmin";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs, ButtonLink,
  Card, Empty, EmptyState, ErrorState, Input, PageHeader, PageShell, Pill,
  Table, TableSkeleton, tdStyle, thStyle, type PillTone,
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

      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Stores" }]} />

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
            "",
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
            <td style={{ ...tdStyle, textAlign: "right" }}>
              <ButtonLink href={`/superadmin/stores/${r.store_id}/drill`} tone="secondary" size="sm">
                View
              </ButtonLink>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function PlanPill({ plan, cycle }: { plan: string; cycle: string }) {
  // Maps plan slug → shared Pill tone so the badge palette tracks
  // the same `--db-tone-*` tokens every other tone surface in the
  // SPA uses (Alert / ErrorState / audit-log badges / etc.).
  const toneByPlan: Record<string, PillTone> = {
    trial:    "warning",
    basic:    "success",
    pro:      "accent",
    inactive: "negative",
  };
  const tone: PillTone = toneByPlan[plan] ?? "neutral";
  const label = plan.charAt(0).toUpperCase() + plan.slice(1);
  return (
    <Pill tone={tone}>
      {label}{cycle ? ` · ${cycle}` : ""}
    </Pill>
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
