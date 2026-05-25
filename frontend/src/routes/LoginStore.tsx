import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { lookupStoreBySlug, type StoreLookup } from "../api/account";
import { api, ApiError } from "../lib/api";
import { setAccessToken } from "../lib/auth";

interface LoginResponse {
  access_token: string;
}

// Per-store employee sign-in at /app/login/:slug. Visual chrome
// (split-screen with brand pane on the left, neon form card on
// the right) lifted from templates/login_store.html so the diff
// against the legacy page stays at zero.
//
// Form contract: submit username + password to /api/v2/auth/login
// scoped to the resolved store_id. The backend sets the
// `ds_last_store` cookie automatically (legacy parity) so an
// installed-PWA employee with cleared session still gets bounced
// here on next visit.
export default function LoginStore() {
  const { slug = "" } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [store,    setStore]    = useState<StoreLookup | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy,     setBusy]     = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset loading/error/store flags before async lookup of the store by slug; cancellation flag guards stale resolutions
    setLoading(true); setNotFound(false); setStore(null);
    lookupStoreBySlug(slug).then(
      (s) => {
        if (cancelled) return;
        if (s === null) setNotFound(true); else setStore(s);
        setLoading(false);
      },
      () => {
        if (!cancelled) { setNotFound(true); setLoading(false); }
      },
    );
    return () => { cancelled = true; };
  }, [slug]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!store) return;
    setError(null); setBusy(true);
    try {
      const result = await api<LoginResponse>("/api/v2/auth/login", {
        method: "POST",
        json: {
          username: username.trim(),
          password,
          store_id: store.store_id,
        },
      });
      setAccessToken(result.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Network error. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <style>{LOGIN_STORE_CSS}</style>

      {loading ? (
        <div className="loading-shell">Loading…</div>
      ) : notFound ? (
        <div className="loading-shell">
          <div className="card-title">Store not found</div>
          <div className="card-sub">
            We couldn't find a store with that code. Check with your
            manager for the correct URL.
          </div>
          <Link to="/login" className="back-link">← Back to sign in</Link>
        </div>
      ) : store ? (
        <div className="store-shell">
          <div className="login-left">
            <div className="bg-grid" aria-hidden="true" />
            <div className="bg-glow" aria-hidden="true" />
            <div className="brand-block">
              <img className="brand-mark" src="/static/brand-mark.svg" alt="" />
              <div className="brand-name">DineroBook</div>
              <div className="brand-store">{store.name}</div>
              <div className="brand-tagline">Employee portal</div>
            </div>
          </div>

          <div className="login-right">
            <div className="status-pill">
              <span className="dot" />
              <span className="label">SECURE · {store.name.toUpperCase()}</span>
            </div>
            <div className="login-heading">Employee sign in</div>
            <div className="login-sub">
              Sign in with the username your store admin gave you.
            </div>

            {error && <div className="error-msg">{error}</div>}

            <form onSubmit={onSubmit}>
              <div className="field">
                <label>Username</label>
                <input
                  type="text"
                  placeholder="your-username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={busy}
                  required
                  autoFocus
                />
              </div>
              <div className="field">
                <label>Password</label>
                <input
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={busy}
                  required
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

            <div className="login-footer">{store.name} · DineroBook</div>
          </div>
        </div>
      ) : null}
    </>
  );
}


