import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useSuperadminAuditLog,
  type SuperadminAuditRow,
} from "../api/superadmin";
import { getCurrentIdentity } from "../lib/auth";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Audit log</h1>
        <p style={emptyStyle}>Superadmin scope required.</p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header
        style={{
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={titleStyle}>Audit log</h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--db-text-muted, #a3a3a3)" }}>
            {data
              ? `${data.total.toLocaleString()} entries${
                  action ? ` matching "${action}"` : ""
                }`
              : "—"}
          </p>
        </div>
        <input
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
          style={{ ...inputStyle, maxWidth: "20rem" }}
        />
      </header>

      <section style={cardStyle}>
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
      </section>
    </main>
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
                  color: "var(--db-text-muted, #a3a3a3)",
                  fontWeight: 500,
                  fontSize: "0.78rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: "1px solid var(--db-border, #262626)",
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
                  <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>—</span>
                )}
              </td>
              <td style={{ ...cellStyle, color: "var(--db-text-muted, #a3a3a3)" }}>
                {r.details || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pager({
  page, totalPages, onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "flex-end",
        alignItems: "center",
        marginTop: "1rem",
        gap: "0.5rem",
      }}
    >
      <button
        type="button"
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        style={{
          ...pagerBtn,
          opacity: page <= 1 ? 0.4 : 1,
          cursor: page <= 1 ? "not-allowed" : "pointer",
        }}
      >
        ← Prev
      </button>
      <span
        style={{
          color: "var(--db-text-muted, #a3a3a3)",
          fontSize: "0.85rem",
          alignSelf: "center",
        }}
      >
        {page} / {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        style={{
          ...pagerBtn,
          opacity: page >= totalPages ? 0.4 : 1,
          cursor: page >= totalPages ? "not-allowed" : "pointer",
        }}
      >
        Next →
      </button>
    </div>
  );
}


const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "82rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
};

const actionPill: React.CSSProperties = {
  display: "inline-block",
  background: "rgba(63,255,0,0.10)",
  color: "var(--db-accent, #3fff00)",
  borderRadius: "999px",
  padding: "0.15rem 0.55rem",
  fontSize: "0.78rem",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const pagerBtn: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.4rem 0.9rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.85rem",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
