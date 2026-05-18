import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";
import {
  totpEnrollConfirm, totpEnrollFinish, totpEnrollStart,
  type TotpEnrollStartResponse,
} from "../api/account";

// Visual chrome lifted 1:1 from templates/_login_chrome.html so the
// SPA versions of the 2FA pages look identical to the legacy Jinja
// pages they replace. Three top-level components (verify / enroll /
// recover) share the same chrome and CSS.

interface PendingState {
  pending_token: string;
  has_recovery_codes?: boolean;
}

function readPending(loc: ReturnType<typeof useLocation>): PendingState | null {
  // Pending tokens are passed via React Router state (not URL —
  // tokens shouldn't appear in browser history or referer headers).
  const s = (loc.state ?? null) as PendingState | null;
  if (s && typeof s.pending_token === "string" && s.pending_token) return s;
  return null;
}


export function TwoFactorVerify() {
  const navigate = useNavigate();
  const loc = useLocation();
  const pending = readPending(loc);
  useEffect(() => {
    if (!pending) navigate("/login", { replace: true });
  }, [pending, navigate]);
  if (!pending) return null;
  return (
    <Chrome title="Enter 6-digit code">
      <VerifyForm
        endpoint="/api/v2/auth/login/totp"
        heading="Enter your code"
        sub="Open your authenticator app and type the 6-digit code it shows for DineroBook."
        codeLabel="Authentication code"
        codeMode="numeric"
        codePlaceholder="123 456"
        codeMaxLen={7}
        codePattern="[0-9 ]*"
        submitLabel="Verify →"
        pending={pending}
      >
        {pending.has_recovery_codes && (
          <div className="aux-link">
            Lost your device?{" "}
            <Link to="/login/2fa/recover" state={pending}>
              Use a recovery code
            </Link>
          </div>
        )}
        <div className="aux-link">
          <Link to="/login">Cancel and sign back in</Link>
        </div>
      </VerifyForm>
    </Chrome>
  );
}


export function TwoFactorRecover() {
  const navigate = useNavigate();
  const loc = useLocation();
  const pending = readPending(loc);
  useEffect(() => {
    if (!pending) navigate("/login", { replace: true });
  }, [pending, navigate]);
  if (!pending) return null;
  return (
    <Chrome title="Use a recovery code">
      <VerifyForm
        endpoint="/api/v2/auth/login/recovery"
        heading="Use a recovery code"
        sub="Enter one of the 8-character recovery codes you saved when setting up 2FA. Each code works only once."
        codeLabel="Recovery code"
        codeMode="text"
        codePlaceholder="ABCD-EFGH"
        codeMaxLen={16}
        submitLabel="Use code →"
        pending={pending}
        uppercase
      >
        <div className="aux-link">
          Got your authenticator back?{" "}
          <Link to="/login/2fa" state={pending}>
            Enter a 6-digit code instead
          </Link>
        </div>
        <div className="aux-link">
          <Link to="/login">Cancel and sign back in</Link>
        </div>
      </VerifyForm>
    </Chrome>
  );
}


type EnrollStep = "scan" | "saved";


