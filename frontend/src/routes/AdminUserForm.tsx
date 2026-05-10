import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createAdminUser, updateAdminUser, useAdminUser,
  type AdminUserCreateBody, type AdminUserUpdateBody,
} from "../api/admin";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// /app/admin/users/new and /app/admin/users/:uid/edit — combined
// create + edit form. Mirrors the legacy admin_user_form.html
// surface 1:1 (username on create only, password optional on
// edit, role pick, is_active checkbox on edit). Field-level
// errors come back as 422 with `field_errors` (mirroring the
// AccountProfile pattern).

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
  const [draft, setDraft] = useState<{
    username:  string;
    full_name: string;
    role:      string;
    is_active: boolean;
    password:  string;
  }>(() => ({
    username:  "",
    full_name: "",
    role:      "employee",
    is_active: true,
    password:  "",
  }));
  const [busy, setBusy]   = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!isEdit || !detail.data) return;
    const u = detail.data.user;
    setDraft({
      username:  u.username,
      full_name: u.full_name,
      role:      u.role || "employee",
      is_active: u.is_active,
      password:  "",
    });
  }, [isEdit, detail.data]);

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>User Management</h1>
        <p style={emptyStyle}>
          You need a store-admin sign-in to manage users.
        </p>
      </main>
    );
  }

  if (isEdit && detail.isLoading) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit User</h1>
        <p style={mutedStyle}>Loading…</p>
      </main>
    );
  }
  if (isEdit && (detail.isError || !detail.data)) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit User</h1>
        <p style={errorStyle}>
          Couldn't load this user.
          {detail.error instanceof Error ? ` ${detail.error.message}` : ""}
        </p>
        <Link to="/admin/users" style={btnOutlineStyle}>← Back</Link>
      </main>
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
    <main style={pageStyle}>
      <header style={{ marginBottom: "1rem" }}>
        <h1 style={titleStyle}>{isEdit ? "Edit User" : "Add User"}</h1>
      </header>

      <section style={cardStyle}>
        <div style={cardHeaderStyle}>
          <span style={cardHeaderTextStyle}>
            {isEdit ? "Update user account" : "Create a new user account"}
          </span>
          <Link to="/admin/users" style={btnOutlineSmStyle}>← Back</Link>
        </div>

        {serverError && <div style={alertErrorStyle}>{serverError}</div>}

        <form onSubmit={onSubmit} autoComplete="off">
          {!isEdit ? (
            <Field label="Username *" error={fieldErrors.username}>
              <input
                type="text" maxLength={80} required
                placeholder="e.g. maria.lopez"
                value={draft.username}
                onChange={(e) => set("username", e.target.value)}
                disabled={busy} style={inputStyle}
              />
            </Field>
          ) : (
            <Field label="Username">
              <input
                type="text" disabled
                value={draft.username}
                style={{ ...inputStyle, opacity: 0.7, cursor: "not-allowed" }}
              />
            </Field>
          )}

          <Field label="Full Name" error={fieldErrors.full_name}>
            <input
              type="text" maxLength={120}
              placeholder="Employee's full name"
              value={draft.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              disabled={busy} style={inputStyle}
            />
          </Field>

          <Field label="Role *" error={fieldErrors.role}>
            <select
              value={draft.role}
              onChange={(e) => set("role", e.target.value)}
              disabled={busy || isSelf}
              style={inputStyle}
            >
              <option value="employee">Employee (Transfer only)</option>
              <option value="admin">Super Admin (Full access)</option>
            </select>
            {isSelf && (
              <span style={hintStyle}>
                You can't change your own role. Ask another admin
                to do it.
              </span>
            )}
          </Field>

          <Field
            label={
              isEdit
                ? "Password (leave blank to keep current)"
                : "Password *"
            }
            error={fieldErrors.password}
          >
            <input
              type="password" maxLength={200}
              placeholder="Set password"
              required={!isEdit}
              value={draft.password}
              onChange={(e) => set("password", e.target.value)}
              disabled={busy} style={inputStyle}
            />
          </Field>

          {isEdit && (
            <Field label="" error={fieldErrors.is_active}>
              <label style={checkboxRowStyle}>
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => set("is_active", e.target.checked)}
                  disabled={busy || isSelf}
                />
                <span style={checkboxLabelStyle}>
                  Account is active
                </span>
              </label>
              {isSelf && (
                <span style={hintStyle}>
                  You can't deactivate your own account. Ask another
                  admin to do it.
                </span>
              )}
            </Field>
          )}

          <div style={{ marginTop: "1.5rem", display: "flex", gap: "0.6rem" }}>
            <button
              type="submit" disabled={busy} style={btnPrimaryStyle}
            >
              {busy ? "Saving…" : (isEdit ? "Save Changes" : "Create User")}
            </button>
            <Link to="/admin/users" style={btnOutlineStyle}>Cancel</Link>
          </div>
        </form>
      </section>
    </main>
  );
}


function Field({
  label, error, children,
}: {
  label:    string;
  error?:   string;
  children: React.ReactNode;
}) {
  return (
    <label style={fieldStyle}>
      {label && <span style={labelStyle}>{label}</span>}
      {children}
      {error && <span style={fieldErrorStyle}>{error}</span>}
    </label>
  );
}


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  padding: "2rem 1.5rem", maxWidth: "36rem",
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
  borderRadius: "0.75rem", padding: "1.5rem",
};

const cardHeaderStyle: React.CSSProperties = {
  display: "flex", alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "1.25rem",
  gap: "0.5rem",
};

const cardHeaderTextStyle: React.CSSProperties = {
  fontWeight: 600, fontSize: "0.98rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
};

const fieldStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column",
  gap: "0.35rem", marginBottom: "1rem",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.7rem", letterSpacing: "0.06em",
  textTransform: "uppercase", fontWeight: 600,
  color: "var(--db-text-muted, #a3a3a3)",
};

const inputStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  background: "var(--db-bg-input, #0d0d0d)",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", fontSize: "0.95rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
};

const hintStyle: React.CSSProperties = {
  fontSize: "0.78rem", color: "var(--db-text-muted, #a3a3a3)",
};

const fieldErrorStyle: React.CSSProperties = {
  fontSize: "0.8rem", color: "var(--db-negative, #ff4d6d)",
};

const checkboxRowStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: "0.5rem",
  cursor: "pointer",
};

const checkboxLabelStyle: React.CSSProperties = {
  fontSize: "0.92rem",
  color: "var(--db-text, #e5e5e5)",
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 600, fontSize: "0.92rem",
  background: "var(--db-neon, #3fff00)",
  color: "var(--db-neon-ink, #001a0f)",
  border: "none", borderRadius: "0.5rem",
  cursor: "pointer",
};

const btnOutlineStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 500, fontSize: "0.92rem",
  background: "transparent",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
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

const alertErrorStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "1rem",
  background: "rgba(255,77,109,0.08)",
  border: "1px solid rgba(255,77,109,0.3)",
  borderRadius: "0.5rem",
  color: "var(--db-negative, #ff4d6d)",
  fontSize: "0.88rem",
};

const mutedStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
};

const errorStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-negative, #ff4d6d)",
};

const emptyStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
};
