import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearAdminUserPermissions, createAdminUser, setAdminUserPermissions,
  updateAdminUser, useAdminUser, useAdminUserPermissions,
  type AdminUserCreateBody, type AdminUserUpdateBody, type PermMatrix,
} from "../api/admin";
import { useSessionStatus } from "../api/account";
import { api, ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, Checkbox, ConfirmDialog, ErrorState, Field, Input,
  Loading, PageHeader, PageShell, Select, space,
} from "../components/ui";
import { useUnsavedGuard } from "../lib/useUnsavedGuard";
import styles from "./AdminUserForm.module.css";

// R-2 access presets. "role" = no overlay (pure role permissions);
// the others seed a custom-access matrix the operator can tweak.
type AccessMode = "role" | "hr" | "bookkeeper" | "custom";

interface UserDraft {
  username:  string;
  full_name: string;
  role:      string;
  is_active: boolean;
  password:  string;
  // U-3 per-user module grants: restrict=false → all store
  // modules (module_access null); restrict=true → only `modules`.
  restrict:  boolean;
  modules:   string[];
  // R-1/R-2 custom access: access="role" → no overlay; anything
  // else carries the resource×action matrix in `perm`.
  access:    AccessMode;
  perm:      PermMatrix | null;
}

function makeBlankUser(): UserDraft {
  return {
    username: "", full_name: "", role: "employee", is_active: true,
    password: "", restrict: false, modules: [],
    access: "role", perm: null,
  };
}

// Fallbacks only while the live lists load — the permission
// endpoints return the authoritative resources/actions.
const FALLBACK_RESOURCES = [
  "transfers", "customers", "daily_book", "monthly", "batches",
  "bank_sync", "reports", "settings", "users", "time_clock",
  "return_checks", "lottery", "day_close", "catalog",
];
const FALLBACK_ACTIONS = ["create", "read", "update", "delete"];

const RESOURCE_LABELS: Record<string, string> = {
  transfers: "Money transfers",
  customers: "Customers",
  daily_book: "Daily book",
  monthly: "Monthly P&L",
  batches: "ACH batches",
  bank_sync: "Bank sync",
  reports: "Reports",
  settings: "Settings",
  users: "Users / Team",
  time_clock: "Time clock (HR)",
  return_checks: "Returned checks",
  lottery: "Lottery",
  day_close: "Day close",
  catalog: "Price book & purchases",
};

const ACTION_LABELS: Record<string, string> = {
  create: "Create", read: "View", update: "Edit", delete: "Delete",
};

function emptyMatrix(resources: string[], actions: string[]): PermMatrix {
  const m: PermMatrix = {};
  for (const r of resources) {
    m[r] = {};
    for (const a of actions) m[r][a] = false;
  }
  return m;
}

// HR & payroll: run the time clock, see the roster — nothing else.
function hrMatrix(resources: string[], actions: string[]): PermMatrix {
  const m = emptyMatrix(resources, actions);
  if (m.time_clock) for (const a of actions) m.time_clock[a] = true;
  if (m.users) m.users.read = true;
  return m;
}

// Bookkeeper: view every ledger, move no money, change nothing.
function bookkeeperMatrix(
  resources: string[], actions: string[],
): PermMatrix {
  const m = emptyMatrix(resources, actions);
  for (const r of resources) {
    if (r === "settings" || r === "users") continue;
    if (m[r]) m[r].read = true;
  }
  return m;
}

interface StorePermissionsPayload {
  resources: string[];
  actions: string[];
  matrix: Record<string, PermMatrix>;
}

// Human labels for the store-module flags (keys mirror the
// backend's MODULE_FLAG_KEYS; the checkbox list only renders keys
// present in the store's session-status `features`).
const MODULE_LABELS: Record<string, string> = {
  module_money_services: "Money services (transfers, batches, senders)",
  module_lottery:        "Lottery",
  module_day_close:      "Day close",
  module_check_cashing:  "Check cashing & returned checks",
  module_price_book:     "Price book & purchases",
};

// /app/admin/users/new and /app/admin/users/:uid/edit — combined
// create + edit form. Mirrors the legacy admin_user_form.html
// surface 1:1 (username on create only, password optional on
// edit, role pick, is_active checkbox on edit). Field-level
// errors come back as 422 with `field_errors` (mirroring the
// Settings profile-tab pattern).