export function TwoFactorEnroll() {
  const navigate = useNavigate();
  const loc = useLocation();
  const pending = readPending(loc);
  const [enrollment, setEnrollment] = useState<TotpEnrollStartResponse | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [step, setStep] = useState<EnrollStep>("scan");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [savedConfirmed, setSavedConfirmed] = useState(false);

  useEffect(() => {
    if (!pending) {
      navigate("/login", { replace: true });
      return;
    }
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mark busy before kicking off the async TOTP-enrollment fetch; cancellation flag guards stale resolutions
    setBusy(true);
    totpEnrollStart(pending.pending_token)
      .then((data) => { if (!cancelled) setEnrollment(data); })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError
            ? err.message
            : "Couldn't start enrollment. Sign in again.",
        );
      })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [pending, navigate]);

  if (!pending) return null;

  async function onVerifyCode(e: FormEvent) {
    e.preventDefault();
    if (!pending) return;
    setError(null); setBusy(true);
    try {
      const r = await totpEnrollFinish(pending.pending_token, code.trim());
      setRecoveryCodes(r.recovery_codes);
      setStep("saved");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "That code didn't match. Try the next one your app shows.",
      );
    } finally { setBusy(false); }
  }

  async function onConfirmSaved(e: FormEvent) {
    e.preventDefault();
    if (!pending || !savedConfirmed) return;
    setError(null); setBusy(true);
    try {
      const r = await totpEnrollConfirm(pending.pending_token);
      if ("access_token" in r && typeof r.access_token === "string") {
        setAccessToken(r.access_token);
        navigate("/home", { replace: true });
      } else {
        setError("Server returned an unexpected response.");
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't finalize sign-in. Try again.",
      );
    } finally { setBusy(false); }
  }

  if (step === "saved" && recoveryCodes) {
    return (
      <Chrome title="Save your recovery codes">
        <div className="login-heading">Save these recovery codes</div>
        <div className="login-sub">
          If you lose access to your authenticator app, each of these codes
          can be used once to sign in instead of a 6-digit code. This is
          the only time they'll be shown.
        </div>
        <div className="info-box">
          <strong>Where to store them:</strong> password manager (1Password,
          Bitwarden), a printed copy in a safe, or both. Don't save them in
          a plain note on your phone — if your phone is the device you've
          just enrolled, losing it loses everything.
        </div>
        <div className="recovery-grid">
          {recoveryCodes.map((c) => (<div key={c}>{c}</div>))}
        </div>
        {error && <div className="error-msg">{error}</div>}
        <form onSubmit={onConfirmSaved} autoComplete="off">
          <div className="checkbox-row">
            <input
              id="confirm" type="checkbox"
              checked={savedConfirmed}
              onChange={(e) => setSavedConfirmed(e.target.checked)}
              required
            />
            <label htmlFor="confirm" style={{
              fontSize: 14, fontWeight: 500,
              textTransform: "none", letterSpacing: "normal",
            }}>
              I've saved these recovery codes somewhere safe.
            </label>
          </div>
          <button
            type="submit" className={`btn-login${busy ? " is-busy" : ""}`}
            disabled={!savedConfirmed || busy}
          >
            {busy ? "Finishing…" : "Finish and sign in →"}
          </button>
        </form>
      </Chrome>
    );
  }

  return (
    <Chrome title="Set up 2FA">
      <div className="login-heading">Set up two-factor authentication</div>
      <div className="login-sub">
        Scan this QR code with Google Authenticator, 1Password, Authy, or
        any TOTP app — then enter the 6-digit code it generates to confirm.
      </div>
      {error && <div className="error-msg">{error}</div>}
      {!enrollment ? (
        <div className="info-box">Loading enrollment details…</div>
      ) : (
        <>
          <div
            className="qr-wrap"
            dangerouslySetInnerHTML={{ __html: enrollment.qr_svg }}
          />
          <div className="info-box">
            <strong>Can't scan?</strong> Enter this secret manually in your
            authenticator app (issuer: <code>{enrollment.issuer}</code>,
            account: <code>{enrollment.username}</code>):
          </div>
          <div className="secret-block">{enrollment.secret_chunks}</div>
          <form onSubmit={onVerifyCode} autoComplete="off"
                style={{ marginTop: 22 }}>
            <div className="field">
              <label htmlFor="enroll-code">
                Enter the 6-digit code from your app
              </label>
              <input
                id="enroll-code"
                type="text" inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9 ]*" maxLength={7}
                placeholder="123 456" autoFocus required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={busy}
                style={{
                  fontFamily: "ui-monospace,monospace",
                  fontSize: 20, letterSpacing: 6,
                  textAlign: "center",
                }}
              />
            </div>
            <button
              type="submit" className={`btn-login${busy ? " is-busy" : ""}`}
              disabled={busy || !code}
            >
              {busy ? "Verifying…" : "Confirm and continue →"}
            </button>
          </form>
        </>
      )}
      <div className="aux-link">
        <Link to="/login">Cancel and sign back in</Link>
      </div>
    </Chrome>
  );
}


