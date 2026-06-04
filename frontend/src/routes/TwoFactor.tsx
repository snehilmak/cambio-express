import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { LoginChrome } from "../components/LoginChrome";
import chrome from "../components/LoginChrome.module.css";
import { Alert, Button, Checkbox, Field, Input } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";
import {
  totpEnrollConfirm, totpEnrollFinish, totpEnrollStart,
  type TotpEnrollStartResponse,
} from "../api/account";
import styles from "./TwoFactor.module.css";

interface PendingState {
  pending_token: string;
  has_recovery_codes?: boolean;
}

function readPending(loc: ReturnType<typeof useLocation>): PendingState | null {
  // Tokens are passed via React Router state (not URL) so they
  // never appear in browser history or referer headers.
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
          <div className={chrome.centerRow}>
            Lost your device?{" "}
            <Link to="/login/2fa/recover" state={pending}>
              Use a recovery code
            </Link>
          </div>
        )}
        <div className={chrome.centerRow}>
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
        <div className={chrome.centerRow}>
          Got your authenticator back?{" "}
          <Link to="/login/2fa" state={pending}>
            Enter a 6-digit code instead
          </Link>
        </div>
        <div className={chrome.centerRow}>
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
        navigate("/dashboard", { replace: true });
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
        <h2 className={chrome.heading}>Save these recovery codes</h2>
        <p className={chrome.sub}>
          If you lose access to your authenticator app, each of these codes
          can be used once to sign in instead of a 6-digit code. This is
          the only time they'll be shown.
        </p>
        <Alert tone="info">
          <strong>Where to store them:</strong> password manager (1Password,
          Bitwarden), a printed copy in a safe, or both. Don't save them in
          a plain note on your phone — if your phone is the device you've
          just enrolled, losing it loses everything.
        </Alert>
        <div className={styles.recoveryGrid}>
          {recoveryCodes.map((c) => (<div key={c}>{c}</div>))}
        </div>
        {error && <Alert tone="error">{error}</Alert>}
        <form onSubmit={onConfirmSaved} autoComplete="off"
              style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <Checkbox checked={savedConfirmed} onChange={setSavedConfirmed}>
            I've saved these recovery codes somewhere safe.
          </Checkbox>
          <Button
            type="submit" tone="primary" size="lg"
            busy={busy}
            disabled={!savedConfirmed || busy}
            style={{ width: "100%" }}
          >
            {busy ? "Finishing…" : "Finish and sign in →"}
          </Button>
        </form>
      </Chrome>
    );
  }

  return (
    <Chrome title="Set up 2FA">
      <h2 className={chrome.heading}>Set up two-factor authentication</h2>
      <p className={chrome.sub}>
        Scan this QR code with Google Authenticator, 1Password, Authy, or
        any TOTP app — then enter the 6-digit code it generates to confirm.
      </p>
      {error && <Alert tone="error">{error}</Alert>}
      {!enrollment ? (
        <Alert tone="info">Loading enrollment details…</Alert>
      ) : (
        <>
          <div
            className={styles.qrWrap}
            dangerouslySetInnerHTML={{ __html: enrollment.qr_svg }}
          />
          <Alert tone="info">
            <strong>Can't scan?</strong> Enter this secret manually in your
            authenticator app (issuer: <code>{enrollment.issuer}</code>,
            account: <code>{enrollment.username}</code>):
          </Alert>
          <div className={styles.secretBlock}>{enrollment.secret_chunks}</div>
          <form onSubmit={onVerifyCode} autoComplete="off"
                style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            <Field label="Enter the 6-digit code from your app">
              <Input
                type="text" inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9 ]*" maxLength={7}
                placeholder="123 456" autoFocus required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={busy}
                style={{
                  fontFamily: "var(--db-font-mono)",
                  fontSize: 20,
                  letterSpacing: 6,
                  textAlign: "center",
                }}
              />
            </Field>
            <Button
              type="submit" tone="primary" size="lg"
              busy={busy}
              disabled={busy || !code}
              style={{ width: "100%" }}
            >
              {busy ? "Verifying…" : "Confirm and continue →"}
            </Button>
          </form>
        </>
      )}
      <div className={chrome.centerRow}>
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
  children?: ReactNode;
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
        navigate("/dashboard", { replace: true });
      } else {
        setError("Server returned an unexpected response.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Network error. Try again.");
    } finally { setBusy(false); }
  }

  return (
    <>
      <h2 className={chrome.heading}>{heading}</h2>
      <p className={chrome.sub}>{sub}</p>
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={onSubmit} autoComplete="off"
            style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <Field label={codeLabel}>
          <Input
            type="text" inputMode={codeMode}
            autoComplete="one-time-code"
            pattern={codePattern}
            maxLength={codeMaxLen}
            placeholder={codePlaceholder} autoFocus required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            disabled={busy}
            style={{
              fontFamily: "var(--db-font-mono)",
              fontSize: codeMode === "numeric" ? 20 : 18,
              letterSpacing: codeMode === "numeric" ? 6 : 2,
              textAlign: "center",
              textTransform: uppercase ? "uppercase" : undefined,
            }}
          />
        </Field>
        <Button
          type="submit" tone="primary" size="lg"
          busy={busy}
          disabled={busy || !code}
          style={{ width: "100%" }}
        >
          {busy ? "Verifying…" : submitLabel}
        </Button>
      </form>
      {children}
    </>
  );
}


function Chrome({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <LoginChrome variant="fixed" brandCentered brandPane={<BrandPane />}>
        {children}
      </LoginChrome>
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
    <div className={styles.brandBlock}>
      <img src="/static/brand-mark.svg" className={styles.brandMark} alt="" />
      <div className={styles.brandName}>DineroBook</div>
      <div className={styles.brandTagline}>TWO-FACTOR AUTHENTICATION</div>
    </div>
  );
}
