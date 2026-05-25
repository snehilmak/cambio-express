import { useSearchParams } from "react-router-dom";

import { useMyActivity, useProfile, useStoreInfo } from "../api/account";
import type { MyActivityRow } from "../api/account";
import { formatTimestamp } from "../lib/datetime";
import {
  Breadcrumbs,
  Button, Card, EmptyState, ErrorState, Field, PageHeader, PageShell,
  Pager, Pill, Select, space, Table, TableSkeleton, tdStyle, thStyle,
  type PillTone,
} from "../components/ui";
import styles from "./AccountActivity.module.css";

// /app/account/activity — cross-store per-user audit feed.
// Mirrors /app/admin/audit-log visually but is scoped to "things
// I did" across every store I've touched (handy for a multi-
// store cashier or an owner who works behind the counter).

export default function AccountActivity() {
  const { data: profile } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const userTz  = profile?.timezone ?? "";
  const storeTz = storeInfo?.store?.timezone ?? "";
  const [sp, setSP] = useSearchParams();
  const page   = Number(sp.get("page") ?? 1) || 1;
  const target = sp.get("target") ?? "";
  const action = sp.get("action") ?? "";

  const { data, isLoading, isError, error, refetch } = useMyActivity({
    target, action, page,
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    if (key !== "page") next.delete("page");
    setSP(next, { replace: true });
  }

  const hasFilters = !!(target || action);

  return (
    <PageShell maxWidth="70rem">

      <Breadcrumbs crumbs={[{ label: "Account", to: "/settings" }, { label: "Activity" }]} />

      <PageHeader title="My activity" />

      <Card style={{ marginBottom: space.lg }}>
        <div className={styles.cardHeader}>
          Filters
          <span className={styles.cardHeaderCount}>
            {data ? `${data.total.toLocaleString()} ${data.total === 1 ? "event" : "events"}` : "—"}
          </span>
        </div>
        <div className={styles.filtersRow}>
          <Field label="Target" style={{ minWidth: "10rem" }}>
            <Select
              value={target}
              onChange={(e) => setParam("target", e.target.value)}
            >
              <option value="">All</option>
              <option value="transfer">Transfer</option>
              <option value="daily_report">Daily Report</option>
              <option value="batch">ACH Batch</option>
            </Select>
          </Field>
          <Field label="Action" style={{ minWidth: "10rem" }}>
            <Select
              value={action}
              onChange={(e) => setParam("action", e.target.value)}
            >
              <option value="">All</option>
              <option value="create">Create</option>
              <option value="update">Update</option>
              <option value="delete">Delete</option>
              <option value="lock">Lock</option>
              <option value="unlock">Unlock</option>
              <option value="status_changed">Status changed</option>
            </Select>
          </Field>
          {hasFilters && (
            <Button
              tone="secondary"
              size="sm"
              onClick={() => setSP(new URLSearchParams(), { replace: true })}
            >
              Clear
            </Button>
          )}
        </div>
      </Card>

      <Card>
        <div className={styles.cardHeader}>
          Recent activity
          {data && (
            <span className={styles.cardHeaderPage}>
              Page {data.page} of {data.total_pages}
            </span>
          )}
        </div>

        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="Nothing here yet — once you log a transfer, lock a daily book, or save a batch you'll see it." />
        )}
        {data && data.rows.length > 0 && (
          <>
            <ActivityTable
              rows={data.rows}
              userTimezone={userTz}
              storeTimezone={storeTz}
            />
            <Pager
              page={data.page}
              totalPages={data.total_pages}
              onPage={(p) => setParam("page", String(p))}
            />
          </>
        )}
      </Card>

      <p className={styles.fine}>
        Covers your transfer creates / edits / status changes /
        deletes, daily-report locks / unlocks, and ACH batch
        creates / updates across every store you've touched.
      </p>
    </PageShell>
  );
}


function ActivityTable({
  rows, userTimezone, storeTimezone,
}: {
  rows: MyActivityRow[];
  userTimezone: string;
  storeTimezone: string;
}) {
  return (
    <Table>
      <thead>
        <tr>
          {["When", "Store", "Action", "Target", "Detail"].map((h) => (
            <th key={h} style={thStyle}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.source}-${r.ts}-${r.target_id}-${i}`}>
            <td style={tdStyle}>
              <span className={styles.monoMuted}>
                {formatTimestamp(r.ts, { userTimezone, storeTimezone })}
              </span>
            </td>
            <td style={tdStyle}>
              {r.store_name || "—"}
            </td>
            <td style={tdStyle}>
              <ActionBadge action={r.action} />
            </td>
            <td style={tdStyle}>
              <span className={styles.targetType}>
                {r.target_type || "—"}
              </span>
              {r.target_label && <div>{r.target_label}</div>}
            </td>
            <td style={{ ...tdStyle }} className={styles.detailCell}>
              {r.summary || "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}


function ActionBadge({ action }: { action: string }) {
  // Maps the raw audit-action string onto a shared Pill tone so
  // the badge palette stays in lock-step with Alert / ErrorState /
  // every other tone-driven surface in the SPA.  Pre-Phase-2 this
  // file hand-rolled its own rgba palette; now it inherits the
  // shared `--db-tone-*` tokens for free.
  const toneByAction: Record<string, PillTone> = {
    create:         "success",
    created:        "success",
    update:         "info",
    updated:        "info",
    delete:         "negative",
    deleted:        "negative",
    lock:           "warning",
    unlock:         "warning",
    status_changed: "warning",
  };
  const tone: PillTone = toneByAction[action] ?? "neutral";
  return <Pill tone={tone}>{action}</Pill>;
}