function VerifyForm({
  endpoint, heading, sub, codeLabel, codeMode, codePlaceholder,
  codeMaxLen, codePattern, submitLabel, pending, uppercase, children,
}: {
  endpoint: string;
  heading: string;
  sub: string;
  codeLabel: string;
  codeMode: "numeric" | "text";
  codePlaceholder: string;
  codeMaxLen: number;
  codePattern?: string;
  submitLabel: string;
  pending: PendingState;
  uppercase?: boolean;
  children?: React.ReactNode;
}) {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      const r = await api<{ access_token: string }>(endpoint, {
        method: "POST",
        json: { pending_token: pending.pending_token, code: code.trim() },
      });
      if (r.access_token) {
        setAccessToken(r.access_token);
        navigate("/home", { replace: true });
      } else {
        setError("Server returned an unexpected response.");
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Network error. Try again.",
      );
    } finally { setBusy(false); }
  }

  return (
    <>
      <div className="login-heading">{heading}</div>
      <div className="login-sub">{sub}</div>
      {error && <div className="error-msg">{error}</div>}
      <form onSubmit={onSubmit} autoComplete="off">
        <div className="field">
          <label htmlFor="tf-code">{codeLabel}</label>
          <input
            id="tf-code"
            type="text" inputMode={codeMode}
            autoComplete="one-time-code"
            pattern={codePattern}
            maxLength={codeMaxLen}
            placeholder={codePlaceholder} autoFocus required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={busy}
            style={{
              fontFamily: "ui-monospace,monospace",
              fontSize: codeMode === "numeric" ? 20 : 18,
              letterSpacing: codeMode === "numeric" ? 6 : 2,
              textAlign: "center",
              textTransform: uppercase ? "uppercase" : undefined,
            }}
          />
        </div>
        <button
          type="submit" className={`btn-login${busy ? " is-busy" : ""}`}
          disabled={busy || !code}
        >
          {busy ? "Verifying…" : submitLabel}
        </button>
      </form>
      {children}
    </>
  );
}


function Chrome({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <style>{TWO_FACTOR_CSS}</style>
      <div className="tf-shell">
        <BrandPane />
        <div className="login-right">
          <div className="login-card">
            {children}
          </div>
        </div>
      </div>
      {/* Update document title for parity with the legacy template's <title> */}
      <DocTitle title={`${title} — DineroBook`} />
    </>
  );
}


function DocTitle({ title }: { title: string }) {
  useEffect(() => {
    const prev = document.title;
    document.title = title;
    return () => { document.title = prev; };
  }, [title]);
  return null;
}


function BrandPane() {
  return (
    <div className="login-left">
      <div className="bg-grid" aria-hidden="true" />
      <div className="bg-glow" aria-hidden="true" />
      <div className="brand-block">
        <img src="/static/brand-mark.svg" className="brand-mark" alt="" />
        <div className="brand-name">DineroBook</div>
        <div className="brand-tagline">TWO-FACTOR AUTHENTICATION</div>
      </div>
    </div>
  );
}


