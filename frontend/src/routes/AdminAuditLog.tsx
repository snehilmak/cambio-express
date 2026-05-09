import { useSearchParams } from "react-router-dom";

import {
  useAdminAuditLog,
  type AdminAuditRow,
  type AdminAuditUserOption,
} from "../api/admin";
import { getCurrentIdentity } from "../lib/auth";

// /app/admin/audit-log — merged operator + transfer audit feed
// for the JWT principal's store. Filters live in the URL so the
// page is shareable; per_page is the legacy 50.

export default function AdminAuditLog() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const page   = Number(sp.get("page") ?? 1) || 1;
  const target = sp.get("target") ?? "";
  const action = sp.get("action") ?? "";
  const user   = sp.get("user")   ?? "";

  const { data, isLoading, isError, error } = useAdminAuditLog(
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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Activity Log</h1>
        <p style={emptyStyle}>
          You need a store-admin sign-in to see the activity log.
        </p>
      </main>
    );
  }

  const hasFilters = !!(target || action || user);

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1rem" }}>
        <h1 style={titleStyle}>Activity Log</h1>
      </header>

      <section style={{ ...cardStyle, marginBottom: "1rem" }}>
        <div style={cardHeaderStyle}>
          Filters
          <span style={{ marginLeft: "0.5rem", color: "var(--db-text-muted, #a3a3a3)", fontWeight: 400 }}>
            {data ? `${data.total.toLocaleString()} ${data.total === 1 ? "event" : "events"}` : "—"}
          </span>
        </div>
        <div style={filtersRowStyle}>
          <Field label="Target">
            <select
              value={target}
              onChange={(e) => setParam("target", e.target.value)}
              style={selectStyle}
            >
              <option value="">All</option>
              <option value="transfer">Transfer</option>
              <option value="daily_report">Daily Report</option>
              <option value="batch">ACH Batch</option>
            </select>
          </Field>
          <Field label="Action">
            <select
              value={action}
              onChange={(e) => setParam("action", e.target.value)}
              style={selectStyle}
            >
              <option value="">All</option>
              <option value="create">Create</option>
              <option value="update">Update</option>
              <option value="delete">Delete</option>
              <option value="lock">Lock</option>
              <option value="unlock">Unlock</option>
              <option value="status_changed">Status changed</option>
            </select>
          </Field>
          <Field label="User">
            <select
              value={user}
              onChange={(e) => setParam("user", e.target.value)}
              style={selectStyle}
              disabled={!data}
            >
              <option value="">Any</option>
              {(data?.store_users ?? []).map((u: AdminAuditUserOption) => (
                <option key={u.id} value={String(u.id)}>
                  {u.label}{u.role !== "admin" ? ` (${u.role})` : ""}
                </option>
              ))}
            </select>
          </Field>
          {hasFilters && (
            <button
              type="button"
              onClick={() => {
                const next = new URLSearchParams();
                setSP(next, { replace: true });
              }}
              style={clearBtnStyle}
            >
              Clear
            </button>
          )}
        </div>
      </section>

      <section style={cardStyle}>
        <div style={cardHeaderStyle}>
          Recent activity
          {data && (
            <span style={{ marginLeft: "auto", color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem", fontWeight: 400 }}>
              Page {data.page} of {data.total_pages}
            </span>
          )}
        </div>

        {isLoading && <Empty>Loading…</Empty>}
        {isError && (
          <Empty error>
            {error instanceof Error ? error.message : "Could not load"}
          </Empty>
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <Empty>No activity matches these filters.</Empty>
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

      <p style={fineStyle}>
        Audit covers transfer creates / edits / status changes /
        deletes, daily-report locks / unlocks, and ACH batch creates
        / updates. Saving daily-report fields generates many
        auto-saves and isn't logged here — the lock event captures
        who closed the day.
      </p>
    </main>
  );
}


function Field({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label style={fieldStyle}>
      <span style={fieldLabelStyle}>{label}</span>
      {children}
    </label>
  );
}


function Table({ rows }: { rows: AdminAuditRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {["When", "Who", "Action", "Target", "Detail"].map((h) => (
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
              <td style={cellStyle}>
                <span style={monoMuted}>{formatTs(r.ts)}</span>
              </td>
              <td style={cellStyle}>
                <strong>{r.user_name || "—"}</strong>
                {r.user_role && (
                  <span style={{ marginLeft: "0.4rem", color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem" }}>
                    ({r.user_role})
                  </span>
                )}
              </td>
              <td style={cellStyle}>
                <ActionBadge action={r.action} />
              </td>
              <td style={cellStyle}>
                <span style={{ color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem" }}>
                  {r.target_type || "—"}
                </span>
                {r.target_label && <div>{r.target_label}</div>}
              </td>
              <td style={{ ...cellStyle, fontSize: "0.9rem", maxWidth: "30rem" }}>
                {r.summary || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
    <span style={{
      display: "inline-block",
      padding: "0.15rem 0.5rem",
      borderRadius: "999px",
      background: c.bg,
      color: c.fg,
      border: `1px solid ${c.border}`,
      fontSize: "0.78rem",
      fontWeight: 500,
      letterSpacing: "0.02em",
    }}>{action}</span>
  );
}


function Pager({
  page, totalPages, onPage,
}: { page: number; totalPages: number; onPage: (p: number) => void }) {
  if (totalPages <= 1) return null;
  return (
    <div style={pagerStyle}>
      <button
        type="button"
        onClick={() => onPage(page - 1)}
        disabled={page <= 1}
        style={{ ...pagerBtn, opacity: page <= 1 ? 0.4 : 1, cursor: page <= 1 ? "not-allowed" : "pointer" }}
      >
        ← Prev
      </button>
      <span style={{ color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem" }}>
        {page} / {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={page >= totalPages}
        style={{ ...pagerBtn, opacity: page >= totalPages ? 0.4 : 1, cursor: page >= totalPages ? "not-allowed" : "pointer" }}
      >
        Next →
      </button>
    </div>
  );
}


function Empty({
  children, error,
}: { children: React.ReactNode; error?: boolean }) {
  return (
    <p style={{
      margin: 0, padding: "2rem 0", textAlign: "center",
      color: error ? "var(--db-negative, #ff3b30)" : "var(--db-text-muted, #a3a3a3)",
    }}>{children}</p>
  );
}


// Server returns ISO timestamps. Render as "May 09, 2026 17:42 UTC"
// to match the legacy %b %d, %Y %H:%M UTC format.
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


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  padding: "2rem 1.5rem", maxWidth: "82rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600, margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const cardHeaderStyle: React.CSSProperties = {
  display: "flex", alignItems: "center",
  fontWeight: 600, fontSize: "0.95rem",
  marginBottom: "1rem",
};

const filtersRowStyle: React.CSSProperties = {
  display: "flex", flexWrap: "wrap",
  gap: "0.75rem", alignItems: "flex-end",
};

const fieldStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column",
  gap: "0.35rem", minWidth: "10rem",
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "0.7rem", letterSpacing: "0.06em",
  textTransform: "uppercase", fontWeight: 600,
  color: "var(--db-text-muted, #a3a3a3)",
};

const selectStyle: React.CSSProperties = {
  padding: "0.55rem 0.75rem",
  background: "var(--db-bg-input, #0d0d0d)",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", fontSize: "0.9rem",
  minWidth: "10rem",
};

const clearBtnStyle: React.CSSProperties = {
  padding: "0.55rem 0.85rem",
  background: "transparent", color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", fontSize: "0.85rem",
  cursor: "pointer",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.6rem 0.75rem",
  color: "var(--db-text-muted, #a3a3a3)",
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--db-border, #262626)",
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
  verticalAlign: "top",
};

const monoMuted: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
  whiteSpace: "nowrap",
};

const pagerStyle: React.CSSProperties = {
  display: "flex", justifyContent: "space-between",
  alignItems: "center", marginTop: "1rem", padding: "0 0.5rem",
};

const pagerBtn: React.CSSProperties = {
  padding: "0.45rem 0.85rem",
  background: "transparent", color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", fontSize: "0.85rem",
};

const fineStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.85rem", lineHeight: 1.55,
};

const emptyStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
};
