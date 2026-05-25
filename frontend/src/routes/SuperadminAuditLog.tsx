import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useSuperadminAuditLog,
  type SuperadminAuditRow,
} from "../api/superadmin";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Card, Empty, EmptyState, ErrorState, Input, PageHeader, PageShell, Pager,
  Pill, Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import styles from "./SuperadminAuditLog.module.css";

// Platform-wide superadmin audit log at /app/superadmin/audit-log.
// Mirrors the legacy /superadmin/reports/audit-log report —
// every superadmin mutation with actor + target + details.
//
// Action filter is a server-side substring match (case-insensitive)
// so an operator can drill into "trial" or "comp_plan" without
// exporting the full table.

export default function SuperadminAuditLog() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const action = sp.get("action") ?? "";
  const page   = Number(sp.get("page") ?? 1);
  const [draft, setDraft] = useState(action);

  const { data, isLoading, isError, error, refetch } = useSuperadminAuditLog(
    page, action,
  );

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    if (key !== "page") next.delete("page");
    setSP(next, { replace: true });
  }

  if (identity?.role !== "superadmin") {
    return (
      <PageShell maxWidth="100%">
        <PageHeader title="Audit log" />
        <Empty>Superadmin scope required.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="100%">

      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Audit log" }]} />

      <PageHeader
        title="Audit log"
        subtitle={data
          ? `${data.total.toLocaleString()} entries${
              action ? ` matching "${action}"` : ""
            }`
          : "—"}
        actions={(
          <Input
            type="search"
            value={draft}
            placeholder="Filter by action…"
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => setParam("action", draft.trim())}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                setParam("action", draft.trim());
              }
            }}
            style={{ maxWidth: "20rem" }}
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
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="No audit entries match." />
        )}
        {data && data.rows.length > 0 && (
          <>
            <AuditTable rows={data.rows} />
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

function AuditTable({ rows }: { rows: SuperadminAuditRow[] }) {
  return (
    <Table>
      <thead>
        <tr>
          {["When", "Actor", "Action", "Target", "Details"].map((h, i) => (
            <th key={i} style={thStyle}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td style={tdStyle}>
              <span className={styles.monoMuted}>
                {r.created_at.replace("T", " ").slice(0, 19)}
              </span>
            </td>
            <td style={tdStyle}>{r.admin_name || "—"}</td>
            <td style={tdStyle}>
              <Pill tone="accent" mono>{r.action}</Pill>
            </td>
            <td style={tdStyle}>
              {r.target_type ? (
                <span className={styles.targetId}>
                  {r.target_type}#{r.target_id || "—"}
                </span>
              ) : (
                <span className={styles.dash}>—</span>
              )}
            </td>
            <td style={tdStyle} className={styles.detailsCell}>
              {r.details || "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