// Styles transcribed from templates/_login_chrome.html so the SPA
// surfaces match the legacy chrome 1:1. Tokens (--db-*) come from
// design-tokens.css which the SPA shell already loads.
const TWO_FACTOR_CSS = `
.tf-shell { display: flex; min-height: 100vh; min-height: 100dvh; }
.login-left {
  flex: 1; min-width: 360px;
  background: var(--db-bg);
  border-right: 1px solid var(--db-gray-2);
  padding: 40px 48px;
  display: flex; align-items: center; justify-content: center;
  position: relative; overflow: hidden;
}
.login-left .bg-grid {
  position: absolute; inset: 0;
  background-image: linear-gradient(var(--db-gray-2) 1px, transparent 1px),
                    linear-gradient(90deg, var(--db-gray-2) 1px, transparent 1px);
  background-size: 48px 48px;
  -webkit-mask-image: radial-gradient(ellipse at center, black 20%, transparent 70%);
  mask-image: radial-gradient(ellipse at center, black 20%, transparent 70%);
  opacity: 0.5; pointer-events: none;
}
.login-left .bg-glow {
  position: absolute; top: 30%; right: -10%;
  width: 420px; height: 420px;
  background: radial-gradient(circle, var(--db-neon-glow-25), transparent 60%);
  pointer-events: none;
}
.brand-block { text-align: center; position: relative; z-index: 1; }
.brand-mark {
  width: 52px; height: 52px; border-radius: 12px;
  box-shadow: 0 0 24px rgba(63,255,0,0.40);
  margin-bottom: 18px; display: block; margin-left: auto; margin-right: auto;
}
.brand-name {
  font-family: var(--db-font-display);
  font-size: 30px; font-weight: 600;
  color: var(--db-gray-9);
  letter-spacing: -0.02em; line-height: 1;
}
.brand-tagline {
  font-family: var(--db-font-mono);
  font-size: 11px; color: var(--db-gray-7);
  margin-top: 12px; letter-spacing: 1.5px; text-transform: uppercase;
}

.login-right {
  width: 520px; background: var(--db-bg);
  display: flex; flex-direction: column; justify-content: center;
  padding: 48px;
  overflow-y: auto; max-height: 100vh; max-height: 100dvh;
}
.login-card {
  display: flex; flex-direction: column;
}
.login-heading {
  font-family: var(--db-font-display);
  font-size: 30px; font-weight: 600;
  color: var(--db-gray-9);
  letter-spacing: -0.025em;
  margin-bottom: 6px;
}
.login-sub {
  font-size: 14px; color: var(--db-gray-7);
  margin-bottom: 28px; line-height: 1.55;
}
.field { display: flex; flex-direction: column; gap: 7px; margin-bottom: 16px; }
.field label {
  font-size: 11.5px; font-weight: 600; letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--db-gray-6);
}
.field input {
  background: var(--db-bg-input); color: var(--db-gray-9);
  border: 1px solid var(--db-gray-3); border-radius: 10px;
  padding: 13px 14px; font-size: 14.5px;
  font-family: var(--db-font-body);
  transition: border-color 0.12s, box-shadow 0.12s;
}
.field input:focus {
  outline: none; border-color: var(--db-neon);
  box-shadow: 0 0 0 3px rgba(63,255,0,0.15);
}

.error-msg {
  background: rgba(255,77,109,0.08); color: var(--db-negative);
  border: 1px solid rgba(255,77,109,0.3);
  border-radius: 10px; padding: 11px 14px;
  font-size: 13px; margin-bottom: 16px;
}
.info-box {
  background: rgba(94,169,255,0.08); color: var(--db-info);
  border: 1px solid rgba(94,169,255,0.3);
  border-radius: 10px; padding: 11px 14px;
  font-size: 13px; margin-bottom: 16px; line-height: 1.5;
}

.btn-login {
  width: 100%; padding: 14px;
  background: var(--db-neon); color: var(--db-neon-ink);
  border: none; border-radius: 10px;
  font-size: 14.5px; font-weight: 600;
  font-family: var(--db-font-body); letter-spacing: -0.01em;
  cursor: pointer; margin-top: 6px;
  box-shadow: 0 0 0 1px var(--db-neon), 0 0 28px var(--db-neon-glow-40);
  transition: background 0.12s;
}
.btn-login:hover:not(:disabled) { background: var(--db-neon-bright); }
.btn-login:disabled { opacity: 0.55; cursor: not-allowed; }

.aux-link {
  margin-top: 18px; font-size: 13px; text-align: center;
  color: var(--db-gray-7);
}
.aux-link a { color: var(--db-neon); text-decoration: none; font-weight: 500; }
.aux-link a:hover { color: var(--db-neon-bright); }

.qr-wrap {
  display: flex; justify-content: center;
  margin: 6px 0 18px;
  padding: 16px; background: var(--db-gray-10);
  border: 1px solid var(--db-gray-3); border-radius: 12px;
}
.qr-wrap svg { width: 220px; height: 220px; display: block; }
.secret-block {
  font-family: var(--db-font-mono);
  font-size: 16px; letter-spacing: 1px;
  background: var(--db-bg-input); border: 1px solid var(--db-gray-3);
  border-radius: 8px; padding: 12px 14px;
  color: var(--db-gray-9); word-break: break-all; text-align: center;
}
.recovery-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px;
  font-family: var(--db-font-mono);
  font-size: 15px; letter-spacing: 1px;
  background: rgba(255,176,32,0.08);
  border: 1px solid rgba(255,176,32,0.3);
  color: var(--db-warning);
  border-radius: 10px; padding: 16px; margin: 6px 0 16px;
}
.checkbox-row {
  display: flex; align-items: flex-start; gap: 10px;
  margin: 14px 0 18px; font-size: 14px; color: var(--db-gray-8);
}
.checkbox-row input[type=checkbox] {
  width: 16px; height: 16px; margin-top: 3px; flex-shrink: 0;
  accent-color: var(--db-neon);
}

@media (max-width: 900px) {
  .tf-shell { flex-direction: column; }
  .login-left {
    flex: none; min-width: 0;
    padding: 24px 24px 20px;
    border-right: none;
    border-bottom: 1px solid var(--db-gray-2);
  }
  .login-left .bg-grid, .login-left .bg-glow { display: none; }
  .brand-mark { width: 40px; height: 40px; margin-bottom: 10px; }
  .brand-name { font-size: 22px; }
  .brand-tagline { font-size: 10px; }
  .login-right {
    width: 100%; padding: 24px 24px 32px;
  }
  .qr-wrap svg { width: 180px; height: 180px; }
  .recovery-grid { grid-template-columns: 1fr; }
}
`;
