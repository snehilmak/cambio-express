import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { signup } from "../api/account";
import { ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";

// Self-service signup at /app/signup. Same shape as the legacy
// /signup Jinja form: store name + email + password + optional
// phone. On success the server returns a JWT scoped to the new
// store; we drop the user straight onto /dashboard.

export default function Signup() {
  const navigate = useNavigate();
  const [storeName, setStoreName] = useState("");
  const [email,     setEmail]     = useState("");
  const [phone,     setPhone]     = useState("");
  const [password,  setPassword]  = useState("");
  const [confirm,   setConfirm]   = useState("");
  const [busy,      setBusy]      = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [field,     setField]     = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setField(null);
    if (password !== confirm) {
      setError("Passwords do not match.");
      setField("confirm");
      return;
    }
    setBusy(true);
    try {
      const result = await signup({
        store_name: storeName.trim(),
        email:      email.trim(),
        password,
        phone:      phone.trim(),
      });
      setAccessToken(result.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (err.body && typeof err.body === "object" && "detail" in err.body) {
          const detail = (err.body as Record<string, unknown>).detail;
          if (
            detail &&
            typeof detail === "object" &&
            "field" in (detail as Record<string, unknown>)
          ) {
            setField(String((detail as Record<string, unknown>).field));
          }
        }
      } else {
        setError("Could not create account. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1rem",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "26rem",
          background: "var(--db-surface-2, #141414)",
          border: "1px solid var(--db-border, #262626)",
          borderRadius: "0.75rem",
          padding: "2rem",
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        }}
      >
        <h1
          style={{
            fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
            fontSize: "1.5rem",
            fontWeight: 600,
            margin: "0 0 0.25rem",
          }}
        >
          Create your store
        </h1>
        <p
          style={{
            margin: "0 0 1.5rem",
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.95rem",
          }}
        >
          7-day free trial · DineroBook
        </p>
        <form
          onSubmit={onSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <Field label="Store name" highlight={field === "store_name"}>
            <input
              type="text" required
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </Field>
          <Field label="Email" highlight={field === "email"}>
            <input
              type="email" required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </Field>
          <Field label="Phone (optional)">
            <input
              type="tel"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </Field>
          <Field label="Password (≥ 8 chars)" highlight={field === "password"}>
            <input
              type="password" required minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </Field>
          <Field label="Confirm password" highlight={field === "confirm"}>
            <input
              type="password" required minLength={8}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </Field>
          {error && (
            <p
              role="alert"
              style={{
                margin: 0,
                color: "var(--db-negative, #ff3b30)",
                fontSize: "0.9rem",
              }}
            >
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy || !storeName || !email || !password || !confirm}
            style={{
              ...buttonStyle,
              opacity:
                busy || !storeName || !email || !password || !confirm ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Creating…" : "Create store"}
          </button>
        </form>
        <p
          style={{
            margin: "1.5rem 0 0",
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
            textAlign: "center",
          }}
        >
          Already have an account?{" "}
          <Link
            to="/login"
            style={{ color: "var(--db-accent, #3fff00)", textDecoration: "none" }}
          >
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

function Field({
  label, highlight, children,
}: {
  label: string;
  highlight?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span
        style={{
          fontSize: "0.85rem",
          color: highlight
            ? "var(--db-negative, #ff3b30)"
            : "var(--db-text-muted, #a3a3a3)",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.65rem 0.85rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "1rem",
  outline: "none",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "var(--db-on-accent, #0a0a0a)",
  border: "none",
  borderRadius: "0.5rem",
  padding: "0.75rem 1rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "1rem",
  fontWeight: 600,
  letterSpacing: "0.01em",
};
