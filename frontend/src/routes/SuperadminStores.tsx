import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  bulkStoreAction,
  useSuperadminStores,
  type SuperadminStoreRow,
} from "../api/superadmin";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Breadcrumbs, Button, ButtonLink, Checkbox,
  Card, Empty, Input, PageHeader, PageShell, Pill,
  Select, Table, TableStates, tdStyle, thStyle, useToast, type PillTone,
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
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkAction, setBulkAction] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAll(rows: SuperadminStoreRow[]) {
    if (selected.size === rows.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(rows.map((r) => r.store_id)));
    }
  }

  async function runBulk() {
    if (selected.size === 0 || !bulkAction) return;
    setBulkBusy(true);
    setBulkError(null);
    try {
      const action = bulkAction as "extend_trial" | "enable" | "disable";
      const res = await bulkStoreAction(Array.from(selected), action);
      toast({ message: `${res.count} store${res.count === 1 ? "" : "s"} updated.`, tone: "success" });
      setSelected(new Set());
      setBulkAction("");
      qc.invalidateQueries({ queryKey: ["superadmin", "stores"] });
    } catch (err) {
      setBulkError(err instanceof ApiError ? err.message : "Bulk action failed.");
    } finally {
      setBulkBusy(false);
    }
  }

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

      {selected.size > 0 && (
        <div className={styles.bulkBar}>
          <span className={styles.bulkCount}>{selected.size} selected</span>
          <Select value={bulkAction} onChange={(e) => setBulkAction(e.target.value)}>
            <option value="">— Choose action —</option>
            <option value="extend_trial">Extend trial (+14d)</option>
            <option value="enable">Enable</option>
            <option value="disable">Disable</option>
          </Select>
          <Button
            onClick={() => { void runBulk(); }}
            busy={bulkBusy}
            disabled={!bulkAction || bulkBusy}
            size="sm"
          >
            Apply
          </Button>
          <Button tone="secondary" size="sm" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      )}

      {bulkError && <Alert tone="error">{bulkError}</Alert>}

      <Card>
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!filtered || filtered.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No stores match these filters."
        />
        {filtered && filtered.length > 0 && (
          <StoresTable
            rows={filtered}
            selected={selected}
            onToggle={toggleSelect}
            onToggleAll={() => toggleAll(filtered)}
          />
        )}
      </Card>
    </PageShell>
  );
}

function StoresTable({ rows, selected, onToggle, onToggleAll }: {
  rows: SuperadminStoreRow[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: () => void;
}) {
  const allSelected = rows.length > 0 && selected.size === rows.length;
  return (
    <Table>
      <thead>
        <tr>
          <th style={thStyle}>
            <Checkbox
              checked={allSelected} onChange={onToggleAll}
              aria-label="Select all stores"
            />
          </th>
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
              <Checkbox
                checked={selected.has(r.store_id)}
                onChange={() => onToggle(r.store_id)}
                aria-label={`Select ${r.name}`}
              />
            </td>
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
