import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  changeUserRole,
  createPlatformUser,
  forcePasswordReset,
  impersonateUser,
  resetUser2FA,
  revokeUserSessions,
  toggleUserActive,
  useSuperadminStores,
  useSuperadminUsers,
  type SuperadminUserRow,
} from "../api/superadmin";
import { ApiError } from "../lib/api";
import { setAccessToken, setCurrentIdentity } from "../lib/auth";
import { formatDate } from "../lib/datetime";
import {
  Alert,
  Breadcrumbs,
  Button,
  Card,
  ConfirmDialog,
  Field,
  Input,
  Pager,
  PageHeader,
  PageShell,
  Pill,
  RowActions,
  Select,
  Table,
  TableStates,
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
  { value: "support", label: "Support" },
];

export default function SuperadminUsers() {
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [storeFilter, setStoreFilter] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const stores = useSuperadminStores();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<{ userId: number; password: string } | null>(null);
  const [confirmAction, setConfirmAction] = useState<{
    userId: number; username: string; action: "toggle" | "reset2fa" | "resetpw" | "impersonate" | "revokesessions";
  } | null>(null);
  const [showAddSupport, setShowAddSupport] = useState(false);
  const [roleChange, setRoleChange] = useState<{
    userId: number; username: string; currentRole: string;
  } | null>(null);
  const [newRole, setNewRole] = useState("");

  const { data, isLoading, isError, error: fetchError, refetch } =
    useSuperadminUsers({ q: q || undefined, role: role || undefined, store_id: storeFilter, page });

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
      } else if (action === "revokesessions") {
        const res = await revokeUserSessions(userId);
        toast({
          message: res.revoked_count > 0
            ? `Revoked ${res.revoked_count} active session${res.revoked_count === 1 ? "" : "s"}.`
            : "No active sessions to revoke.",
          tone: "success",
        });
        refresh();
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
    revokesessions: `Revoke every active session for "${confirmAction?.username}"? They'll be bounced to the login page on their next API call. Use for compromised credentials, departing staff, or any "lock them out now" incident.`,
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
            <Select
              value={storeFilter ?? ""}
              onChange={(e) => {
                setStoreFilter(e.target.value ? Number(e.target.value) : undefined);
                setPage(1);
              }}
            >
              <option value="">All stores</option>
              {(stores.data?.rows ?? []).map((s) => (
                <option key={s.store_id} value={s.store_id}>{s.name}</option>
              ))}
            </Select>
          </div>
        )}
      />

      {error && <Alert tone="error">{error}</Alert>}

      <div className={styles.addSupportRow}>
        <Button
          tone="secondary"
          onClick={() => setShowAddSupport((v) => !v)}
        >
          {showAddSupport ? "Cancel" : "Add support login"}
        </Button>
      </div>

      {showAddSupport && (
        <AddSupportLoginCard
          onCreated={() => {
            setShowAddSupport(false);
            refresh();
          }}
        />
      )}

      {tempPw && (
        <Alert tone="success">
          <div className={styles.tempPwLabel}>
            Temporary password (show to the user — it won't be displayed again):
          </div>
          <div className={styles.tempPw}>{tempPw.password}</div>
        </Alert>
      )}

      <Card>
        <TableStates
          isLoading={isLoading} isError={isError} error={fetchError}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No users match these filters."
          rows={8} cols={6}
        />
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
                  onChangeRole={() => {
                    setRoleChange({ userId: u.id, username: u.username, currentRole: u.role });
                    setNewRole("");
                  }}
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
          : confirmAction?.action === "revokesessions" ? "Revoke sessions"
          : "Impersonate user"
        }
        message={confirmMessages[confirmAction?.action ?? "toggle"] ?? ""}
        confirmLabel={
          confirmAction?.action === "impersonate" ? "Sign in as user"
          : confirmAction?.action === "revokesessions" ? "Revoke sessions"
          : "Confirm"
        }
        confirmTone={
          confirmAction?.action === "impersonate" ? "danger"
          : confirmAction?.action === "revokesessions" ? "danger"
          : "primary"
        }
        busy={busyId != null}
        onConfirm={() => { void doAction(); }}
        onCancel={() => setConfirmAction(null)}
      />

      <ConfirmDialog
        open={roleChange != null}
        title="Change role"
        message={(
          <>
            Change role for &quot;{roleChange?.username}&quot; from {roleChange?.currentRole} to:
            <Select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              style={{ marginTop: "0.5rem" }}
            >
              <option value="">— Select role —</option>
              <option value="admin">Admin</option>
              <option value="employee">Employee</option>
              <option value="owner">Owner</option>
            </Select>
          </>
        )}
        confirmLabel={busyId != null ? "Saving…" : "Change role"}
        busy={busyId != null}
        onConfirm={() => {
          if (!roleChange || !newRole) return;
          setBusyId(roleChange.userId);
          setError(null);
          changeUserRole(roleChange.userId, newRole)
            .then(() => {
              toast({ message: `Role changed to ${newRole}.`, tone: "success" });
              refresh();
              setRoleChange(null);
              setNewRole("");
            })
            .catch((err) => {
              setError(err instanceof ApiError ? err.message : "Failed to change role.");
            })
            .finally(() => setBusyId(null));
        }}
        onCancel={() => { setRoleChange(null); setNewRole(""); }}
      />
    </PageShell>
  );
}


