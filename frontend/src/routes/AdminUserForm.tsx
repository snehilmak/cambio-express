import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createAdminUser, updateAdminUser, useAdminUser,
  type AdminUserCreateBody, type AdminUserUpdateBody,
} from "../api/admin";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, ConfirmDialog, ErrorState, Field, Input, Loading,
  PageHeader, PageShell, Select, space,
} from "../components/ui";
import { useUnsavedGuard } from "../lib/useUnsavedGuard";
import styles from "./AdminUserForm.module.css";

interface UserDraft {
  username:  string;
  full_name: string;
  role:      string;
  is_active: boolean;
  password:  string;
}

function makeBlankUser(): UserDraft {
  return { username: "", full_name: "", role: "employee", is_active: true, password: "" };
}

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

  const detail = useAdminUser(isEdit ? uid : null);

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
    const hydrated: UserDraft = {
      username:  u.username,
      full_name: u.full_name,
      role:      u.role || "employee",
      is_active: u.is_active,
      password:  "",
    };
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft + dirty baseline from server-fetched user record on edit
    setDraft(hydrated);
    setBaseline(hydrated);
  }, [isEdit, detail.data]);

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
      if (isEdit) {
        const body: AdminUserUpdateBody = {
          full_name: draft.full_name,
          role:      draft.role,
          is_active: draft.is_active,
        };
        if (draft.password) body.password = draft.password;
        await updateAdminUser(uid, body);
      } else {
        const body: AdminUserCreateBody = {
          username:  draft.username.trim(),
          password:  draft.password,
          full_name: draft.full_name,
          role:      draft.role,
        };
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
