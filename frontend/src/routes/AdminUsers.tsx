import { Link } from "react-router-dom";

import {
  useAdminUsers,
  type AdminUserRow,
} from "../api/admin";
import { useProfile, useStoreInfo } from "../api/account";
import { getCurrentIdentity } from "../lib/auth";
import { formatDate } from "../lib/datetime";
import {
  Breadcrumbs,
  Button, ButtonLink, Card, Empty, PageHeader,
  PageShell, Pill, Table, TableStates, tdStyle, thStyle,
} from "../components/ui";
import styles from "./AdminUsers.module.css";

// /app/admin/users — per-store user roster + entry point to the
// Add / Edit forms. Mirrors the legacy admin_users.html surface:
// table of (username, full_name, role, status, created) plus an
// Edit button per row (suppressed on the caller's own row to
// match the legacy "(you)" label).

export default function AdminUsers() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useAdminUsers();
  const { data: profile } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const userTz  = profile?.timezone ?? "";
  const storeTz = storeInfo?.store?.timezone ?? "";

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

      <Breadcrumbs crumbs={[{ label: "User Management" }]} />

      <PageHeader
        title="User Management"
        subtitle="Manage who has access and what they can see."
        actions={(
          <ButtonLink href="/admin/users/new" tone="primary" size="sm"> 
            + Add User
          </ButtonLink>
        )}
      />

      <Card>
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No users yet"
          emptyBody="Add one to get started."
          rows={4} cols={4}
        />
        {data && data.rows.length > 0 && (
          <UserTable
            rows={data.rows}
            selfId={identity.user_id}
            userTimezone={userTz}
            storeTimezone={storeTz}
          />
        )}
      </Card>

      <section className={styles.infoCallout}>
        <h2 className={styles.calloutTitle}>Access Levels</h2>
        <div className={styles.accessLevels}>
          <p>
            <strong>Super Admin</strong> — Full
            access: all transfers from all employees, ACH batch log,
            bank data, reconciliation, user management.
          </p>
          <p>
            <strong>Employee</strong> — Can only
            log new transfers and view their own entries. No bank
            data, no ACH batches, no other employees' data.
          </p>
        </div>
      </section>
    </PageShell>
  );
}


function UserTable({
  rows, selfId, userTimezone, storeTimezone,
}: {
  rows: AdminUserRow[];
  selfId: number;
  userTimezone: string;
  storeTimezone: string;
}) {
  return (
    <Table>
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
            <td style={tdStyle}>
              <strong>{u.username}</strong>
            </td>
            <td style={tdStyle}>{u.full_name || "—"}</td>
            <td style={tdStyle}>
              <Pill tone={u.role === "admin" ? "accent" : "info"}>
                {u.role === "admin" ? "Super Admin" : "Employee"}
              </Pill>
            </td>
            <td style={tdStyle}>
              <Pill tone={u.is_active ? "accent" : "negative"}>
                {u.is_active ? "Active" : "Inactive"}
              </Pill>
            </td>
            <td style={tdStyle}>
              <span className={styles.monoCell}>
                {formatDate(u.created_at, { userTimezone, storeTimezone })}
              </span>
            </td>
            <td style={tdStyle}>
              {u.id !== selfId ? (
                <Link
                  to={`/admin/users/${u.id}/edit`}
                  style={{ textDecoration: "none" }}
                >
                  <Button tone="secondary" size="sm">Edit</Button>
                </Link>
              ) : (
                <span className={styles.mutedSmall}>(you)</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}