export default function AdminUserForm() {
  const { uid: uidStr } = useParams();
  const uid = uidStr ? Number(uidStr) : null;
  const isEdit = uid != null;

  const queryClient = useQueryClient();
  const navigate    = useNavigate();
  const identity    = getCurrentIdentity();

  const detail  = useAdminUser(isEdit ? uid : null);
  const session = useSessionStatus();
  const userPerms = useAdminUserPermissions(isEdit ? uid : null);
  // Role matrices seed the "Custom" editor on create; shares the
  // Store Permissions page's cache key + payload shape.
  const storePerms = useQuery<StorePermissionsPayload>({
    enabled: identity?.role === "admin" || identity?.role === "owner",
    queryKey: ["store-permissions"],
    queryFn: () =>
      api<StorePermissionsPayload>("/api/v2/admin/store-permissions"),
  });

  // Form state — three sources hydrate it: the detail response on
  // edit, blank defaults on create.
  const [draft, setDraft] = useState<UserDraft>(makeBlankUser);
  // Baseline = last server-synced (or blank) draft; drives the guard.
  const [baseline, setBaseline] = useState<UserDraft>(makeBlankUser);
  const [busy, setBusy]   = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!isEdit || !detail.data) return;
    const u = detail.data.user;
    const fields = {
      username:  u.username,
      full_name: u.full_name,
      role:      u.role || "employee",
      is_active: u.is_active,
      password:  "",
      restrict:  u.module_access != null,
      modules:   u.module_access ?? [],
    };
    // Merge (don't replace) so the perms effect below and this one
    // can hydrate independently in either order.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft + dirty baseline from server-fetched user record on edit
    setDraft((d) => ({ ...d, ...fields }));
    setBaseline((b) => ({ ...b, ...fields }));
  }, [isEdit, detail.data]);

  useEffect(() => {
    if (!isEdit || !userPerms.data) return;
    const p = userPerms.data.has_custom
      ? {
          access: "custom" as const,
          perm: structuredClone(userPerms.data.matrix),
        }
      : { access: "role" as const, perm: null };
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate the custom-access half of the draft from the R-1 overlay endpoint
    setDraft((d) => ({ ...d, ...p }));
    setBaseline((b) => ({ ...b, ...p }));
  }, [isEdit, userPerms.data]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const guard = useUnsavedGuard(isDirty && !busy, {
    message: "You have unsaved edits on this user. Leave without saving?",
  });

  const isSelf = useMemo(() => {
    if (!isEdit || !detail.data || !identity) return false;
    return detail.data.user.id === identity.user_id;
  }, [isEdit, detail.data, identity]);

  function set<K extends keyof typeof draft>(
    key: K, value: (typeof draft)[K],
  ) {
    setDraft((d) => ({ ...d, [key]: value }));
    if (fieldErrors[key as string]) {
      setFieldErrors((e) => {
        const next = { ...e }; delete next[key as string]; return next;
      });
    }
  }

  const resources =
    userPerms.data?.resources
    ?? storePerms.data?.resources
    ?? FALLBACK_RESOURCES;
  const actions =
    userPerms.data?.actions
    ?? storePerms.data?.actions
    ?? FALLBACK_ACTIONS;

  function seedCustomMatrix(): PermMatrix {
    // Start "Custom" from what the user can do TODAY: their
    // resolved matrix on edit, their role's store matrix on create.
    if (isEdit && userPerms.data) {
      return structuredClone(userPerms.data.matrix);
    }
    const roleMatrix = storePerms.data?.matrix?.[draft.role];
    if (roleMatrix) return structuredClone(roleMatrix);
    return emptyMatrix(resources, actions);
  }

  function setAccess(mode: AccessMode) {
    setDraft((d) => {
      let perm = d.perm;
      if (mode === "hr") perm = hrMatrix(resources, actions);
      else if (mode === "bookkeeper") perm = bookkeeperMatrix(resources, actions);
      else if (mode === "custom") perm = perm ?? seedCustomMatrix();
      else perm = null;
      return { ...d, access: mode, perm };
    });
  }

  function togglePerm(resource: string, action: string) {
    setDraft((d) => {
      if (!d.perm) return d;
      const perm = structuredClone(d.perm);
      perm[resource] = perm[resource] ?? {};
      perm[resource][action] = !perm[resource][action];
      // Hand-editing any box means the matrix is theirs now.
      return { ...d, access: "custom", perm };
    });
  }

  if (
    !identity
    || (identity.role !== "admin" && identity.role !== "owner")
  ) {
    return (
      <PageShell maxWidth="36rem">
        <PageHeader title="User Management" />
        <p>You need a store-admin sign-in to manage users.</p>
      </PageShell>
    );
  }

  if (isEdit && detail.isLoading) {
    return (
      <PageShell maxWidth="36rem">
        <PageHeader title="Edit User" />
        <Loading />
      </PageShell>
    );
  }
  if (isEdit && (detail.isError || !detail.data)) {
    return (
      <PageShell maxWidth="36rem">
        <PageHeader title="Edit User" />
        <ErrorState
          message={`Couldn't load this user.${detail.error instanceof Error ? ` ${detail.error.message}` : ""}`}
          onRetry={() => { void detail.refetch(); }}
        />
      </PageShell>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setServerError(null);
    setFieldErrors({});
    try {
      const moduleAccess = draft.restrict ? draft.modules : null;
      const wantsCustom = draft.access !== "role" && draft.perm != null;
      if (isEdit) {
        const body: AdminUserUpdateBody = {
          full_name: draft.full_name,
          role:      draft.role,
          is_active: draft.is_active,
          module_access: moduleAccess,
        };
        if (draft.password) body.password = draft.password;
        await updateAdminUser(uid, body);
        // Custom access saves through the R-1 overlay endpoints —
        // only when it actually changed (each write revokes the
        // user's sessions, so no-op saves shouldn't log them out).
        if (!isSelf) {
          const hadCustom = baseline.access !== "role";
          const permChanged =
            wantsCustom !== hadCustom
            || (wantsCustom
                && JSON.stringify(draft.perm)
                   !== JSON.stringify(baseline.perm));
          if (permChanged && wantsCustom && draft.perm) {
            await setAdminUserPermissions(uid, draft.perm);
          } else if (permChanged && !wantsCustom && hadCustom) {
            await clearAdminUserPermissions(uid);
          }
        }
      } else {
        const body: AdminUserCreateBody = {
          username:  draft.username.trim(),
          password:  draft.password,
          full_name: draft.full_name,
          role:      draft.role,
          module_access: moduleAccess,
        };
        if (wantsCustom && draft.perm) body.permissions = draft.perm;
        await createAdminUser(body);
      }
      // Invalidate roster + this user's detail cache so the next
      // visit to /admin/users shows the updated row.
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      navigate("/admin/users");
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const detailBody = (err.body as {
          detail?: string | { field_errors?: Record<string, string> };
        })?.detail;
        if (detailBody && typeof detailBody === "object" && detailBody.field_errors) {
          setFieldErrors(detailBody.field_errors);
        } else {
          setServerError(err.message);
        }
      } else if (err instanceof ApiError) {
        setServerError(err.message);
      } else {
        setServerError("Network error. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell maxWidth="36rem">

      <Breadcrumbs crumbs={[{ label: "User Management", to: "/admin/users" }, { label: isEdit ? "Edit User" : "Add User" }]} />

      <PageHeader title={isEdit ? "Edit User" : "Add User"} />

      <Card>
        <div className={styles.cardHeader}>
          <span className={styles.cardHeaderText}>
            {isEdit ? "Update user account" : "Create a new user account"}
          </span>
        </div>

        {serverError && <Alert tone="error">{serverError}</Alert>}

        <form
          onSubmit={onSubmit}
          autoComplete="off"
          style={{ display: "flex", flexDirection: "column", gap: space.lg, marginTop: space.lg }}
        >
          {!isEdit ? (
            <Field label="Username *" error={fieldErrors.username}>
              <Input
                type="text" maxLength={80} required
                placeholder="e.g. maria.lopez"
                value={draft.username}
                onChange={(e) => set("username", e.target.value)}
                disabled={busy}
              />
            </Field>
          ) : (
            <Field label="Username">
              <Input
                type="text" disabled
                value={draft.username}
                style={{ opacity: 0.7, cursor: "not-allowed" }}
              />
            </Field>
          )}

          <Field label="Full Name" error={fieldErrors.full_name}>
            <Input
              type="text" maxLength={120}
              placeholder="Employee's full name"
              value={draft.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              disabled={busy}
            />
          </Field>

          <Field
            label="Role *"
            error={fieldErrors.role}
            hint={isSelf ? "You can't change your own role. Ask another admin to do it." : undefined}
          >
            <Select
              value={draft.role}
              onChange={(e) => set("role", e.target.value)}
              disabled={busy || isSelf}
            >
              <option value="employee">Employee (Transfer only)</option>
              <option value="admin">Super Admin (Full access)</option>
            </Select>
          </Field>

          {!isSelf && (
            <Field
              label="Access"
              hint="What this user can actually do — enforced on every request, not just hidden in the UI. Pick a preset or customize per area."
            >
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                <Select
                  value={draft.access}
                  onChange={(e) => setAccess(e.target.value as AccessMode)}
                  disabled={busy}
                >
                  <option value="role">
                    {draft.role === "admin"
                      ? "Full access (role default)"
                      : "Standard employee access (role default)"}
                  </option>
                  <option value="hr">HR &amp; payroll — time clock only, no financials</option>
                  <option value="bookkeeper">Bookkeeper — view books, move no money</option>
                  <option value="custom">Custom — pick exactly what they can do</option>
                </Select>
                {draft.access !== "role" && draft.perm && (
                  <div style={{ overflowX: "auto" }}>
                    <table className={styles.matrix}>
                      <thead>
                        <tr>
                          <th>Area</th>
                          {actions.map((a) => (
                            <th key={a}>{ACTION_LABELS[a] ?? a}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {resources.map((resource) => (
                          <tr key={resource}>
                            <td>{RESOURCE_LABELS[resource] ?? resource}</td>
                            {actions.map((action) => (
                              <td key={action}>
                                <div className={styles.checkCell}>
                                  <Checkbox
                                    checked={draft.perm?.[resource]?.[action] ?? false}
                                    onChange={() => togglePerm(resource, action)}
                                    disabled={busy}
                                  >{""}</Checkbox>
                                </div>
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </Field>
          )}

          <Field
            label="Module access"
            error={fieldErrors.module_access}
            hint="Which parts of the app this user sees. Restricting hides modules from their navigation — use Access above to change what they can actually do."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
              <label className={styles.checkboxRow}>
                <input
                  type="radio" name="module-access-mode"
                  checked={!draft.restrict}
                  onChange={() => set("restrict", false)}
                  disabled={busy}
                />
                <span className={styles.checkboxLabel}>
                  All store modules
                </span>
              </label>
              <label className={styles.checkboxRow}>
                <input
                  type="radio" name="module-access-mode"
                  checked={draft.restrict}
                  onChange={() => set("restrict", true)}
                  disabled={busy}
                />
                <span className={styles.checkboxLabel}>
                  Only selected modules
                </span>
              </label>
              {draft.restrict && (
                <div style={{
                  display: "flex", flexDirection: "column",
                  gap: "0.35rem", paddingLeft: "1.6rem",
                }}>
                  {(session.data?.features ?? Object.keys(MODULE_LABELS))
                    .map((key) => (
                      <label key={key} className={styles.checkboxRow}>
                        <input
                          type="checkbox"
                          checked={draft.modules.includes(key)}
                          onChange={(e) => set(
                            "modules",
                            e.target.checked
                              ? [...draft.modules, key]
                              : draft.modules.filter((k) => k !== key),
                          )}
                          disabled={busy}
                        />
                        <span className={styles.checkboxLabel}>
                          {MODULE_LABELS[key] ?? key}
                        </span>
                      </label>
                    ))}
                </div>
              )}
            </div>
          </Field>

          <Field
            label={
              isEdit
                ? "Password (leave blank to keep current)"
                : "Password *"
            }
            error={fieldErrors.password}
          >
            <Input
              type="password" maxLength={200}
              placeholder="Set password"
              required={!isEdit}
              value={draft.password}
              onChange={(e) => set("password", e.target.value)}
              disabled={busy}
            />
          </Field>

          {isEdit && (
            <Field
              label=""
              error={fieldErrors.is_active}
              hint={isSelf ? "You can't deactivate your own account. Ask another admin to do it." : undefined}
            >
              <label className={styles.checkboxRow}>
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => set("is_active", e.target.checked)}
                  disabled={busy || isSelf}
                />
                <span className={styles.checkboxLabel}>
                  Account is active
                </span>
              </label>
            </Field>
          )}

          <div style={{ marginTop: space.sm, display: "flex", gap: "0.6rem" }}>
            <Button type="submit" busy={busy} disabled={busy}>
              {busy ? "Saving…" : (isEdit ? "Save Changes" : "Create User")}
            </Button>
            <Button
              type="button"
              tone="secondary"
              onClick={() => guard.confirmLeave(() => navigate("/admin/users"))}
              disabled={busy}
            >
              Cancel
            </Button>
          </div>
        </form>
      </Card>

      <ConfirmDialog {...guard.dialogProps} />
    </PageShell>
  );
}
