import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { resetPassword } from "../api/account";
import { ApiError } from "../lib/api";

// /app/reset-password?token=… — consume a one-time token to set
// a new password. Token comes from the email link.
//
// Visual chrome matches /app/forgot-password and the rest of the
// auth family: sticky brand nav, dark backdrop with grid + glow,
// status pill on the card.
export default function ResetPassword() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const token = sp.get("token") ?? "";
  const [pw,      setPw]      = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy,    setBusy]    = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [done,    setDone]    = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (pw !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (pw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword({
        token,
        new_password: pw,
        confirm_password: confirm,
      });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reset password. The link may be expired.",
      );
    } finally {
      setBusy(false);
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
          {!token ? (
            <>
              <div className="status-pill error-pill">
                <span className="dot" />
                <span className="label">LINK MISSING</span>
              </div>
              <div className="card-title">Reset link missing</div>
              <div className="card-sub">
                This link doesn't include a token. Request a new reset link
                and we'll email you a fresh one.
              </div>
              <Link to="/forgot-password" className="submit-btn submit-link">
                Request a new link
              </Link>
              <Link to="/login" className="back-link">← Back to sign in</Link>
            </>
          ) : done ? (
            <>
              <div className="status-pill">
                <span className="dot" />
                <span className="label">✓ PASSWORD UPDATED</span>
              </div>
              <div className="card-title">Password updated</div>
              <div className="card-sub">
                You can now sign in with your new password.
              </div>
              <button
                type="button"
                className="submit-btn"
                onClick={() => navigate("/login")}
              >
                Sign in →
              </button>
            </>
          ) : (
            <>
              <div className="status-pill">
                <span className="dot" />
                <span className="label">SET A NEW PASSWORD</span>
              </div>
              <div className="card-title">Set a new password</div>
              <div className="card-sub">Choose something at least 8 characters long.</div>

              {error && <div className="error-msg">{error}</div>}

              <form onSubmit={onSubmit}>
                <div className="field">
                  <label>New password</label>
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    placeholder="Min. 8 characters"
                    value={pw}
                    onChange={(e) => setPw(e.target.value)}
                    disabled={busy}
                    required
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label>Confirm new password</label>
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    placeholder="Repeat"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    disabled={busy}
                    required
                  />
                </div>
                <button
                  type="submit"
                  className={`submit-btn${busy ? " is-busy" : ""}`}
                  disabled={busy || !pw || !confirm}
                >
                  {busy ? "Saving…" : "Update password"}
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


// Same CSS used by ForgotPassword.tsx. When all auth pages
// migrate, a follow-up PR pulls this into a shared AuthShell
// component (and matching ./auth/AuthCard).
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
.status-pill.error-pill{border-color:rgba(255,77,109,.3);background:rgba(255,77,109,.06)}
.status-pill.error-pill .dot{background:var(--db-negative);box-shadow:0 0 8px rgba(255,77,109,.5)}
.status-pill.error-pill .label{color:var(--db-negative)}

.card-title{font-family:var(--db-font-display);font-size:30px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.025em;margin-bottom:6px}
.card-sub{font-size:13.5px;color:var(--db-gray-7);margin-bottom:24px;line-height:1.6}

.field{margin-bottom:18px}
.card label{display:block;font-family:var(--db-font-mono);font-size:10.5px;font-weight:500;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
.card input{width:100%;padding:12px 14px;background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:10px;font-size:14px;color:var(--db-gray-9);font-family:var(--db-font-body);outline:none;transition:border-color .15s,box-shadow .15s}
.card input:focus{border-color:var(--db-neon);box-shadow:0 0 0 3px var(--db-neon-glow-15)}
.card input::placeholder{color:var(--db-gray-5)}
.error-msg{background:rgba(255,77,109,.08);color:var(--db-negative);border:1px solid rgba(255,77,109,.3);border-radius:10px;padding:11px 14px;font-size:13px;margin-bottom:18px;font-family:var(--db-font-body)}

.submit-btn{width:100%;background:var(--db-neon);color:var(--db-neon-ink);border:none;padding:14px;border-radius:10px;font-size:14.5px;font-weight:600;cursor:pointer;font-family:var(--db-font-body);letter-spacing:-.01em;margin-top:10px;box-shadow:0 0 0 1px var(--db-neon),0 0 28px var(--db-neon-glow-40);transition:background .12s;text-decoration:none;text-align:center;display:block}
.submit-btn:hover:not(:disabled){background:var(--db-neon-bright)}
.submit-btn:disabled{opacity:.6;cursor:not-allowed}
.submit-btn.is-busy:disabled{cursor:wait}
.submit-btn.submit-link{box-sizing:border-box;color:var(--db-neon-ink)}

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