// Page-local CSS lifted from templates/login_store.html so the
// visual diff stays at zero. Tokens come from the global
// design-tokens.css.
const LOGIN_STORE_CSS = `
.store-shell{display:flex;min-height:100vh;min-height:100dvh;background:var(--db-bg);color:var(--db-gray-9);font-family:var(--db-font-body);overscroll-behavior-y:none;-webkit-font-smoothing:antialiased}
.store-shell *,.store-shell *::before,.store-shell *::after{box-sizing:border-box;margin:0;padding:0}
.store-shell ::selection{background:var(--db-neon);color:var(--db-neon-ink)}

.login-left{flex:1;min-width:360px;background:var(--db-bg);border-right:1px solid var(--db-gray-2);padding:40px 48px;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
.login-left .bg-grid{position:absolute;inset:0;background-image:linear-gradient(var(--db-gray-2) 1px,transparent 1px),linear-gradient(90deg,var(--db-gray-2) 1px,transparent 1px);background-size:48px 48px;-webkit-mask-image:radial-gradient(ellipse at center,black 20%,transparent 70%);mask-image:radial-gradient(ellipse at center,black 20%,transparent 70%);opacity:.5;pointer-events:none}
.login-left .bg-glow{position:absolute;top:30%;right:-10%;width:420px;height:420px;background:radial-gradient(circle,var(--db-neon-glow-25),transparent 60%);pointer-events:none}
.brand-block{text-align:center;position:relative;z-index:1}
.brand-mark{width:52px;height:52px;border-radius:12px;box-shadow:0 0 24px rgba(63,255,0,0.40);margin-bottom:18px;display:block;margin-left:auto;margin-right:auto}
.brand-name{font-family:var(--db-font-display);font-size:30px;font-weight:600;color:var(--db-gray-9);letter-spacing:-.02em;line-height:1}
.brand-store{font-size:14px;color:var(--db-gray-7);margin-top:10px;letter-spacing:.5px;font-weight:500}
.brand-tagline{font-family:var(--db-font-mono);font-size:11px;color:var(--db-gray-6);margin-top:10px;letter-spacing:1.5px;text-transform:uppercase}

.login-right{width:520px;background:var(--db-bg);display:flex;flex-direction:column;justify-content:center;padding:48px;overflow-y:auto;max-height:100vh;max-height:100dvh}
.status-pill{display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border:1px solid var(--db-gray-3);border-radius:999px;background:var(--db-bg-elevated);margin-bottom:22px;align-self:flex-start}
.status-pill .dot{width:6px;height:6px;border-radius:999px;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon)}
.status-pill .label{font-family:var(--db-font-mono);font-size:10px;color:var(--db-gray-7);letter-spacing:1.2px}
.login-heading{font-family:var(--db-font-display);font-size:30px;font-weight:600;color:var(--db-gray-9);letter-spacing:-.025em;margin-bottom:6px}
.login-sub{font-size:14px;color:var(--db-gray-7);margin-bottom:28px}
.field{display:flex;flex-direction:column;gap:7px;margin-bottom:16px}
.login-right label{font-family:var(--db-font-mono);font-size:10.5px;font-weight:500;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase}
.login-right input{padding:13px 14px;background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:10px;font-size:14px;font-family:var(--db-font-body);color:var(--db-gray-9);width:100%;outline:none;transition:border-color .15s,box-shadow .15s}
.login-right input::placeholder{color:var(--db-gray-5)}
.login-right input:focus{border-color:var(--db-neon);box-shadow:0 0 0 3px var(--db-neon-glow-15)}
.error-msg{background:rgba(255,77,109,.08);color:var(--db-negative);border:1px solid rgba(255,77,109,.3);border-radius:10px;padding:11px 14px;font-size:13px;margin-bottom:16px}
.btn-login{width:100%;padding:14px;background:var(--db-neon);color:var(--db-neon-ink);border:none;border-radius:10px;font-size:14.5px;font-weight:600;font-family:var(--db-font-body);letter-spacing:-.01em;cursor:pointer;margin-top:6px;box-shadow:0 0 0 1px var(--db-neon),0 0 28px var(--db-neon-glow-40);transition:background .12s}
.btn-login:hover:not(:disabled){background:var(--db-neon-bright)}
.btn-login:disabled{opacity:.6;cursor:not-allowed}
.btn-login.is-busy:disabled{cursor:wait}
.login-footer{margin-top:28px;font-family:var(--db-font-mono);font-size:11px;color:var(--db-gray-6);text-align:center;letter-spacing:.5px}

.loading-shell{min-height:100vh;min-height:100dvh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 24px;background:var(--db-bg);color:var(--db-gray-7);font-family:var(--db-font-body);text-align:center;gap:12px}
.loading-shell .card-title{font-family:var(--db-font-display);font-size:28px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.025em}
.loading-shell .card-sub{font-size:14px;color:var(--db-gray-7);max-width:420px;line-height:1.6}
.loading-shell .back-link{margin-top:12px;color:var(--db-neon);font-size:13px;text-decoration:none;font-weight:500}
.loading-shell .back-link:hover{color:var(--db-neon-bright)}

@media (max-width:900px){
  .store-shell{flex-direction:column}
  .login-left{flex:none;min-width:0;padding:24px 24px 20px;padding-top:max(24px,env(safe-area-inset-top));border-right:none;border-bottom:1px solid var(--db-gray-2)}
  .login-left .bg-grid,.login-left .bg-glow{display:none}
  .brand-mark{width:40px;height:40px;margin-bottom:10px}
  .brand-name{font-size:22px}
  .brand-store{font-size:13px;margin-top:6px}
  .brand-tagline{font-size:10px}
  .login-right{width:100%;padding:24px 24px 32px;padding-bottom:max(32px,env(safe-area-inset-bottom));flex:0 0 auto;max-height:none}
  .login-heading{font-size:24px}
  .login-sub{margin-bottom:22px}
  .field{margin-bottom:14px}
  .login-right input{font-size:16px}
  .login-footer{margin-top:24px}
}
@media (max-width:480px){
  .login-left{padding:20px 20px 16px;padding-top:max(20px,env(safe-area-inset-top))}
  .login-right{padding:20px 20px 24px;padding-bottom:max(24px,env(safe-area-inset-bottom))}
  .brand-name{font-size:20px}
  .brand-mark{width:36px;height:36px}
}
`;
