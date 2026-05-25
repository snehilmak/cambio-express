import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button } from "../components/ui";
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
  enroll_required?: boolean;
}

interface LocationState {
  from?: string;
}

interface PendingState {
  pending_token: string;
  has_recovery_codes: boolean;
}

// Login screen for the SPA. Visual chrome lifted from
// templates/login.html (the legacy Jinja version) so the new SPA
// route doesn't regress on look-and-feel: split-screen brand pane on
// the left, form card with status pill + employee escape hatch on
// the right.
//
// Two-step auth flow when the user's role requires 2FA (today:
// superadmin enrolled in TOTP):
//
//   step 1: POST /api/v2/auth/login-cross-store with creds.
//           If `requires_totp=true`, hold pending_token and show
//           the 6-digit code prompt in the right pane.
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
          // Fresh user in a 2FA-required role — drive them through
          // the dedicated enrollment page rather than the inline
          // verify-code form.
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
    <>
      <style>{LOGIN_CSS}</style>
      <div className="login-shell">
        <BrandPane />
        <div className="login-right">
          <div className="login-card">
            {pending ? (
              <SecondFactor
                state={pending}
                onSuccess={finishLogin}
                onCancel={() => {
                  setPending(null);
                  setError(null);
                }}
              />
            ) : (
              <PrimaryForm
                username={username}
                setUsername={setUsername}
                password={password}
                setPassword={setPassword}
                error={error}
                busy={busy}
                onSubmit={onSubmit}
              />
            )}
          </div>
        </div>
      </div>
    </>
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
      <div className="status-pill" aria-hidden="true">
        <span className="dot" />
        <span className="label">ALL SYSTEMS OPERATIONAL</span>
      </div>
      <h2 className="login-heading">Sign in</h2>
      <p className="login-sub">Welcome back. Pick up where you left off.</p>

      {error && <div className="error-msg">{error}</div>}

      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="lf-user">Username</label>
          <input
            id="lf-user"
            type="text"
            placeholder="admin@store.com"
            autoFocus
            required
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={busy}
          />
        </div>
        <div className="field">
          <div className="label-row">
            <label htmlFor="lf-pass" style={{ marginBottom: 0 }}>Password</label>
            <Link className="forgot-link" to="/forgot-password">Forgot?</Link>
          </div>
          <input
            id="lf-pass"
            type="password"
            placeholder="••••••••"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
        </div>
        <button
          type="submit"
          className={`btn-login${busy ? " is-busy" : ""}`}
          disabled={busy || !username || !password}
        >
          {busy ? "Signing in…" : "Sign in →"}
        </button>
      </form>

      <div className="employee-box">
        <div className="employee-box-title">Employee? Sign in to your store</div>
        <div className="employee-box-sub">
          Enter the store code your manager gave you. We'll take you to
          your store's sign-in page.
        </div>
        {/* Was posting to /employee-login (legacy Flask handler
            removed in PR #550); now navigates client-side to
            /login/{slug} which `LoginStore` handles. */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const raw = (form.elements.namedItem("store_code") as HTMLInputElement | null)?.value || "";
            const slug = raw.trim().toLowerCase();
            if (slug) navigate(`/login/${encodeURIComponent(slug)}`);
          }}
        >
          <input
            type="text"
            name="store_code"
            placeholder="Store code"
            autoComplete="off"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
          />
          <button type="submit">Go →</button>
        </form>
      </div>

      <div className="switcher">
        <span>New to DineroBook?</span>
        <Link to="/signup">Create an account →</Link>
      </div>

      <div className="login-footer">
        <div className="login-footer-row">
          <span className="login-footer-item">🔒 Bank-grade encryption</span>
          <span className="login-footer-item">99.9% uptime</span>
          <span className="login-footer-item">180-day retention</span>
        </div>
        <div className="copyright">
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
    <>
      <div className="status-pill" aria-hidden="true">
        <span className="dot" />
        <span className="label">TWO-FACTOR REQUIRED</span>
      </div>
      <h2 className="login-heading">Verify your identity</h2>
      <p className="login-sub">
        {mode === "totp"
          ? "Enter the 6-digit code from your authenticator app."
          : "Enter one of your single-use recovery codes."}
      </p>

      {error && <div className="error-msg">{error}</div>}

      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="lf-code">
            {mode === "totp" ? "Verification code" : "Recovery code"}
          </label>
          <input
            id="lf-code"
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
              fontFamily: "var(--db-font-mono)",
              fontSize: "1.15rem",
              letterSpacing: "0.1em",
            }}
          />
        </div>
        <button
          type="submit"
          className={`btn-login${busy ? " is-busy" : ""}`}
          disabled={busy || !code}
        >
          {busy ? "Verifying…" : "Verify →"}
        </button>
      </form>

      <div className="totp-actions">
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
        <Button tone="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>

      <div className="login-footer">
        <div className="copyright">
          © 2026 DineroBook · <a href="/privacy">Privacy</a>
        </div>
      </div>
    </>
  );
}


