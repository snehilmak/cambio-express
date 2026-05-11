import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  createTeamMember,
  deactivateTeamMember,
  deletePasskey,
  passkeysSupported,
  registerPasskey,
  updateStoreInfo,
  updateTeamMember,
  usePasskeys,
  useStoreInfo,
  useTeam,
  type TeamMemberRow,
} from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { ErrorState, Loading, PageHeader, PageShell } from "../components/ui";

// Account settings page at /app/settings. v1 ships the
// change-password card; subsequent PRs add profile / preferences /
// 2FA / passkey management.

export default function Settings() {
  const identity = getCurrentIdentity();

  return (
    <PageShell maxWidth="60rem" gap="1rem">
      <PageHeader title="Settings" subtitle={identity?.username || "—"} />

      <StoreInfoCard />
      <SubscriptionCard />
      <TeamCard />
      <ChangePasswordCard />
      <PasskeysCard />
    </PageShell>
  );
}

function PasskeysCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, refetch } = usePasskeys();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const supported = passkeysSupported();

  if (identity == null) return null;

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["account", "passkeys"] });
  }

  async function remove(id: number, label: string) {
    if (!confirm(`Remove "${label || "this device"}"?`)) return;
    setErr(null); setBusyId(id);
    try {
      await deletePasskey(id);
      refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not remove device.");
    } finally {
      setBusyId(null);
    }
  }

  async function add() {
    setErr(null); setAddBusy(true);
    try {
      await registerPasskey(newName.trim());
      setAdding(false);
      setNewName("");
      refresh();
    } catch (e) {
      // navigator.credentials.create() rejects on cancel / wrong
      // device / etc. with browser-specific messages — surface
      // them as-is so users see the actual reason.
      const msg = e instanceof ApiError
        ? e.message
        : (e instanceof Error ? e.message : "Could not create passkey.");
      setErr(msg);
    } finally {
      setAddBusy(false);
    }
  }

  return (
    <section style={cardStyle}>
      <div style={{
        display: "flex", alignItems: "center", gap: "0.75rem",
        marginBottom: "0.6rem",
      }}>
        <h2 style={{ ...sectionTitleStyle, flex: 1, margin: 0 }}>Passkeys</h2>
        {supported && !adding && (
          <button
            type="button" onClick={() => { setAdding(true); setErr(null); }}
            style={miniBtnStyle}
          >
            + Add a passkey
          </button>
        )}
      </div>
      <p
        style={{
          margin: "0 0 1rem",
          fontSize: "0.85rem",
          color: "var(--db-text-muted, #a3a3a3)",
        }}
      >
        Sign in with your device (Touch ID, Face ID, Windows Hello,
        or a hardware key) instead of a password. Passkeys are
        phishing-resistant and count as two-factor auth, so a passkey
        login skips the verification-code step.
      </p>
      {!supported && (
        <p style={{
          margin: "0 0 1rem", padding: "0.55rem 0.85rem",
          background: "rgba(94,169,255,0.08)",
          border: "1px solid rgba(94,169,255,0.3)",
          borderRadius: "0.5rem",
          color: "var(--db-info, #5ea9ff)",
          fontSize: "0.85rem",
        }}>
          This browser doesn't expose the WebAuthn API, so passkeys
          aren't available here. Use a modern Chrome, Safari, Firefox,
          or Edge build.
        </p>
      )}
      {adding && (
        <div style={{
          marginBottom: "1rem", padding: "0.85rem",
          background: "var(--db-bg-input, #0d0d0d)",
          border: "1px solid var(--db-border, #262626)",
          borderRadius: "0.5rem",
        }}>
          <label style={{
            display: "block", marginBottom: "0.4rem",
            fontSize: "0.78rem", letterSpacing: "0.05em",
            textTransform: "uppercase", fontWeight: 600,
            color: "var(--db-text-muted, #a3a3a3)",
          }}>
            Nickname for this passkey
          </label>
          <input
            type="text" value={newName} maxLength={120}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="e.g. MacBook Touch ID"
            autoFocus disabled={addBusy}
            style={{
              width: "100%", boxSizing: "border-box",
              padding: "0.55rem 0.7rem",
              background: "var(--db-surface-2, #141414)",
              color: "var(--db-text, #e5e5e5)",
              border: "1px solid var(--db-border, #262626)",
              borderRadius: "0.4rem", fontSize: "0.9rem",
              marginBottom: "0.6rem",
            }}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              type="button" onClick={add} disabled={addBusy}
              style={{
                ...miniBtnStyle,
                background: "var(--db-neon, #3fff00)",
                color: "var(--db-neon-ink, #001a0f)",
                fontWeight: 600,
              }}
            >
              {addBusy ? "Creating…" : "Create passkey"}
            </button>
            <button
              type="button"
              onClick={() => { setAdding(false); setNewName(""); setErr(null); }}
              disabled={addBusy} style={miniBtnStyle}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Could not load passkeys."
          onRetry={() => { void refetch(); }}
        />
      )}
      {data && data.passkeys.length === 0 && !isLoading && (
        <p style={{ margin: 0, color: "var(--db-text-muted, #a3a3a3)" }}>
          No passkeys registered yet.
        </p>
      )}
      {data && data.passkeys.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {data.passkeys.map((p) => (
            <li
              key={p.id}
              style={{
                display: "flex",
                gap: "0.75rem",
                alignItems: "center",
                padding: "0.5rem 0",
                borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
              }}
            >
              <span style={{ flex: 1 }}>
                <div style={{ fontWeight: 500 }}>
                  {p.name || "Unnamed device"}
                </div>
                <div
                  style={{
                    fontSize: "0.78rem",
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  Added {p.created_at.slice(0, 10)}
                  {p.last_used_at &&
                    ` · last used ${p.last_used_at.slice(0, 10)}`}
                </div>
              </span>
              <button
                type="button"
                onClick={() => remove(p.id, p.name)}
                disabled={busyId === p.id}
                style={{
                  ...miniBtnStyle,
                  opacity: busyId === p.id ? 0.5 : 1,
                  cursor: busyId === p.id ? "wait" : "pointer",
                }}
              >
                {busyId === p.id ? "Removing…" : "Remove"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {err && (
        <p
          role="alert"
          style={{
            margin: "0.5rem 0 0",
            color: "var(--db-negative, #ff3b30)",
            fontSize: "0.85rem",
          }}
        >
          {err}
        </p>
      )}
    </section>
  );
}

function SubscriptionCard() {
  const identity = getCurrentIdentity();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canManage =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";
  if (!canManage || identity?.store_id == null) return null;

  async function openPortal() {
    setErr(null);
    setBusy(true);
    try {
      const { openBillingPortal } = await import("../api/billing");
      const result = await openBillingPortal();
      window.location.assign(result.url);
    } catch (e) {
      // 409 = no Stripe customer yet (trial store) — push to subscribe
      if (e instanceof ApiError && e.status === 409) {
        window.location.assign("/app/subscribe");
        return;
      }
      setErr(e instanceof ApiError ? e.message : "Could not open billing portal.");
      setBusy(false);
    }
  }

  return (
    <section style={cardStyle}>
      <h2 style={sectionTitleStyle}>Subscription</h2>
      <p
        style={{
          margin: "0 0 1rem",
          fontSize: "0.85rem",
          color: "var(--db-text-muted, #a3a3a3)",
        }}
      >
        Change plan, update payment method, or cancel — all on Stripe's
        secure billing portal. Trial stores can pick a plan instead.
      </p>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <a href="/app/subscribe" style={primaryBtnLink}>
          Choose / change plan
        </a>
        <button
          type="button"
          onClick={openPortal}
          disabled={busy}
          style={{
            ...secondaryBtn,
            opacity: busy ? 0.6 : 1,
            cursor: busy ? "wait" : "pointer",
          }}
        >
          {busy ? "Opening…" : "Manage on Stripe"}
        </button>
      </div>
      {err && (
        <p
          role="alert"
          style={{
            margin: "0.5rem 0 0",
            color: "var(--db-negative, #ff3b30)",
            fontSize: "0.85rem",
          }}
        >
          {err}
        </p>
      )}
    </section>
  );
}

function TeamCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError } = useTeam();
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  function refetch() {
    queryClient.invalidateQueries({ queryKey: ["admin", "team"] });
    // Also invalidate the transfer-form's roster hook so the
    // dropdown picks up new / removed cashiers without a reload.
    queryClient.invalidateQueries({ queryKey: ["transfers", "employees"] });
  }

  async function add() {
    setErr(null);
    setBusy(true);
    try {
      await createTeamMember(newName);
      setNewName("");
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't add member");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(m: TeamMemberRow) {
    setErr(null);
    try {
      await updateTeamMember(m.id, { is_active: !m.is_active });
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't update");
    }
  }

  async function remove(m: TeamMemberRow) {
    setErr(null);
    try {
      await deactivateTeamMember(m.id);
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't deactivate");
    }
  }

  if (identity?.store_id == null) return null;

  return (
    <section style={cardStyle}>
      <h2 style={sectionTitleStyle}>Team</h2>
      <p
        style={{
          margin: "0 0 1rem",
          fontSize: "0.85rem",
          color: "var(--db-text-muted, #a3a3a3)",
        }}
      >
        Cashier names that appear in the "Processed by" dropdown
        on the transfer form. Deactivated rows stay so historical
        transfer attribution survives.
      </p>

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Could not load team."
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 1rem" }}>
          {data.members.length === 0 && (
            <li
              style={{
                padding: "0.5rem 0",
                color: "var(--db-text-muted, #a3a3a3)",
              }}
            >
              No team members yet.
            </li>
          )}
          {data.members.map((m) => (
            <li
              key={m.id}
              style={{
                display: "flex",
                gap: "0.75rem",
                alignItems: "center",
                padding: "0.4rem 0",
                borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
              }}
            >
              <span
                style={{
                  flex: 1,
                  color: m.is_active
                    ? "var(--db-text, #f5f5f5)"
                    : "var(--db-text-muted, #a3a3a3)",
                  textDecoration: m.is_active ? "none" : "line-through",
                }}
              >
                {m.name}
              </span>
              {canEdit && (
                <>
                  <button
                    type="button"
                    onClick={() => toggle(m)}
                    style={miniBtnStyle}
                    title={m.is_active ? "Deactivate" : "Reactivate"}
                  >
                    {m.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                  {m.is_active && (
                    <button
                      type="button"
                      onClick={() => remove(m)}
                      style={miniBtnStyle}
                    >
                      ✕
                    </button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {canEdit && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New cashier name"
            style={inputStyle}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newName.trim()) {
                e.preventDefault();
                add();
              }
            }}
          />
          <button
            type="button"
            onClick={add}
            disabled={busy || !newName.trim()}
            style={{
              ...saveBtnStyle,
              opacity: busy || !newName.trim() ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
              whiteSpace: "nowrap",
            }}
          >
            + Add
          </button>
        </div>
      )}
      {err && (
        <p
          role="alert"
          style={{
            margin: "0.5rem 0 0",
            color: "var(--db-negative, #ff3b30)",
            fontSize: "0.9rem",
          }}
        >
          {err}
        </p>
      )}
    </section>
  );
}

const miniBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text-muted, #a3a3a3)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.4rem",
  padding: "0.25rem 0.6rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.8rem",
  cursor: "pointer",
};

function StoreInfoCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, refetch } = useStoreInfo();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [taxRatePct, setTaxRatePct] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  // Hydrate the form from the read-side row when it arrives.
  // Federal tax is stored as a decimal (0.01 = 1%) but operators
  // think in percents — display + edit accordingly.
  useEffect(() => {
    if (!data?.store) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable store-settings fields from server-fetched row (federal_tax_rate gets a decimal->percent conversion for display)
    setName(data.store.name);
    setEmail(data.store.email);
    setPhone(data.store.phone);
    setAddress(data.store.address);
    setTaxRatePct(((data.store.federal_tax_rate || 0) * 100).toFixed(2));
  }, [data]);

  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setOkMsg(null);
    setBusy(true);
    try {
      await updateStoreInfo({
        name, email, phone, address,
        federal_tax_rate: Number(taxRatePct) / 100,
      });
      await queryClient.invalidateQueries({
        queryKey: ["admin", "store-info"],
      });
      setOkMsg("Store info saved.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Store</h2>
        <p
          style={{
            margin: 0,
            fontSize: "0.9rem",
            color: "var(--db-text-muted, #a3a3a3)",
          }}
        >
          Sign in as a store admin to manage store info.
        </p>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Store</h2>
        <Loading />
      </section>
    );
  }
  if (isError || !data) {
    return (
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Store</h2>
        <ErrorState
          message="Could not load store info."
          onRetry={() => { void refetch(); }}
        />
      </section>
    );
  }

  return (
    <section style={cardStyle}>
      <h2 style={sectionTitleStyle}>Store</h2>
      <p
        style={{
          margin: "0 0 1rem",
          fontSize: "0.85rem",
          color: "var(--db-text-muted, #a3a3a3)",
        }}
      >
        Slug{" "}
        <code
          style={{
            fontFamily:
              "var(--db-font-mono, 'JetBrains Mono', monospace)",
            color: "var(--db-text, #f5f5f5)",
          }}
        >
          {data.store.slug}
        </code>{" "}
        · plan {data.store.plan}
      </p>
      <form
        onSubmit={onSubmit}
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(15rem, 1fr))",
          gap: "0.85rem",
        }}
      >
        <Field label="Store name">
          <input type="text" value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!canEdit}
            style={inputStyle} required />
        </Field>
        <Field label="Email">
          <input type="email" value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={!canEdit}
            style={inputStyle} />
        </Field>
        <Field label="Phone">
          <input type="tel" value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={!canEdit}
            style={inputStyle} />
        </Field>
        <Field label="Address">
          <input type="text" value={address}
            onChange={(e) => setAddress(e.target.value)}
            disabled={!canEdit}
            style={inputStyle} />
        </Field>
        <Field label="Federal tax rate (%)">
          <input type="number" step="0.01" min="0" max="100"
            value={taxRatePct}
            onChange={(e) => setTaxRatePct(e.target.value)}
            disabled={!canEdit}
            style={inputStyle} />
        </Field>
        {err && (
          <p
            role="alert"
            style={{
              margin: 0,
              gridColumn: "1 / -1",
              color: "var(--db-negative, #ff3b30)",
              fontSize: "0.9rem",
            }}
          >
            {err}
          </p>
        )}
        {okMsg && (
          <p
            role="status"
            style={{
              margin: 0,
              gridColumn: "1 / -1",
              color: "var(--db-accent, #3fff00)",
              fontSize: "0.9rem",
            }}
          >
            {okMsg}
          </p>
        )}
        {canEdit && (
          <div
            style={{
              gridColumn: "1 / -1",
              display: "flex",
              justifyContent: "flex-end",
            }}
          >
            <button
              type="submit"
              disabled={busy || !name}
              style={{
                ...saveBtnStyle,
                opacity: busy || !name ? 0.6 : 1,
                cursor: busy ? "wait" : "pointer",
              }}
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        )}
      </form>
    </section>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOkMsg(null);
    setBusy(true);
    try {
      await changePassword({
        current_password: current,
        new_password:     next,
        confirm_password: confirm,
      });
      setOkMsg("Password updated.");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not update password.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={cardStyle}>
      <h2 style={sectionTitleStyle}>Change password</h2>
      <form
        onSubmit={onSubmit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.85rem",
          maxWidth: "26rem",
        }}
      >
        <Field label="Current password">
          <input
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="New password (≥ 8 chars)">
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="Confirm new password">
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            style={inputStyle}
          />
        </Field>
        {error && (
          <p
            role="alert"
            style={{ margin: 0, color: "var(--db-negative, #ff3b30)", fontSize: "0.9rem" }}
          >
            {error}
          </p>
        )}
        {okMsg && (
          <p
            role="status"
            style={{ margin: 0, color: "var(--db-accent, #3fff00)", fontSize: "0.9rem" }}
          >
            {okMsg}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !current || !next || !confirm}
          style={{
            ...saveBtnStyle,
            opacity: busy || !current || !next || !confirm ? 0.6 : 1,
            cursor: busy ? "wait" : "pointer",
          }}
        >
          {busy ? "Saving…" : "Update password"}
        </button>
      </form>
    </section>
  );
}

function Field({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span
        style={{
          fontSize: "0.78rem",
          color: "var(--db-text-muted, #a3a3a3)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--db-text-muted, #a3a3a3)",
  margin: "0 0 1rem",
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
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

const saveBtnStyle: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "var(--db-on-accent, #0a0a0a)",
  border: "none",
  borderRadius: "0.5rem",
  padding: "0.7rem 1.25rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  fontWeight: 600,
};

const primaryBtnLink: React.CSSProperties = {
  ...saveBtnStyle,
  textDecoration: "none",
  display: "inline-flex",
  alignItems: "center",
};

const secondaryBtn: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.7rem 1.25rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
};
