import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { forgotPassword } from "../api/account";

// /app/forgot-password — request a reset link.
//
// Per CLAUDE.md security invariant #10 the response is always
// "Check your email" regardless of whether the address exists,
// so attackers can't enumerate registered emails. The SPA mirrors
// that: success message renders the same shape no matter what
// the server returned.
//
// Visual chrome (sticky nav + status pill + dark backdrop) lifted
// from the same family used by Login + Signup so the auth flow
// reads as one experience.
export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy,  setBusy]  = useState(false);
  const [done,  setDone]  = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await forgotPassword(email.trim());
    } catch {
      // Server responds 200 even on unknown email; if a network
      // hiccup loses the request we still flip to the success state
      // so we don't leak whether the address was registered.
    } finally {
      setBusy(false);
      setDone(true);
    }
  }

  return (
    <>
      <style>{AUTH_CSS}</style>

      <nav className="site">
        <Link to="/" className="nav-brand">
          <img className="mark" src="/static/brand-mark.svg" alt="" />
          <span className="name">DineroBook</span>
        </Link>
        <Link to="/login" className="nav-login">← Back to sign in</Link>
      </nav>

      <div className="page">
        <div className="page-grid" aria-hidden="true" />
        <div className="page-glow" aria-hidden="true" />

        <div className="card">
          {done ? (
            <>
              <div className="status-pill">
                <span className="dot" />
                <span className="label">✓ EMAIL SENT</span>
              </div>
              <div className="card-title">Check your email</div>
              <div className="card-sub">
                If <span className="mono">{email}</span> is registered, you'll
                receive a link to set a new password. The link expires in
                1 hour. If you don't see it, check your spam folder.
              </div>
              <Link to="/login" className="back-link">← Back to sign in</Link>
            </>
          ) : (
            <>
              <div className="status-pill">
                <span className="dot" />
                <span className="label">PASSWORD RESET</span>
              </div>
              <div className="card-title">Forgot your password?</div>
              <div className="card-sub">
                Enter the email on your account. We'll send a one-time link
                to set a new password. For employees, contact your store
                admin for a reset.
              </div>
              <form onSubmit={onSubmit}>
                <div className="field">
                  <label>Email</label>
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={busy}
                    required
                    autoFocus
                  />
                </div>
                <button
                  type="submit"
                  className={`submit-btn${busy ? " is-busy" : ""}`}
                  disabled={busy || !email}
                >
                  {busy ? "Sending…" : "Send reset link"}
                </button>
              </form>
              <Link to="/login" className="back-link">← Back to sign in</Link>
            </>
          )}
        </div>
      </div>
    </>
  );
}


// Shared chrome with /app/reset-password and /app/signup. When all
// auth pages are migrated a follow-up PR pulls these into a single
// AuthShell + AuthCard component.
const AUTH_CSS = `
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
.card-sub{font-size:13.5px;color:var(--db-gray-7);margin-bottom:24px;line-height:1.6}
.card-sub .mono{font-family:var(--db-font-mono);color:var(--db-gray-9);font-size:13px}

.field{margin-bottom:18px}
.card label{display:block;font-family:var(--db-font-mono);font-size:10.5px;font-weight:500;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
.card input{width:100%;padding:12px 14px;background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:10px;font-size:14px;color:var(--db-gray-9);font-family:var(--db-font-body);outline:none;transition:border-color .15s,box-shadow .15s}
.card input:focus{border-color:var(--db-neon);box-shadow:0 0 0 3px var(--db-neon-glow-15)}
.card input::placeholder{color:var(--db-gray-5)}
.error-msg{background:rgba(255,77,109,.08);color:var(--db-negative);border:1px solid rgba(255,77,109,.3);border-radius:10px;padding:11px 14px;font-size:13px;margin-bottom:18px;font-family:var(--db-font-body)}

.submit-btn{width:100%;background:var(--db-neon);color:var(--db-neon-ink);border:none;padding:14px;border-radius:10px;font-size:14.5px;font-weight:600;cursor:pointer;font-family:var(--db-font-body);letter-spacing:-.01em;margin-top:10px;box-shadow:0 0 0 1px var(--db-neon),0 0 28px var(--db-neon-glow-40);transition:background .12s}
.submit-btn:hover:not(:disabled){background:var(--db-neon-bright)}
.submit-btn:disabled{opacity:.6;cursor:not-allowed}
.submit-btn.is-busy:disabled{cursor:wait}

.back-link{display:block;text-align:center;margin-top:20px;font-size:13px;color:var(--db-gray-7);text-decoration:none;font-weight:500}
.back-link:hover{color:var(--db-neon)}

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
`;
