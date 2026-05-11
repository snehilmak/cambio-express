import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { previewReferral, signup, type ReferralPreview } from "../api/account";
import { ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";

// Self-service signup at /app/signup. Visual chrome lifted from
// templates/signup.html (the legacy Jinja version) so the new SPA
// route doesn't regress on look-and-feel.
//
// Form contract mirrors the legacy /signup POST: store name +
// email + password + optional phone + optional referral code.
// On success the server returns a JWT scoped to the new store
// and we drop the user straight on /dashboard.
//
// Referral code: lifted via `?ref=CODE` on first paint, looked up
// against /api/v2/auth/referral/<code> so the green banner can
// render with the actual `$X off` figure. An unknown code is
// silently dropped — same behaviour as the legacy form.
export default function Signup() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const refFromUrl = (params.get("ref") || "").toUpperCase();

  const [storeName, setStoreName] = useState("");
  const [email,     setEmail]     = useState("");
  const [phone,     setPhone]     = useState("");
  const [password,  setPassword]  = useState("");
  const [refCode,   setRefCode]   = useState(refFromUrl);
  const [busy,      setBusy]      = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [errors,    setErrors]    = useState<Record<string, string>>({});
  const [referral,  setReferral]  = useState<ReferralPreview | null>(null);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  // Resolve the referral preview whenever the typed/URL code
  // changes. Debounce to avoid hammering the API on every keystroke.
  useEffect(() => {
    const code = refCode.trim().toUpperCase();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- debounced referral-code preview: clear local referral state when the input empties (the .then callback below sets it for non-empty codes)
    if (!code) { setReferral(null); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      previewReferral(code).then(
        (r) => { if (!cancelled) setReferral(r); },
        () => { if (!cancelled) setReferral(null); },
      );
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [refCode]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setErrors({});
    setBusy(true);
    try {
      const result = await signup({
        store_name: storeName.trim(),
        email:      email.trim(),
        password,
        phone:      phone.trim(),
        ref_code:   refCode.trim().toUpperCase(),
      });
      setAccessToken(result.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        // Map per-field errors back to the specific input. Server
        // returns {detail: {field, message}} for 422/409 — we
        // surface the field-level message under that input and
        // hide the page-level error for the same field.
        const detail = (err.body as { detail?: { field?: string; message?: string } } | null)?.detail;
        if (detail?.field && detail?.message) {
          setErrors({ [detail.field]: detail.message });
          setError(null);
        }
      } else {
        setError("Could not create account. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <style>{SIGNUP_CSS}</style>

      <nav className="site">
        <Link to="/" className="nav-brand">
          <img className="mark" src="/static/brand-mark.svg" alt="" />
          <span className="name">DineroBook</span>
        </Link>
        <Link to="/login" className="nav-login">Already have an account? Sign in</Link>
      </nav>

      <div className="page">
        <div className="page-grid" aria-hidden="true" />
        <div className="page-glow" aria-hidden="true" />

        <div className="card">
          <div className="status-pill">
            <span className="dot" />
            <span className="label">✓ 7-DAY FREE TRIAL · NO CARD</span>
          </div>
          <div className="card-title">Create your store</div>
          <div className="card-sub">Close your first daily book in ten minutes.</div>

          {referral && (
            <div className="referral-banner">
              🎉 Referred by a DineroBook user — you'll get
              {" "}<strong>${(referral.reward_referee_cents / 100).toFixed(0)}</strong>
              {" "}off your first paid month when you subscribe.
            </div>
          )}

          {error && <div className="error-msg page-error">{error}</div>}

          <form onSubmit={onSubmit}>
            <Field label="Store Name" error={errors.store_name}>
              <input
                type="text"
                value={storeName}
                onChange={(e) => setStoreName(e.target.value)}
                placeholder="e.g. Lamar Money Center"
                disabled={busy}
                required
              />
            </Field>
            <Field label="Store Email" error={errors.email}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="store@example.com"
                autoComplete="email"
                disabled={busy}
                required
              />
            </Field>
            <Field label="Password" error={errors.password}>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min. 8 characters"
                autoComplete="new-password"
                minLength={8}
                disabled={busy}
                required
              />
            </Field>
            <Field label="Phone" optional>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="555-000-0000"
                autoComplete="tel"
                disabled={busy}
              />
            </Field>
            <Field label="Referral code" optional>
              <input
                type="text"
                value={refCode}
                onChange={(e) => setRefCode(e.target.value.toUpperCase())}
                placeholder="e.g. ABCD1234"
                maxLength={12}
                disabled={busy}
                style={{
                  textTransform: "uppercase",
                  fontFamily: "var(--db-font-mono)",
                  letterSpacing: "2px",
                }}
              />
            </Field>
            <button
              type="submit"
              className={`submit-btn${busy ? " is-busy" : ""}`}
              disabled={busy || !storeName || !email || !password}
            >
              {busy ? "Creating store…" : "Start free trial →"}
            </button>
          </form>

          <div className="login-prompt">
            Already have an account? <Link to="/login">Sign in</Link>
          </div>
          <div className="login-prompt" style={{ marginTop: 10 }}>
            Own multiple locations? <a href="/signup/owner">Sign up as an owner →</a>
          </div>
        </div>
      </div>
    </>
  );
}


function Field({
  label, optional, error, children,
}: {
  label: string;
  optional?: boolean;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label>
        {label}
        {optional && <span className="optional">(optional)</span>}
      </label>
      {children}
      {error && <div className="error-msg">{error}</div>}
    </div>
  );
}


// CSS lifted verbatim from templates/signup.html so visual diff
// against the legacy page stays at zero. Tokens come from the
// global static/design-tokens.css.
const SIGNUP_CSS = `
.signup-shell *,.signup-shell *::before,.signup-shell *::after{box-sizing:border-box;margin:0;padding:0}
nav.site{position:sticky;top:0;z-index:100;background:rgba(11,13,18,0.85);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:0 40px;height:60px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--db-gray-2)}
.nav-brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.nav-brand .mark{width:28px;height:28px;border-radius:8px;box-shadow:0 0 12px rgba(63,255,0,0.40);display:block}
.nav-brand .name{font-family:var(--db-font-display);color:var(--db-gray-9);font-size:17px;font-weight:600;letter-spacing:-.02em}
.nav-login{color:var(--db-gray-7);font-size:13px;text-decoration:none;font-weight:500}
.nav-login:hover{color:var(--db-gray-9)}

.page{min-height:calc(100vh - 60px);min-height:calc(100dvh - 60px);display:flex;align-items:center;justify-content:center;padding:48px 24px;position:relative;overflow:hidden;background:var(--db-bg);color:var(--db-gray-9);font-family:var(--db-font-body);-webkit-font-smoothing:antialiased}
.page-glow{position:absolute;inset:0;background:radial-gradient(ellipse 50% 40% at 50% 30%,var(--db-neon-glow-15),transparent 70%);pointer-events:none}
.page-grid{position:absolute;inset:0;background-image:linear-gradient(var(--db-gray-2) 1px,transparent 1px),linear-gradient(90deg,var(--db-gray-2) 1px,transparent 1px);background-size:48px 48px;-webkit-mask-image:radial-gradient(ellipse at 50% 40%,black 20%,transparent 60%);mask-image:radial-gradient(ellipse at 50% 40%,black 20%,transparent 60%);opacity:.4;pointer-events:none}

.card{position:relative;background:var(--db-bg-elevated);border:1px solid var(--db-gray-3);border-radius:16px;padding:36px 40px;width:100%;max-width:460px;box-shadow:0 24px 80px rgba(0,0,0,0.5)}

.status-pill{display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border:1px solid var(--db-gray-2);border-radius:999px;background:var(--db-bg-input);margin-bottom:20px}
.status-pill .dot{width:6px;height:6px;border-radius:999px;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon)}
.status-pill .label{font-family:var(--db-font-mono);font-size:10px;color:var(--db-neon);letter-spacing:1.5px}

.card-title{font-family:var(--db-font-display);font-size:30px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.025em;margin-bottom:6px}
.card-sub{font-size:13.5px;color:var(--db-gray-7);margin-bottom:24px}

.referral-banner{background:var(--db-neon-glow-8);color:var(--db-neon);border:1px solid rgba(63,255,0,.3);border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:18px;font-family:var(--db-font-body)}
.referral-banner strong{color:var(--db-neon-bright)}

.field{margin-bottom:16px}
.card label{display:block;font-family:var(--db-font-mono);font-size:10.5px;font-weight:500;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
.optional{color:var(--db-gray-5);font-weight:400;font-size:10px;margin-left:4px;letter-spacing:normal;text-transform:none}
.card input{width:100%;padding:12px 14px;background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:10px;font-size:14px;color:var(--db-gray-9);font-family:var(--db-font-body);outline:none;transition:border-color .15s,box-shadow .15s}
.card input:focus{border-color:var(--db-neon);box-shadow:0 0 0 3px var(--db-neon-glow-15)}
.card input::placeholder{color:var(--db-gray-5)}
.field.has-error input{border-color:var(--db-negative)}
.error-msg{font-size:12px;color:var(--db-negative);margin-top:5px}
.error-msg.page-error{background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.3);border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:18px;margin-top:0}

.submit-btn{width:100%;background:var(--db-neon);color:var(--db-neon-ink);border:none;padding:14px;border-radius:10px;font-size:14.5px;font-weight:600;cursor:pointer;font-family:var(--db-font-body);letter-spacing:-.01em;margin-top:10px;box-shadow:0 0 0 1px var(--db-neon),0 0 28px var(--db-neon-glow-40);transition:background .12s}
.submit-btn:hover:not(:disabled){background:var(--db-neon-bright)}
.submit-btn:disabled{opacity:.6;cursor:not-allowed}
.submit-btn.is-busy:disabled{cursor:wait}

.login-prompt{text-align:center;margin-top:16px;font-size:13px;color:var(--db-gray-7)}
.login-prompt a{color:var(--db-neon);text-decoration:none;font-weight:500}

@media (max-width:600px){
  nav.site{padding:0 16px;height:56px}
  .nav-brand .name{font-size:16px}
  .nav-login{font-size:12px}
  .page{padding:24px 14px;min-height:calc(100vh - 56px);min-height:calc(100dvh - 56px)}
  .card{padding:28px 24px;border-radius:14px}
  .card-title{font-size:24px}
  .card input{font-size:16px;padding:13px 14px}
  .submit-btn{padding:14px;font-size:15px}
}
@media (max-width:380px){
  .nav-login{display:none}
}
`;
