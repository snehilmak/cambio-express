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
  requires_totp: boolean;
  pending_token: string | null;
  has_recovery_codes: boolean;
}

interface LocationState {
  from?: string;
}

interface PendingState {
  pending_token: string;
  has_recovery_codes: boolean;
}

// Login screen for the SPA. Two-step flow when the user's role
// requires 2FA (today: superadmin enrolled in TOTP):
//
//   step 1: POST /api/v2/auth/login-cross-store with creds.
//           If `requires_totp=true`, hold pending_token and show
//           the 6-digit code prompt.
//   step 2: POST /api/v2/auth/login/totp with {pending_token, code}
//           OR /auth/login/recovery with a recovery code.
//
// Single-step flow (admin / owner / employee) gets the access
// token immediately and routes to the dashboard.
export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [busy, setBusy]         = useState(false);
  const [pending, setPending]   = useState<PendingState | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const dest = (location.state as LocationState | null)?.from || "/dashboard";

  function finishLogin(token: string) {
    setAccessToken(token);
    navigate(dest, { replace: true });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await api<LoginResponse>("/api/v2/auth/login-cross-store", {
        method: "POST",
        json: { username: username.trim(), password },
      });
      if (result.requires_totp && result.pending_token) {
        setPending({
          pending_token: result.pending_token,
          has_recovery_codes: result.has_recovery_codes,
        });
      } else {
        finishLogin(result.access_token);
      }
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

  if (pending) {
    return (
      <SecondFactor
        state={pending}
        onSuccess={finishLogin}
        onCancel={() => {
          setPending(null);
          setError(null);
        }}
      />
    );
  }

  return (
    <main style={shellStyle}>
      <div style={cardStyle}>
        <h1 style={titleStyle}>Sign in</h1>
        <p style={subTitleStyle}>DineroBook · new experience preview</p>
        <form
          onSubmit={onSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <label style={labelStyle}>
            <span style={labelTextStyle}>Username</span>
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
          <label style={labelStyle}>
            <span style={{ ...labelTextStyle, display: "flex", justifyContent: "space-between" }}>
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
          {error && <ErrorLine>{error}</ErrorLine>}
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
        <p style={footerStyle}>
          Employees: please use your store's sign-in URL.
        </p>
        <p style={footerStyle}>
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

function SecondFactor({
  state, onSuccess, onCancel,
}: {
  state: PendingState;
  onSuccess: (token: string) => void;
  onCancel: () => void;
}) {
  const [mode, setMode]   = useState<"totp" | "recovery">("totp");
  const [code, setCode]   = useState("");
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setBusy(true);
    const url =
      mode === "totp"
        ? "/api/v2/auth/login/totp"
        : "/api/v2/auth/login/recovery";
    try {
      const result = await api<LoginResponse>(url, {
        method: "POST",
        json: { pending_token: state.pending_token, code: code.trim() },
      });
      if (result.access_token) {
        onSuccess(result.access_token);
      } else {
        setError("Server returned an unexpected response.");
      }
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
    <main style={shellStyle}>
      <div style={cardStyle}>
        <h1 style={titleStyle}>Two-factor verification</h1>
        <p style={subTitleStyle}>
          {mode === "totp"
            ? "Enter the 6-digit code from your authenticator app."
            : "Enter one of your single-use recovery codes."}
        </p>
        <form
          onSubmit={onSubmit}
          style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
        >
          <label style={labelStyle}>
            <span style={labelTextStyle}>
              {mode === "totp" ? "Verification code" : "Recovery code"}
            </span>
            <input
              type="text"
              autoComplete="one-time-code"
              autoFocus
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={busy}
              inputMode={mode === "totp" ? "numeric" : "text"}
              pattern={mode === "totp" ? "[0-9]*" : undefined}
              placeholder={mode === "totp" ? "123456" : "ABCD-1234"}
              style={{
                ...inputStyle,
                fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                fontSize: "1.15rem",
                letterSpacing: "0.1em",
              }}
            />
          </label>
          {error && <ErrorLine>{error}</ErrorLine>}
          <button
            type="submit"
            disabled={busy || !code}
            style={{
              ...buttonStyle,
              opacity: busy || !code ? 0.6 : 1,
              cursor: busy || !code ? "wait" : "pointer",
            }}
          >
            {busy ? "Verifying…" : "Verify"}
          </button>
        </form>
        <div
          style={{
            marginTop: "1rem",
            display: "flex",
            justifyContent: "space-between",
            fontSize: "0.85rem",
          }}
        >
          {mode === "totp" && state.has_recovery_codes && (
            <button
              type="button"
              onClick={() => { setMode("recovery"); setCode(""); setError(null); }}
              style={linkBtnStyle}
            >
              Use a recovery code
            </button>
          )}
          {mode === "recovery" && (
            <button
              type="button"
              onClick={() => { setMode("totp"); setCode(""); setError(null); }}
              style={linkBtnStyle}
            >
              Back to authenticator code
            </button>
          )}
          <button
            type="button"
            onClick={onCancel}
            style={linkBtnStyle}
          >
            Cancel
          </button>
        </div>
      </div>
    </main>
  );
}

function ErrorLine({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      style={{
        margin: 0,
        color: "var(--db-negative, #ff3b30)",
        fontSize: "0.9rem",
      }}
    >
      {children}
    </p>
  );
}

const shellStyle: React.CSSProperties = {
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
  margin: "0 0 0.25rem",
};

const subTitleStyle: React.CSSProperties = {
  margin: "0 0 1.5rem",
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.95rem",
};

const labelStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: "0.4rem",
};

const labelTextStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
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

const linkBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text-muted, #a3a3a3)",
  border: "none",
  padding: 0,
  fontSize: "0.85rem",
  textDecoration: "underline",
  cursor: "pointer",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
};

const footerStyle: React.CSSProperties = {
  margin: "1.5rem 0 0",
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
  textAlign: "center",
};
