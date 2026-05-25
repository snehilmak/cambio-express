import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  forcePasswordReset,
  impersonateUser,
  resetUser2FA,
  toggleUserActive,
  useSuperadminUsers,
  type SuperadminUserRow,
} from "../api/superadmin";
import { ApiError } from "../lib/api";
import { setAccessToken, setCurrentIdentity } from "../lib/auth";
import {
  Alert,
  Breadcrumbs,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  Loading,
  Pager,
  PageHeader,
  PageShell,
  Pill,
  RowActions,
  Select,
  Table,
  TableSkeleton,
  tdStyle,
  thStyle,
  useToast,
} from "../components/ui";
import styles from "./SuperadminUsers.module.css";

const ROLES = [
  { value: "", label: "All roles" },
  { value: "admin", label: "Admin" },
  { value: "employee", label: "Employee" },
  { value: "owner", label: "Owner" },
  { value: "superadmin", label: "Superadmin" },
];

export default function SuperadminUsers() {
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<{ userId: number; password: string } | null>(null);
  const [confirmAction, setConfirmAction] = useState<{
    userId: number; username: string; action: "toggle" | "reset2fa" | "resetpw" | "impersonate";
  } | null>(null);

  const { data, isLoading, isError, error: fetchError, refetch } =
    useSuperadminUsers({ q: q || undefined, role: role || undefined, page });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["superadmin", "users"] });
  }

  async function doAction() {
    if (!confirmAction) return;
    const { userId, action } = confirmAction;
    setBusyId(userId);
    setError(null);
    setTempPw(null);
    try {
      if (action === "toggle") {
        const res = await toggleUserActive(userId);
        toast({
          message: res.is_active ? "User enabled." : "User disabled.",
          tone: "success",
        });
        refresh();
      } else if (action === "reset2fa") {
        await resetUser2FA(userId);
        toast({ message: "2FA cleared — user can re-enroll at next login.", tone: "success" });
        refresh();
      } else if (action === "resetpw") {
        const res = await forcePasswordReset(userId);
        setTempPw({ userId, password: res.temp_password });
        toast({ message: "Password reset.", tone: "success" });
        refresh();
      } else if (action === "impersonate") {
        const res = await impersonateUser(userId);
        setAccessToken(res.token);
        setCurrentIdentity({
          user_id: res.user.id,
          username: res.user.username,
          full_name: res.user.full_name,
          role: res.user.role,
          store_id: res.user.store_id,
          permissions: [],
        });
        window.location.assign("/app/dashboard");
        return;
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setBusyId(null);
      setConfirmAction(null);
    }
  }

  const confirmMessages: Record<string, string> = {
    toggle: `Toggle active status for "${confirmAction?.username}"?`,
    reset2fa: `Clear 2FA enrollment for "${confirmAction?.username}"? They'll need to re-enroll at next login.`,
    resetpw: `Reset password for "${confirmAction?.username}"? A temporary password will be generated.`,
    impersonate: `Sign in as "${confirmAction?.username}"? You'll leave this page and see the app from their perspective. This is audit-logged.`,
  };

  return (
    <PageShell>
      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Users" }]} />

      <PageHeader
        title="All users"
        subtitle={data ? `${data.total.toLocaleString()} users` : "—"}
        actions={(
          <div className={styles.filterRow}>
            <Input
              type="search"
              value={q}
              placeholder="Search name, email, username…"
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              className={styles.searchInput}
            />
            <Select
              value={role}
              onChange={(e) => { setRole(e.target.value); setPage(1); }}
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </Select>
          </div>
        )}
      />

      {error && <Alert tone="error">{error}</Alert>}

      {tempPw && (
        <Alert tone="success">
          <div className={styles.tempPwLabel}>
            Temporary password (show to the user — it won't be displayed again):
          </div>
          <div className={styles.tempPw}>{tempPw.password}</div>
        </Alert>
      )}

      <Card>
        {isLoading && <TableSkeleton rows={8} cols={6} />}
        {isError && (
          <ErrorState
            message={fetchError instanceof Error ? fetchError.message : "Could not load users"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="No users match these filters." />
        )}
        {data && data.rows.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th style={thStyle}>User</th>
                <th style={thStyle}>Role</th>
                <th style={thStyle}>Store</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>2FA</th>
                <th style={thStyle}>Last login</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  busyId={busyId}
                  onAction={(action) =>
                    setConfirmAction({ userId: u.id, username: u.username, action })
                  }
                />
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {data && data.total_pages > 1 && (
        <Pager
          page={data.page}
          totalPages={data.total_pages}
          onPage={setPage}
        />
      )}

      <ConfirmDialog
        open={confirmAction != null}
        title={
          confirmAction?.action === "toggle" ? "Toggle user"
          : confirmAction?.action === "reset2fa" ? "Reset 2FA"
          : confirmAction?.action === "resetpw" ? "Reset password"
          : "Impersonate user"
        }
        message={confirmMessages[confirmAction?.action ?? "toggle"] ?? ""}
        confirmLabel={
          confirmAction?.action === "impersonate" ? "Sign in as user" : "Confirm"
        }
        confirmTone={confirmAction?.action === "impersonate" ? "danger" : "primary"}
        busy={busyId != null}
        onConfirm={() => { void doAction(); }}
        onCancel={() => setConfirmAction(null)}
      />
    </PageShell>
  );
}


function UserRow({
  user: u,
  busyId,
  onAction,
}: {
  user: SuperadminUserRow;
  busyId: number | null;
  onAction: (action: "toggle" | "reset2fa" | "resetpw" | "impersonate") => void;
}) {
  const isSuperadmin = u.role === "superadmin";
  return (
    <tr>
      <td style={tdStyle}>
        <div className={styles.userName}>{u.full_name || u.username}</div>
        <div className={styles.userMeta}>
          {u.username}
          {u.email ? ` · ${u.email}` : ""}
        </div>
      </td>
      <td style={tdStyle}>
        <RolePill role={u.role} />
      </td>
      <td style={tdStyle}>
        {u.store_name ? (
          <span>{u.store_name}</span>
        ) : (
          <span className={styles.monoMuted}>—</span>
        )}
      </td>
      <td style={tdStyle}>
        <Pill tone={u.is_active ? "accent" : "negative"}>
          {u.is_active ? "Active" : "Disabled"}
        </Pill>
      </td>
      <td style={tdStyle}>
        {u.has_2fa ? (
          <Pill tone="success">Enrolled</Pill>
        ) : (
          <span className={styles.monoMuted}>—</span>
        )}
      </td>
      <td style={tdStyle}>
        <span className={styles.monoMuted}>
          {u.last_login_at ? u.last_login_at.slice(0, 10) : "Never"}
        </span>
      </td>
      <td style={{ ...tdStyle, textAlign: "right" }}>
        {!isSuperadmin && (
          <RowActions
            actions={[
              {
                label: u.is_active ? "Disable" : "Enable",
                onClick: () => onAction("toggle"),
                disabled: busyId === u.id,
              },
              {
                label: "Reset password",
                onClick: () => onAction("resetpw"),
                disabled: busyId === u.id,
              },
              ...(u.has_2fa ? [{
                label: "Reset 2FA",
                onClick: () => onAction("reset2fa"),
                disabled: busyId === u.id,
              }] : []),
              {
                label: "Impersonate",
                onClick: () => onAction("impersonate"),
                disabled: busyId === u.id,
              },
            ]}
          />
        )}
      </td>
    </tr>
  );
}


function RolePill({ role }: { role: string }) {
  const tone = role === "superadmin" ? "negative"
    : role === "admin" ? "accent"
    : role === "owner" ? "info"
    : "neutral";
  return <Pill tone={tone}>{role}</Pill>;
}
