import { useSearchParams } from "react-router-dom";

import {
  useAdminAuditLog,
  type AdminAuditRow,
  type AdminAuditUserOption,
} from "../api/admin";
import { useProfile, useStoreInfo } from "../api/account";
import { formatTimestamp } from "../lib/datetime";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Button, Card, Empty, Field, InfoTip, PageHeader, PageShell,
  Pager, Select, space, Table, TableStates, tdStyle, thStyle,
} from "../components/ui";
import { AuditActionBadge } from "../components/AuditActionBadge";
import styles from "./AdminAuditLog.module.css";

// /app/admin/audit-log — merged operator + transfer audit feed
// for the JWT principal's store. Filters live in the URL so the
// page is shareable; per_page is the legacy 50.

export default function AdminAuditLog() {
  const identity = getCurrentIdentity();
  const { data: profile } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const userTz  = profile?.timezone ?? "";
  const storeTz = storeInfo?.store?.timezone ?? "";
  const [sp, setSP] = useSearchParams();
  const page   = Number(sp.get("page") ?? 1) || 1;
  const target = sp.get("target") ?? "";
  const action = sp.get("action") ?? "";
  const user   = sp.get("user")   ?? "";

  const { data, isLoading, isError, error, refetch } = useAdminAuditLog(
    page, target, action, user,
  );

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    if (key !== "page") next.delete("page");
    setSP(next, { replace: true });
  }

  if (identity?.role !== "admin" && identity?.role !== "owner") {
    return (
      <PageShell>
        <PageHeader title="Audit log" />
        <Empty>You need a store-admin sign-in to see the activity log.</Empty>
      </PageShell>
    );
  }

  const hasFilters = !!(target || action || user);

  return (
    <PageShell>

      <Breadcrumbs crumbs={[{ label: "Finance" }, { label: "Activity log" }]} />

      <PageHeader
        title={
          <>
            Audit log
            <InfoTip text="Covers transfer creates, edits, status changes and deletes, daily-report locks and unlocks, and ACH batch creates and updates. Routine daily-report auto-saves aren't logged — the lock event captures who closed the day." />
          </>
        }
        subtitle="Every admin action across the store, newest first."
      />

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
          <Field label="User" style={{ minWidth: "10rem" }}>
            <Select
              value={user}
              onChange={(e) => setParam("user", e.target.value)}
              disabled={!data}
            >
              <option value="">Any</option>
              {(data?.store_users ?? []).map((u: AdminAuditUserOption) => (
                <option key={u.id} value={String(u.id)}>
                  {u.label}{u.role !== "admin" ? ` (${u.role})` : ""}
                </option>
              ))}
            </Select>
          </Field>
          {hasFilters && (
            <Button
              tone="secondary"
              size="sm"
              onClick={() => {
                const next = new URLSearchParams();
                setSP(next, { replace: true });
              }}
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

        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No activity matches these filters."
        />
        {data && data.rows.length > 0 && (
          <>
            <AuditTable
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

    </PageShell>
  );
}


function AuditTable({
  rows, userTimezone, storeTimezone,
}: {
  rows: AdminAuditRow[];
  userTimezone: string;
  storeTimezone: string;
}) {
  return (
    <Table>
      <thead>
        <tr>
          {["When", "Actor", "Action", "Target", "Details"].map((h) => (
            <th key={h} style={thStyle}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          // ts + target_id is unique enough; (source, ts) collisions
          // can happen across the same wallclock second so we add
          // the index as the final tiebreaker.
          <tr key={`${r.source}-${r.ts}-${r.target_id}-${i}`}>
            <td style={tdStyle}>
              <span className={styles.monoMuted}>
                {formatTimestamp(r.ts, { userTimezone, storeTimezone })}
              </span>
            </td>
            <td style={tdStyle}>
              <strong>{r.user_name || "—"}</strong>
              {r.user_role && (
                <span className={styles.userRole}>
                  ({r.user_role})
                </span>
              )}
            </td>
            <td style={tdStyle}>
              <AuditActionBadge action={r.action} />
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


