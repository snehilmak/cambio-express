import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { LoginChrome } from "../components/LoginChrome";
import chrome from "../components/LoginChrome.module.css";
import { Alert, Button, Field, Input, Pill } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";
import styles from "./Login.module.css";

interface LoginResponse {
  access_token: string;
  requires_totp: boolean;
  pending_token: string | null;
  has_recovery_codes: boolean;
  enroll_required?: boolean;
}

interface LocationState {
  from?: string;
}

interface PendingState {
  pending_token: string;
  has_recovery_codes: boolean;
}

/** SPA sign-in. Two-step when the role requires 2FA (superadmin):
 *  step 1 POSTs creds, step 2 verifies a 6-digit TOTP or recovery
 *  code. Admin/owner/employee skip step 2 and get the token straight
 *  from /login-cross-store. */
export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [busy, setBusy]         = useState(false);
  const [pending, setPending]   = useState<PendingState | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const stateDest = (location.state as LocationState | null)?.from;

  function finishLogin(token: string) {
    setAccessToken(token);
    navigate(stateDest || "/dashboard", { replace: true });
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
        if (result.enroll_required) {
          navigate("/login/2fa/enroll", {
            state: { pending_token: result.pending_token },
            replace: true,
          });
          return;
        }
        setPending({
          pending_token: result.pending_token,
          has_recovery_codes: result.has_recovery_codes,
        });
      } else {
        finishLogin(result.access_token);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Network error. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <LoginChrome variant="flex" brandPane={<BrandPane />}>
      {pending ? (
        <SecondFactor
          state={pending}
          onSuccess={finishLogin}
          onCancel={() => { setPending(null); setError(null); }}
        />
      ) : (
        <PrimaryForm
          username={username} setUsername={setUsername}
          password={password} setPassword={setPassword}
          error={error}
          busy={busy}
          onSubmit={onSubmit}
        />
      )}
    </LoginChrome>
  );
}


function PrimaryForm({
  username, setUsername, password, setPassword, error, busy, onSubmit,
}: {
  username: string;
  setUsername: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  error: string | null;
  busy: boolean;
  onSubmit: (e: FormEvent) => void;
}) {
  const navigate = useNavigate();
  return (
    <>
      <Pill tone="accent" dot mono>ALL SYSTEMS OPERATIONAL</Pill>
      <h2 className={chrome.heading}>Sign in</h2>
      <p className={chrome.sub}>Welcome back. Pick up where you left off.</p>

      {error && <Alert tone="error">{error}</Alert>}

      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <Field label="Username">
          <Input
            type="text"
            placeholder="admin@store.com"
            autoFocus required
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={busy}
          />
        </Field>
        <Field
          label={
            <span style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Password</span>
              <Link
                to="/forgot-password"
                style={{ fontSize: "0.78rem", color: "var(--db-neon)", fontWeight: 500, textDecoration: "none" }}
              >
                Forgot?
              </Link>
            </span>
          }
        >
          <Input
            type="password"
            placeholder="••••••••"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
        </Field>
        <Button
          type="submit"
          tone="primary"
          size="lg"
          busy={busy}
          disabled={busy || !username || !password}
          style={{ width: "100%" }}
        >
          {busy ? "Signing in…" : "Sign in →"}
        </Button>
      </form>

      <div className={styles.employeeBox}>
        <div className={styles.employeeTitle}>Employee? Sign in to your store</div>
        <div className={styles.employeeSub}>
          Enter the store code your manager gave you. We'll take you to
          your store's sign-in page.
        </div>
        <form
          className={styles.employeeForm}
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const raw = (form.elements.namedItem("store_code") as HTMLInputElement | null)?.value || "";
            const slug = raw.trim().toLowerCase();
            if (slug) navigate(`/login/${encodeURIComponent(slug)}`);
          }}
        >
          <Input
            type="text"
            name="store_code"
            placeholder="Store code"
            autoComplete="off"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            className={styles.employeeInput}
          />
          <Button type="submit" tone="secondary">Go →</Button>
        </form>
      </div>

      <div className={chrome.centerRow}>
        New to DineroBook? <Link to="/signup">Create an account →</Link>
      </div>

      <div className={chrome.footer}>
        <div className={chrome.footerRow}>
          <span className={chrome.footerItem}>🔒 Bank-grade encryption</span>
          <span className={chrome.footerItem}>99.9% uptime</span>
          <span className={chrome.footerItem}>180-day retention</span>
        </div>
        <div className={chrome.copyright}>
          © 2026 DineroBook · <a href="/privacy">Privacy</a>
        </div>
      </div>
    </>
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
      setError(err instanceof ApiError ? err.message : "Network error. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Pill tone="accent" dot mono>TWO-FACTOR REQUIRED</Pill>
      <h2 className={chrome.heading}>Verify your identity</h2>
      <p className={chrome.sub}>
        {mode === "totp"
          ? "Enter the 6-digit code from your authenticator app."
          : "Enter one of your single-use recovery codes."}
      </p>

      {error && <Alert tone="error">{error}</Alert>}

      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <Field label={mode === "totp" ? "Verification code" : "Recovery code"}>
          <Input
            type="text"
            autoComplete="one-time-code"
            autoFocus required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={busy}
            inputMode={mode === "totp" ? "numeric" : "text"}
            pattern={mode === "totp" ? "[0-9]*" : undefined}
            placeholder={mode === "totp" ? "123456" : "ABCD-1234"}
            style={{
              fontFamily: "var(--db-font-mono)",
              fontSize: "1.15rem",
              letterSpacing: "0.1em",
            }}
          />
        </Field>
        <Button
          type="submit"
          tone="primary"
          size="lg"
          busy={busy}
          disabled={busy || !code}
          style={{ width: "100%" }}
        >
          {busy ? "Verifying…" : "Verify →"}
        </Button>
      </form>

      <div className={chrome.formActions}>
        {mode === "totp" && state.has_recovery_codes && (
          <Button
            tone="ghost"
            onClick={() => { setMode("recovery"); setCode(""); setError(null); }}
          >
            Use a recovery code
          </Button>
        )}
        {mode === "recovery" && (
          <Button
            tone="ghost"
            onClick={() => { setMode("totp"); setCode(""); setError(null); }}
          >
            Back to authenticator code
          </Button>
        )}
        <Button tone="ghost" onClick={onCancel}>Cancel</Button>
      </div>

      <div className={chrome.footer}>
        <div className={chrome.copyright}>
          © 2026 DineroBook · <a href="/privacy">Privacy</a>
        </div>
      </div>
    </>
  );
}


