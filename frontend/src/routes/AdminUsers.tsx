import { Link } from "react-router-dom";

import {
  useAdminUsers,
  type AdminUserRow,
} from "../api/admin";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, EmptyState, ErrorState, PageHeader, PageShell,
  TableSkeleton, tokens,
} from "../components/ui";

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
      <PageShell>
        <PageHeader title="User Management" />
        <Empty>You need a store-admin sign-in to manage users.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="User Management"
        subtitle="Manage who has access and what they can see."
        actions={(
          <ButtonLink href="/admin/users/new" tone="primary">
            + Add User
          </ButtonLink>
        )}
      />

      <Card padding="0.5rem 0.5rem">
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
      </Card>

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
    </PageShell>
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


const infoCalloutStyle: React.CSSProperties = {
  marginTop: "1.25rem",
  background: tokens.surface2,
  border: `1px solid ${tokens.border}`,
  borderLeft: `3px solid ${tokens.accent}`,
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const cardTitleStyle: React.CSSProperties = {
  margin: "0 0 0.6rem", fontSize: "0.95rem", fontWeight: 600,
  fontFamily: tokens.fontDisplay,
};

const accessLevelsStyle: React.CSSProperties = {
  color: tokens.textMuted,
  fontSize: "0.88rem", lineHeight: 1.6,
};

const strongStyle: React.CSSProperties = {
  color: tokens.text, fontWeight: 600,
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.6rem 0.75rem",
  color: tokens.textMuted,
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: `1px solid ${tokens.border}`,
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
  verticalAlign: "middle",
};

const monoCell: React.CSSProperties = {
  fontFamily: tokens.fontMono,
  fontSize: "0.85rem",
  color: tokens.textMuted,
  whiteSpace: "nowrap",
};

const btnOutlineSmStyle: React.CSSProperties = {
  padding: "0.35rem 0.75rem",
  fontWeight: 500, fontSize: "0.82rem",
  background: "transparent",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.4rem",
  textDecoration: "none",
  display: "inline-block",
};

const mutedSmallStyle: React.CSSProperties = {
  color: tokens.textMuted,
  fontSize: "0.85rem",
};
