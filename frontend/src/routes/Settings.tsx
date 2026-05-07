import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  updateStoreInfo,
  useStoreInfo,
} from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// Account settings page at /app/settings. v1 ships the
// change-password card; subsequent PRs add profile / preferences /
// 2FA / passkey management.

export default function Settings() {
  const identity = getCurrentIdentity();

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Settings</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
          }}
        >
          {identity?.username || "—"}
        </p>
      </header>

      <StoreInfoCard />
      <ChangePasswordCard />
    </main>
  );
}

function StoreInfoCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError } = useStoreInfo();

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
        <p style={{ margin: 0, color: "var(--db-text-muted, #a3a3a3)" }}>Loading…</p>
      </section>
    );
  }
  if (isError || !data) {
    return (
      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Store</h2>
        <p
          style={{
            margin: 0,
            color: "var(--db-negative, #ff3b30)",
          }}
        >
          Could not load store info.
        </p>
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

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "60rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
  gap: "1rem",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

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