function UserRow({
  user: u,
  busyId,
  onAction,
  onChangeRole,
}: {
  user: SuperadminUserRow;
  busyId: number | null;
  onAction: (action: "toggle" | "reset2fa" | "resetpw" | "impersonate" | "revokesessions") => void;
  onChangeRole: () => void;
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
        <Pill tone={u.is_active ? "accent" : "neutral"}>
          {u.is_active ? "Active" : "Inactive"}
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
          {u.last_login_at ? formatDate(u.last_login_at) : "Never"}
        </span>
      </td>
      <td style={{ ...tdStyle, textAlign: "right" }}>
        {!isSuperadmin && (
          <RowActions
            actions={[
              {
                label: "Change role",
                onClick: onChangeRole,
                disabled: busyId === u.id,
              },
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
              {
                label: "Revoke sessions",
                onClick: () => onAction("revokesessions"),
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
    : role === "support" ? "warning"
    : role === "admin" ? "accent"
    : role === "owner" ? "info"
    : "neutral";
  return <Pill tone={tone}>{role}</Pill>;
}

/** Inline create form for a store-less "support" platform login —
 *  tickets-only role, password sign-in with a 7-day login window.
 *  The role is fixed server-side (POST /superadmin/platform-users
 *  only mints support). */
function AddSupportLoginCard({ onCreated }: { onCreated: () => void }) {
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createPlatformUser({
        username: username.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });
      toast({
        message: `Support login "${username.trim()}" created.`,
        tone: "success",
      });
      onCreated();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not create the login.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={onSubmit} autoComplete="off">
        <p className={styles.addSupportLead}>
          Support logins can only work the ticket queue - no store
          data, no platform controls. They sign in with a password
          and are logged out automatically 7 days after each login.
        </p>
        {error && <Alert tone="error">{error}</Alert>}
        <div className={styles.addSupportGrid}>
          <Field label="Username">
            <Input
              value={username} required minLength={3} maxLength={80}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Field>
          <Field label="Full name">
            <Input
              value={fullName} maxLength={120}
              onChange={(e) => setFullName(e.target.value)}
            />
          </Field>
          <Field label="Email" hint="Ticket-update emails go here.">
            <Input
              type="email" value={email} maxLength={255}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Password" hint="At least 8 characters.">
            <Input
              type="password" value={password} required
              minLength={8} maxLength={200}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        </div>
        <Button type="submit" busy={busy} disabled={busy}>
          {busy ? "Creating\u2026" : "Create support login"}
        </Button>
      </form>
    </Card>
  );
}
