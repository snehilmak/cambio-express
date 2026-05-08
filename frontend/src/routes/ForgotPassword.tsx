import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { forgotPassword } from "../api/account";

// /app/forgot-password — request a reset link.
//
// Per the CLAUDE.md security invariant the response is always
// "Check your email" regardless of whether the address exists.
// We mirror that on the SPA: success message is the same shape
// no matter what the server returned.

export default function ForgotPassword() {
  const [email,    setEmail]    = useState("");
  const [busy,     setBusy]     = useState(false);
  const [done,     setDone]     = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await forgotPassword(email.trim());
    } catch {
      // Server responds 200 even on unknown email; if a network
      // hiccup loses the request, still show the success state
      // so we don't leak whether the address was known.
    } finally {
      setBusy(false);
      setDone(true);
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
        <h1 style={titleStyle}>Reset your password</h1>
        {done ? (
          <p
            style={{
              margin: "0 0 0.5rem",
              color: "var(--db-text, #f5f5f5)",
              lineHeight: 1.6,
            }}
          >
            If <code>{email}</code> is registered, you'll receive an
            email with a link to set a new password. Check your inbox.
          </p>
        ) : (
          <>
            <p
              style={{
                margin: "0 0 1.5rem",
                color: "var(--db-text-muted, #a3a3a3)",
                fontSize: "0.95rem",
              }}
            >
              Enter the email you used to sign up. We'll send a one-time
              link valid for 1 hour.
            </p>
            <form
              onSubmit={onSubmit}
              style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
            >
              <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--db-text-muted, #a3a3a3)" }}>Email</span>
                <input
                  type="email" required autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={busy}
                  style={inputStyle}
                />
              </label>
              <button
                type="submit"
                disabled={busy || !email}
                style={{
                  ...buttonStyle,
                  opacity: busy || !email ? 0.6 : 1,
                  cursor: busy ? "wait" : "pointer",
                }}
              >
                {busy ? "Sending…" : "Send reset link"}
              </button>
            </form>
          </>
        )}
        <p
          style={{
            margin: "1.5rem 0 0",
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
            textAlign: "center",
          }}
        >
          <Link
            to="/login"
            style={{ color: "var(--db-accent, #3fff00)", textDecoration: "none" }}
          >
            ← Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

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
};