function BrandPane() {
  return (
    <div className="login-left">
      <div className="bg-grid" aria-hidden="true" />
      <div className="bg-glow" aria-hidden="true" />

      <div className="brand-row">
        <span className="mark" aria-hidden="true">$</span>
        <span className="wordmark">DineroBook</span>
      </div>

      <div className="login-left-mid">
        <div className="eyebrow-pill">
          <span className="dot" />THE DAILY BOOK · FOR MSBs
        </div>
        <h1>Close your day in<br /><span className="neon">fifteen minutes.</span></h1>
        <p className="p">
          Check cashing, money orders, wire transfers — every dollar that
          moves through your store, logged and reconciled in one place.
        </p>

        <div className="iso-wrap">
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

      <div className="login-left-bottom">
        <div className="quote">
          "Our monthly close went from three days of spreadsheet chaos to
          one afternoon."
        </div>
        <div className="attrib">
          <span className="av" aria-hidden="true">M</span>
          <div>
            <div className="nm">Marcela R.</div>
            <div className="rl">Owner · 3 stores · Miami, FL</div>
          </div>
        </div>
      </div>
    </div>
  );
}


// Page-local CSS lifted verbatim from templates/login.html so the
// visual diff against the legacy login page stays at zero. Tokens
// (`--db-*`) come from the global static/design-tokens.css.
const LOGIN_CSS = `
.login-shell{display:flex;min-height:100vh;min-height:100dvh;background:var(--db-bg);color:var(--db-gray-9);font-family:var(--db-font-body);overscroll-behavior-y:none;-webkit-font-smoothing:antialiased}
.login-shell *,.login-shell *::before,.login-shell *::after{box-sizing:border-box;margin:0;padding:0}
.login-shell ::selection{background:var(--db-neon);color:var(--db-neon-ink)}

.login-left{width:50%;min-width:480px;background:var(--db-bg);border-right:1px solid var(--db-gray-2);padding:40px 56px;display:flex;flex-direction:column;position:relative;overflow:hidden}
.login-left .bg-grid{position:absolute;inset:0;background-image:linear-gradient(var(--db-gray-2) 1px,transparent 1px),linear-gradient(90deg,var(--db-gray-2) 1px,transparent 1px);background-size:48px 48px;-webkit-mask-image:radial-gradient(ellipse at 60% 40%,black 20%,transparent 70%);mask-image:radial-gradient(ellipse at 60% 40%,black 20%,transparent 70%);opacity:.5;pointer-events:none}
.login-left .bg-glow{position:absolute;top:30%;right:-10%;width:420px;height:420px;background:radial-gradient(circle,var(--db-neon-glow-25),transparent 60%);pointer-events:none}
.brand-row{display:flex;align-items:center;gap:12px;position:relative;z-index:1}
.brand-row .mark{width:36px;height:36px;border-radius:10px;background:var(--db-brand);color:var(--db-brand-ink);display:inline-flex;align-items:center;justify-content:center;font-family:var(--db-font-display);font-weight:700;font-size:22px;box-shadow:0 0 24px var(--db-neon-glow-40)}
.brand-row .wordmark{font-family:var(--db-font-display);font-weight:600;font-size:20px;letter-spacing:-.02em;color:var(--db-gray-9)}
.login-left-mid{flex:1;display:flex;flex-direction:column;justify-content:center;position:relative;z-index:1;max-width:480px}
.login-left .eyebrow-pill{display:inline-flex;align-items:center;gap:10px;padding:5px 12px;border:1px solid rgba(63,255,0,.3);border-radius:999px;background:var(--db-neon-glow-8);font-family:var(--db-font-mono);font-size:11px;color:var(--db-neon);letter-spacing:2px;text-transform:uppercase;align-self:flex-start;margin-bottom:24px;font-weight:500}
.login-left .eyebrow-pill .dot{width:6px;height:6px;border-radius:999px;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon)}
.login-left h1{font-family:var(--db-font-display);font-size:44px;line-height:1.05;font-weight:700;letter-spacing:-.035em;margin-bottom:16px;color:var(--db-gray-9)}
.login-left h1 .neon{color:var(--db-neon)}
.login-left .p{font-size:15px;color:var(--db-gray-7);line-height:1.6;margin-bottom:32px}
.iso-wrap{max-width:420px}
.iso-wrap svg{width:100%;height:auto}
.login-left-bottom{position:relative;z-index:1;padding-top:24px;border-top:1px solid var(--db-gray-2)}
.quote{font-size:14px;color:var(--db-gray-8);line-height:1.55;margin-bottom:14px;max-width:440px}
.attrib{display:flex;align-items:center;gap:10px}
.attrib .av{width:32px;height:32px;border-radius:999px;background:linear-gradient(135deg,var(--db-neon) 0%,var(--db-neon-dim) 100%);color:var(--db-neon-ink);display:inline-flex;align-items:center;justify-content:center;font-family:var(--db-font-display);font-weight:700;font-size:13px}
.attrib .nm{font-size:12.5px;color:var(--db-gray-9);font-weight:600}
.attrib .rl{font-size:11px;color:var(--db-gray-7);margin-top:1px}

.login-right{flex:1;background:var(--db-bg);display:flex;flex-direction:column;justify-content:center;align-items:center;padding:40px 32px}
.login-card{width:100%;max-width:400px}
.status-pill{display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border:1px solid var(--db-gray-2);border-radius:999px;background:var(--db-bg-elevated);margin-bottom:28px}
.status-pill .dot{width:6px;height:6px;border-radius:999px;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon)}
.status-pill .label{font-family:var(--db-font-mono);font-size:10px;color:var(--db-gray-7);letter-spacing:1.2px}
.login-heading{font-family:var(--db-font-display);font-size:36px;font-weight:600;letter-spacing:-.03em;color:var(--db-gray-9);margin-bottom:8px}
.login-sub{font-size:14px;color:var(--db-gray-7);margin-bottom:32px}
.login-card .field{margin-bottom:18px}
.login-card .label-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.login-card label{display:block;font-family:var(--db-font-mono);font-size:10.5px;font-weight:500;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px}
.login-card input[type="text"],.login-card input[type="password"],.login-card input[type="email"],.login-card input[type="tel"]{width:100%;padding:13px 14px;background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:10px;font-size:14px;color:var(--db-gray-9);font-family:var(--db-font-body);outline:none;transition:border-color .15s,box-shadow .15s}
.login-card input:focus{border-color:var(--db-neon);box-shadow:0 0 0 3px var(--db-neon-glow-15)}
.login-card input::placeholder{color:var(--db-gray-5)}
.login-card .forgot-link{font-size:12px;color:var(--db-neon);text-decoration:none;font-family:var(--db-font-body)}
.login-card .forgot-link:hover{color:var(--db-neon-bright)}
.error-msg{background:rgba(255,77,109,.08);color:var(--db-negative);border:1px solid rgba(255,77,109,.3);border-radius:10px;padding:11px 14px;font-size:13px;margin-bottom:18px;font-family:var(--db-font-body)}
.btn-login{width:100%;padding:14px;background:var(--db-neon);color:var(--db-neon-ink);border:none;border-radius:10px;font-size:14.5px;font-weight:600;cursor:pointer;font-family:var(--db-font-body);letter-spacing:-.01em;box-shadow:0 0 0 1px var(--db-neon),0 0 28px var(--db-neon-glow-40);transition:background .12s;margin-top:6px}
.btn-login:hover:not(:disabled){background:var(--db-neon-bright)}
.btn-login:disabled{opacity:.6;cursor:not-allowed}
.btn-login.is-busy:disabled{cursor:wait}

.employee-box{margin-top:28px;padding:16px 18px;background:var(--db-bg-elevated);border:1px solid var(--db-gray-3);border-radius:12px}
.employee-box-title{font-size:13px;font-weight:600;color:var(--db-gray-9);margin-bottom:4px}
.employee-box-sub{font-size:12px;color:var(--db-gray-7);margin-bottom:10px;line-height:1.45}
.employee-box form{display:flex;gap:8px}
.employee-box input{flex:1;padding:10px 12px;font-size:14px;border:1px solid var(--db-gray-3);border-radius:8px;background:var(--db-bg-input);color:var(--db-gray-9);font-family:var(--db-font-body)}
.employee-box button{padding:10px 16px;background:transparent;color:var(--db-gray-9);border:1px solid var(--db-gray-4);border-radius:8px;font-size:14px;font-weight:600;font-family:var(--db-font-body);cursor:pointer}
.employee-box button:hover{border-color:var(--db-neon);color:var(--db-neon)}

.switcher{text-align:center;font-size:13.5px;margin-top:28px;display:flex;justify-content:center;gap:6px;flex-wrap:wrap;color:var(--db-gray-7)}
.switcher a{color:var(--db-neon);text-decoration:none;font-weight:500}

.login-footer{margin-top:40px;text-align:center}
.login-footer-row{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin-bottom:10px}
.login-footer-item{font-size:11.5px;color:var(--db-gray-6)}
.copyright{font-size:11px;color:var(--db-gray-5)}
.copyright a{color:var(--db-gray-6);text-decoration:none}

.totp-actions{margin-top:20px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
/* .link-btn retired — TOTP recovery / cancel / back actions
   now use the kit <Button tone="ghost"> primitive, which has the
   same transparent + underlined + hover-to-neon treatment. */

@media (max-width: 900px){
  .login-shell{flex-direction:column}
  .login-left{width:100%;min-width:0;padding:28px 24px 24px;padding-top:max(28px,env(safe-area-inset-top));flex:none}
  .login-left h1{font-size:32px}
  .login-left .p{font-size:14px;margin-bottom:20px}
  .iso-wrap{max-width:360px;margin:0 auto 8px}
  .login-left-bottom{padding-top:18px;margin-top:8px}
  .quote{font-size:13px}
  .login-right{width:100%;padding:28px 24px;padding-bottom:max(28px,env(safe-area-inset-bottom));flex:0 0 auto}
  .login-heading{font-size:26px}
  .login-sub{margin-bottom:22px}
  .login-card .field{margin-bottom:14px}
  .login-card input[type="text"],.login-card input[type="password"],.login-card input[type="email"],.login-card input[type="tel"],.employee-box input{font-size:16px}
}
@media (max-width: 480px){
  .login-left{padding:22px 20px 16px}
  .brand-row .mark{width:30px;height:30px;font-size:18px}
  .brand-row .wordmark{font-size:17px}
  .login-left h1{font-size:28px}
  .iso-wrap{display:none}
  .login-right{padding:22px 20px 24px}
  .login-heading{font-size:22px}
}
`;
