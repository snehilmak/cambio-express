import { useSearchParams } from "react-router-dom";

import { useMyActivity } from "../api/account";
import type { MyActivityRow } from "../api/account";
import {
  Button, Card, EmptyState, ErrorState, Field, PageHeader, PageShell,
  Pager, Select, Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import styles from "./AccountActivity.module.css";

// /app/account/activity — cross-store per-user audit feed.
// Mirrors /app/admin/audit-log visually but is scoped to "things
// I did" across every store I've touched (handy for a multi-
// store cashier or an owner who works behind the counter).

export default function AccountActivity() {
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
    <PageShell>
      <PageHeader title="My activity" />

      <Card style={{ marginBottom: "1rem" }}>
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
            <ActivityTable rows={data.rows} />
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


function ActivityTable({ rows }: { rows: MyActivityRow[] }) {
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
              <span className={styles.monoMuted}>{formatTs(r.ts)}</span>
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
  const palette: Record<string, { bg: string; fg: string; border: string }> = {
    create:         { bg: "rgba(63,255,0,0.10)",  fg: "#3fff00", border: "rgba(63,255,0,0.35)" },
    created:        { bg: "rgba(63,255,0,0.10)",  fg: "#3fff00", border: "rgba(63,255,0,0.35)" },
    update:         { bg: "rgba(94,169,255,0.10)", fg: "#5ea9ff", border: "rgba(94,169,255,0.35)" },
    updated:        { bg: "rgba(94,169,255,0.10)", fg: "#5ea9ff", border: "rgba(94,169,255,0.35)" },
    delete:         { bg: "rgba(255,77,109,0.10)", fg: "#ff4d6d", border: "rgba(255,77,109,0.35)" },
    deleted:        { bg: "rgba(255,77,109,0.10)", fg: "#ff4d6d", border: "rgba(255,77,109,0.35)" },
    lock:           { bg: "rgba(255,176,32,0.10)", fg: "#ffb020", border: "rgba(255,176,32,0.35)" },
    unlock:         { bg: "rgba(255,176,32,0.10)", fg: "#ffb020", border: "rgba(255,176,32,0.35)" },
    status_changed: { bg: "rgba(255,221,87,0.10)", fg: "#ffdd57", border: "rgba(255,221,87,0.35)" },
  };
  const c = palette[action] ?? { bg: "#1c1c1c", fg: "#a3a3a3", border: "#2a2a2a" };
  return (
    <span
      className={styles.actionBadge}
      style={{ background: c.bg, color: c.fg, border: `1px solid ${c.border}` }}
    >
      {action}
    </span>
  );
}


function formatTs(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  const day   = String(d.getUTCDate()).padStart(2, "0");
  const yr    = d.getUTCFullYear();
  const hh    = String(d.getUTCHours()).padStart(2, "0");
  const mm    = String(d.getUTCMinutes()).padStart(2, "0");
  return `${month} ${day}, ${yr} ${hh}:${mm} UTC`;
}
