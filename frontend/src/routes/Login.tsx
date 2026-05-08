import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: number;
  username: string;
  full_name: string;
  role: string;
  store_id: number | null;
  permissions: string[];
}

interface LocationState {
  from?: string;
}

// Login screen for the SPA. Posts to /api/v2/auth/login-cross-store —
// the cookieless endpoint that finds the user's home store from
// just username + password (employees rejected, see the FastAPI
// service for parity with the legacy `/login` POST).
//
// On success we stash the JWT in localStorage and route to either
// the page the user originally tried to reach (when RequireAuth
// bounced them here) or the dashboard.
export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [busy, setBusy]         = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const dest = (location.state as LocationState | null)?.from || "/dashboard";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await api<LoginResponse>("/api/v2/auth/login-cross-store", {
        method: "POST",
        json: { username: username.trim(), password },
      });
      setAccessToken(result.access_token);
      navigate(dest, { replace: true });
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Network error. Please try again.";
      setError(msg);
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
          Sign in
        </h1>
        <p
          style={{
            margin: "0 0 1.5rem",
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.95rem",
          }}
        >
          DineroBook · new experience preview
        </p>
        <form
          onSubmit={onSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <span
              style={{
                fontSize: "0.85rem",
                color: "var(--db-text-muted, #a3a3a3)",
              }}
            >
              Username
            </span>
            <input
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <span
              style={{
                fontSize: "0.85rem",
                color: "var(--db-text-muted, #a3a3a3)",
                display: "flex",
                justifyContent: "space-between",
              }}
            >
              <span>Password</span>
              <Link
                to="/forgot-password"
                style={{
                  color: "var(--db-text-muted, #a3a3a3)",
                  fontSize: "0.78rem",
                  textDecoration: "none",
                }}
              >
                Forgot?
              </Link>
            </span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              style={inputStyle}
            />
          </label>
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
            disabled={busy || !username || !password}
            style={{
              ...buttonStyle,
              opacity: busy || !username || !password ? 0.6 : 1,
              cursor: busy || !username || !password ? "wait" : "pointer",
            }}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p
          style={{
            margin: "1.5rem 0 0.5rem",
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
            textAlign: "center",
          }}
        >
          Employees: please use your store's sign-in URL.
        </p>
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
            textAlign: "center",
          }}
        >
          New here?{" "}
          <Link
            to="/signup"
            style={{
              color: "var(--db-accent, #3fff00)",
              textDecoration: "none",
            }}
          >
            Create your store
          </Link>
        </p>
      </div>
    </main>
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
  transition: "border-color 150ms ease",
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
  transition: "transform 120ms ease, opacity 120ms ease",
};