function BrandPane() {
  return (
    <>
      <div className={styles.brandHead}>
        <span className={styles.brandMark} aria-hidden="true">$</span>
        <span className={styles.wordmark}>DineroBook</span>
      </div>

      <div className={styles.midBlock}>
        <Pill tone="accent" dot mono>THE DAILY BOOK · FOR MSBs</Pill>
        <h1 className={styles.hero}>
          Close your day in<br />
          <span className={styles.heroNeon}>fifteen minutes.</span>
        </h1>
        <p className={styles.heroLede}>
          Check cashing, money orders, wire transfers — every dollar that
          moves through your store, logged and reconciled in one place.
        </p>

        <div className={styles.iso}>
          <svg viewBox="0 0 420 240" aria-hidden="true">
            <defs>
              <linearGradient id="paneL" x1="0" x2="1" y1="0" y2="1">
                <stop offset="0" stopColor="#161920" />
                <stop offset="1" stopColor="#0e1117" />
              </linearGradient>
              <filter id="glowL"><feGaussianBlur stdDeviation="2.5" /></filter>
            </defs>
            <g>
              <path d="M 90 30 L 320 0 L 410 30 L 180 60 Z" fill="url(#paneL)" stroke="#272c38" />
              <path d="M 90 30 L 180 60 L 180 100 L 90 70 Z" fill="#0b0d12" stroke="#272c38" />
              <path d="M 410 30 L 180 60 L 180 100 L 410 70 Z" fill="url(#paneL)" stroke="#272c38" />
              <g transform="translate(200,30)">
                <rect x="0" y="0" width="14" height="20" fill="#3fff00" opacity=".45" transform="skewY(18)" />
                <rect x="22" y="-6" width="14" height="26" fill="#3fff00" opacity=".7" transform="skewY(18)" />
                <rect x="44" y="-12" width="14" height="32" fill="#3fff00" transform="skewY(18)" />
                <rect x="66" y="-18" width="14" height="38" fill="#3fff00" transform="skewY(18)" />
                <rect x="88" y="-10" width="14" height="30" fill="#3fff00" opacity=".75" transform="skewY(18)" />
                <rect x="110" y="-22" width="14" height="42" fill="#3fff00" transform="skewY(18)" />
              </g>
            </g>
            <g transform="translate(-30,100)">
              <path d="M 80 50 L 300 20 L 390 50 L 170 80 Z" fill="url(#paneL)" stroke="#3fff00" opacity=".95" />
              <path d="M 80 50 L 170 80 L 170 130 L 80 100 Z" fill="#0b0d12" stroke="#3fff00" />
              <path d="M 390 50 L 170 80 L 170 130 L 390 100 Z" fill="url(#paneL)" stroke="#3fff00" />
              <g transform="translate(185,40)">
                <g transform="skewY(-9)">
                  <text x="0" y="8" fontFamily="JetBrains Mono" fontSize="8" fill="#9199a8">DAILY BOOK · MAR 14</text>
                  <rect x="0" y="14" width="95" height="11" fill="#0b0d12" stroke="#272c38" />
                  <text x="4" y="22" fontFamily="JetBrains Mono" fontSize="8" fill="#e5e7eb">CASH IN $4,200</text>
                  <rect x="100" y="14" width="95" height="11" fill="#0b0d12" stroke="#272c38" />
                  <text x="104" y="22" fontFamily="JetBrains Mono" fontSize="8" fill="#e5e7eb">OUT $3,850</text>
                  <rect x="0" y="29" width="195" height="11" fill="#0b0d12" stroke="#3fff00" />
                  <text x="4" y="37" fontFamily="JetBrains Mono" fontSize="8" fill="#3fff00">NET +$350.00</text>
                </g>
              </g>
            </g>
            <g transform="translate(340,160)" filter="url(#glowL)">
              <rect x="0" y="0" width="44" height="44" rx="10" fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5" />
              <text x="22" y="31" textAnchor="middle" fontFamily="Space Grotesk" fontSize="26" fontWeight="700" fill="#3fff00">$</text>
            </g>
          </svg>
        </div>
      </div>

      <div className={styles.bottomBlock}>
        <div className={styles.quote}>
          "Our monthly close went from three days of spreadsheet chaos to
          one afternoon."
        </div>
        <div className={styles.attrib}>
          <span className={styles.attribAvatar} aria-hidden="true">M</span>
          <div>
            <div className={styles.attribName}>Marcela R.</div>
            <div className={styles.attribRole}>Owner · 3 stores · Miami, FL</div>
          </div>
        </div>
      </div>
    </>
  );
}
