import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { resetPassword } from "../api/account";
import { ApiError } from "../lib/api";

// /app/reset-password?token=… — consume a one-time token to set
// a new password. Token comes from the email link.

export default function ResetPassword() {
  const [sp]       = useSearchParams();
  const navigate    = useNavigate();
  const token       = sp.get("token") ?? "";
  const [pw,       setPw]       = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [busy,     setBusy]     = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [done,     setDone]     = useState(false);

  if (!token) {
    return (
      <main style={pageStyle}>
        <div style={cardStyle}>
          <h1 style={titleStyle}>Reset link missing</h1>
          <p style={{ margin: 0, color: "var(--db-text-muted, #a3a3a3)" }}>
            This link doesn't include a token.{" "}
            <Link
              to="/forgot-password"
              style={{ color: "var(--db-accent, #3fff00)" }}
            >
              Request a new reset link
            </Link>
            .
          </p>
        </div>
      </main>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (pw !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword({
        token,
        new_password: pw,
        confirm_password: confirm,
      });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reset password. The link may be expired.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={pageStyle}>
      <div style={cardStyle}>
        {done ? (
          <>
            <h1 style={titleStyle}>Password updated</h1>
            <p
              style={{
                margin: "0 0 1.5rem",
                color: "var(--db-text-muted, #a3a3a3)",
                lineHeight: 1.6,
              }}
            >
              You can now sign in with your new password.
            </p>
            <button
              type="button"
              onClick={() => navigate("/login")}
              style={buttonStyle}
            >
              Sign in
            </button>
          </>
        ) : (
          <>
            <h1 style={titleStyle}>Set a new password</h1>
            <form
              onSubmit={onSubmit}
              style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
            >
              <Field label="New password (≥ 8 chars)">
                <input
                  type="password" required minLength={8}
                  autoComplete="new-password"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  disabled={busy}
                  style={inputStyle}
                />
              </Field>
              <Field label="Confirm new password">
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
                disabled={busy || !pw || !confirm}
                style={{
                  ...buttonStyle,
                  opacity: busy || !pw || !confirm ? 0.6 : 1,
                  cursor: busy ? "wait" : "pointer",
                }}
              >
                {busy ? "Saving…" : "Update password"}
              </button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}

function Field({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span style={{ fontSize: "0.85rem", color: "var(--db-text-muted, #a3a3a3)" }}>
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
  alignItems: "center",
  justifyContent: "center",
  padding: "2rem 1rem",
};

const cardStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: "26rem",
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "2rem",
  boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "1.5rem",
  fontWeight: 600,
  margin: "0 0 0.75rem",
};

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
  cursor: "pointer",
};
