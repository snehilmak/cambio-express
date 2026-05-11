import { Link } from "react-router-dom";

import {
  useAdminUsers,
  type AdminUserRow,
} from "../api/admin";
import { getCurrentIdentity } from "../lib/auth";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui";

// /app/admin/users — per-store user roster + entry point to the
// Add / Edit forms. Mirrors the legacy admin_users.html surface:
// table of (username, full_name, role, status, created) plus an
// Edit button per row (suppressed on the caller's own row to
// match the legacy "(you)" label).

export default function AdminUsers() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useAdminUsers();

  if (
    !identity
    || (identity.role !== "admin" && identity.role !== "owner")
  ) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>User Management</h1>
        <p style={emptyStyle}>
          You need a store-admin sign-in to manage users.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header style={headerStyle}>
        <div>
          <h1 style={titleStyle}>User Management</h1>
          <p style={leadStyle}>
            Manage who has access and what they can see.
          </p>
        </div>
        <Link to="/admin/users/new" style={btnPrimaryStyle}>
          + Add User
        </Link>
      </header>

      <section style={cardStyle}>
        {isLoading && <TableSkeleton rows={4} cols={4} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load users"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="No users yet" body="Add one to get started." />
        )}
        {data && data.rows.length > 0 && (
          <Table rows={data.rows} selfId={identity.user_id} />
        )}
      </section>

      <section style={infoCalloutStyle}>
        <h2 style={cardTitleStyle}>Access Levels</h2>
        <div style={accessLevelsStyle}>
          <p style={{ margin: 0 }}>
            <strong style={strongStyle}>Super Admin</strong> — Full
            access: all transfers from all employees, ACH batch log,
            bank data, reconciliation, user management.
          </p>
          <p style={{ margin: "0.5rem 0 0" }}>
            <strong style={strongStyle}>Employee</strong> — Can only
            log new transfers and view their own entries. No bank
            data, no ACH batches, no other employees' data.
          </p>
        </div>
      </section>
    </main>
  );
}


function Table({
  rows, selfId,
}: { rows: AdminUserRow[]; selfId: number }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {["Username", "Full Name", "Role", "Status", "Created", ""].map((h) => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id}>
              <td style={cellStyle}>
                <strong>{u.username}</strong>
              </td>
              <td style={cellStyle}>{u.full_name || "—"}</td>
              <td style={cellStyle}>
                <RoleBadge role={u.role} />
              </td>
              <td style={cellStyle}>
                <StatusBadge active={u.is_active} />
              </td>
              <td style={{ ...cellStyle, ...monoCell }}>
                {formatCreated(u.created_at)}
              </td>
              <td style={cellStyle}>
                {u.id !== selfId ? (
                  <Link
                    to={`/admin/users/${u.id}/edit`}
                    style={btnOutlineSmStyle}
                  >
                    Edit
                  </Link>
                ) : (
                  <span style={mutedSmallStyle}>(you)</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function RoleBadge({ role }: { role: string }) {
  const isAdmin = role === "admin";
  return (
    <span style={{
      display: "inline-block",
      padding: "0.15rem 0.5rem",
      borderRadius: "999px",
      background: isAdmin
        ? "rgba(63,255,0,0.10)"
        : "rgba(94,169,255,0.10)",
      color: isAdmin ? "#3fff00" : "#5ea9ff",
      border: `1px solid ${isAdmin ? "rgba(63,255,0,0.35)" : "rgba(94,169,255,0.35)"}`,
      fontSize: "0.78rem",
      fontWeight: 500,
      letterSpacing: "0.02em",
    }}>
      {isAdmin ? "Super Admin" : "Employee"}
    </span>
  );
}


function StatusBadge({ active }: { active: boolean }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "0.15rem 0.5rem",
      borderRadius: "999px",
      background: active
        ? "rgba(63,255,0,0.10)"
        : "rgba(255,77,109,0.10)",
      color: active ? "#3fff00" : "#ff4d6d",
      border: `1px solid ${active ? "rgba(63,255,0,0.35)" : "rgba(255,77,109,0.35)"}`,
      fontSize: "0.78rem",
      fontWeight: 500,
      letterSpacing: "0.02em",
    }}>
      {active ? "Active" : "Inactive"}
    </span>
  );
}


// Server returns ISO timestamps. Render as "MM/DD/YYYY" (UTC) to
// match the legacy `created_at.strftime('%m/%d/%Y')` cell.
function formatCreated(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const yy = d.getUTCFullYear();
  return `${mm}/${dd}/${yy}`;
}


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  padding: "2rem 1.5rem", maxWidth: "82rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
};

const headerStyle: React.CSSProperties = {
  display: "flex", flexWrap: "wrap",
  alignItems: "center", justifyContent: "space-between",
  gap: "0.75rem", marginBottom: "1rem",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600, margin: 0,
};

const leadStyle: React.CSSProperties = {
  margin: "0.4rem 0 0",
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.9rem",
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "0.5rem 0.5rem",
};

const infoCalloutStyle: React.CSSProperties = {
  marginTop: "1.25rem",
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderLeft: "3px solid var(--db-neon, #3fff00)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const cardTitleStyle: React.CSSProperties = {
  margin: "0 0 0.6rem", fontSize: "0.95rem", fontWeight: 600,
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
};

const accessLevelsStyle: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.88rem", lineHeight: 1.6,
};

const strongStyle: React.CSSProperties = {
  color: "var(--db-text, #e5e5e5)", fontWeight: 600,
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
  verticalAlign: "middle",
};

const monoCell: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
  whiteSpace: "nowrap",
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 600, fontSize: "0.92rem",
  background: "var(--db-neon, #3fff00)",
  color: "var(--db-neon-ink, #001a0f)",
  border: "none", borderRadius: "0.5rem",
  textDecoration: "none",
  display: "inline-block",
};

const btnOutlineSmStyle: React.CSSProperties = {
  padding: "0.35rem 0.75rem",
  fontWeight: 500, fontSize: "0.82rem",
  background: "transparent",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.4rem",
  textDecoration: "none",
  display: "inline-block",
};

const mutedSmallStyle: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.85rem",
};

const emptyStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
};
