import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { signupOwner } from "../api/account";
import { ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";

// Multi-store owner signup at /app/signup/owner. Visual chrome
// lifted from templates/signup_owner.html (the legacy Jinja
// version) so the visual diff stays at zero.
//
// Form contract mirrors the legacy /signup/owner POST: full name +
// email + password. On success the server returns a JWT for the
// new owner (role="owner", store_id=null) and we drop the user
// straight onto /owner/dashboard.
export default function SignupOwner() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [busy,     setBusy]     = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [errors,   setErrors]   = useState<Record<string, string>>({});

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setErrors({});
    setBusy(true);
    try {
      const result = await signupOwner({
        full_name: fullName.trim(),
        email:     email.trim(),
        password,
      });
      setAccessToken(result.access_token);
      navigate("/owner/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
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
      <style>{OWNER_CSS}</style>

      <nav className="site">
        <Link to="/" className="nav-brand">
          <img className="mark" src="/static/brand-mark.svg" alt="" />
          <span className="name">DineroBook</span>
        </Link>
        <Link to="/login" className="nav-login">Already have an account? Sign in</Link>
      </nav>

      <div className="page">
        <div className="page-glow" aria-hidden="true" />
        <div className="card">
          <div className="pill">★ MULTI-STORE OWNER</div>
          <div className="card-title">Create owner account</div>
          <div className="card-sub">Manage multiple store locations from one login.</div>

          {error && <div className="error-msg page-error">{error}</div>}

          <form onSubmit={onSubmit}>
            <Field label="Full Name" error={errors.full_name}>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your full name"
                disabled={busy}
                required
              />
            </Field>
            <Field label="Email" error={errors.email}>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
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
            <button
              type="submit"
              className={`submit-btn${busy ? " is-busy" : ""}`}
              disabled={busy || !fullName || !email || !password}
            >
              {busy ? "Creating account…" : "Create owner account →"}
            </button>
          </form>

          <div className="login-prompt">
            Already have an account? <Link to="/login">Sign in</Link>
          </div>
          <div className="login-prompt" style={{ marginTop: 10 }}>
            Managing a single store? <Link to="/signup">Sign up as a store</Link>
          </div>
        </div>
      </div>
    </>
  );
}


function Field({
  label, error, children,
}: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label>{label}</label>
      {children}
      {error && <div className="error-msg">{error}</div>}
    </div>
  );
}


// Chrome lifted from templates/signup_owner.html. The CSS shared
// with /app/signup, /app/forgot-password, /app/reset-password is
// scheduled for extraction into a shared AuthShell once all auth
// pages have migrated — see the auth-dedup TODO PR.
const OWNER_CSS = `
nav.site{position:sticky;top:0;z-index:100;background:rgba(11,13,18,0.85);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:0 40px;height:60px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--db-gray-2)}
.nav-brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.nav-brand .mark{width:28px;height:28px;border-radius:8px;box-shadow:0 0 12px rgba(63,255,0,0.40);display:block}
.nav-brand .name{font-family:var(--db-font-display);color:var(--db-gray-9);font-size:17px;font-weight:600;letter-spacing:-.02em}
.nav-login{color:var(--db-gray-7);font-size:13px;text-decoration:none;font-weight:500}
.nav-login:hover{color:var(--db-gray-9)}

.page{min-height:calc(100vh - 60px);min-height:calc(100dvh - 60px);display:flex;align-items:center;justify-content:center;padding:48px 24px;position:relative;overflow:hidden;background:var(--db-bg);color:var(--db-gray-9);font-family:var(--db-font-body);-webkit-font-smoothing:antialiased}
.page-glow{position:absolute;inset:0;background:radial-gradient(ellipse 50% 40% at 50% 30%,var(--db-neon-glow-15),transparent 70%);pointer-events:none}

.card{position:relative;background:var(--db-bg-elevated);border:1px solid var(--db-gray-3);border-radius:16px;padding:36px 40px;width:100%;max-width:460px;box-shadow:0 24px 80px rgba(0,0,0,0.5)}

.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border:1px solid rgba(63,255,0,.3);border-radius:999px;background:var(--db-neon-glow-8);font-family:var(--db-font-mono);font-size:10px;color:var(--db-neon);letter-spacing:1.5px;margin-bottom:20px;text-transform:uppercase;font-weight:500}

.card-title{font-family:var(--db-font-display);font-size:30px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.025em;margin-bottom:6px}
.card-sub{font-size:13.5px;color:var(--db-gray-7);margin-bottom:24px}

.field{margin-bottom:16px}
.card label{display:block;font-family:var(--db-font-mono);font-size:10.5px;font-weight:500;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
.card input{width:100%;padding:12px 14px;background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:10px;font-size:14px;color:var(--db-gray-9);font-family:var(--db-font-body);outline:none;transition:border-color .15s,box-shadow .15s}
.card input:focus{border-color:var(--db-neon);box-shadow:0 0 0 3px var(--db-neon-glow-15)}
.card input::placeholder{color:var(--db-gray-5)}
.field.has-error input{border-color:var(--db-negative)}
.error-msg{font-size:12px;color:var(--db-negative);margin-top:5px}
.error-msg.page-error{background:var(--db-tone-error-bg,rgba(255,77,109,.08));border:1px solid var(--db-tone-error-border,rgba(255,77,109,.3));border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:18px;margin-top:0}

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
}
@media (max-width:380px){
  .nav-login{display:none}
}
`;
