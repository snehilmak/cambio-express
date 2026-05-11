import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useSuperadminAuditLog,
  type SuperadminAuditRow,
} from "../api/superadmin";
import { getCurrentIdentity } from "../lib/auth";
import {
  Card, Empty, EmptyState, ErrorState, Input, PageHeader, PageShell, Pager,
  TableSkeleton, tokens,
} from "../components/ui";

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
      <PageShell maxWidth="82rem">
        <PageHeader title="Audit log" />
        <Empty>Superadmin scope required.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="82rem">
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
            <Table rows={data.rows} />
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

function Table({ rows }: { rows: SuperadminAuditRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.92rem",
        }}
      >
        <thead>
          <tr>
            {["When", "Actor", "Action", "Target", "Details"].map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: "left",
                  padding: "0.6rem 0.75rem",
                  color: tokens.textMuted,
                  fontWeight: 500,
                  fontSize: "0.78rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: `1px solid ${tokens.border}`,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cellStyle}>
                <span style={monoMuted}>{r.created_at.replace("T", " ").slice(0, 19)}</span>
              </td>
              <td style={cellStyle}>{r.admin_name || "—"}</td>
              <td style={cellStyle}>
                <span style={actionPill}>{r.action}</span>
              </td>
              <td style={cellStyle}>
                {r.target_type ? (
                  <span style={{ ...mono, fontSize: "0.85rem" }}>
                    {r.target_type}#{r.target_id || "—"}
                  </span>
                ) : (
                  <span style={{ color: tokens.textMuted }}>—</span>
                )}
              </td>
              <td style={{ ...cellStyle, color: tokens.textMuted }}>
                {r.details || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};

const mono: React.CSSProperties = {
  fontFamily: tokens.fontMono,
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: tokens.textMuted,
};

const actionPill: React.CSSProperties = {
  display: "inline-block",
  background: "rgba(63,255,0,0.10)",
  color: tokens.accent,
  borderRadius: "999px",
  padding: "0.15rem 0.55rem",
  fontSize: "0.78rem",
  fontFamily: tokens.fontMono,
};
