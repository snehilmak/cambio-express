import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import {
  getCurrentIdentity, getRefreshFallback, persistLoginResponse,
} from "../lib/auth";
import { Loading } from "./ui";

interface Props {
  children: React.ReactNode;
}

// Route guard that bounces unauthed users to /login.  Designed to
// wrap the children of a <Route element={...}> entry.  Preserves
// the originally-requested path in `location.state.from` so the
// login page can return the user there after a successful sign-in.
//
// PWA recovery: the identity cache lives in localStorage but the
// actual auth lives in the `db_refresh_token` httpOnly cookie
// (good for 14 days).  iOS PWAs (and some Android Chrome modes)
// aggressively clear localStorage on app close even when cookies
// survive — that left users facing a "please sign in again"
// prompt on every cold open of the installed app, even though
// they HAD a valid refresh cookie.
//
// On mount with no identity hint, we POST /auth/refresh once.  If
// the refresh cookie's still valid the server hands us a fresh
// access cookie + the identity claims; we persist those back into
// localStorage and let the user through without re-auth.  If the
// refresh fails (no cookie, revoked, expired), we bounce to /login
// — same UX as before.

export default function RequireAuth({ children }: Props) {
  const identityFromStorage = getCurrentIdentity();
  const location = useLocation();
  // `ok` when storage already has the identity hint; otherwise
  // `checking` while we probe /auth/refresh; `denied` if the
  // probe fails (or storage was empty AND refresh 401s).
  const [bootState, setBootState] = useState<"ok" | "checking" | "denied">(
    identityFromStorage ? "ok" : "checking",
  );

  useEffect(() => {
    if (identityFromStorage) return;
    let cancelled = false;
    void (async () => {
      try {
        const fallbackJti = getRefreshFallback();
        const resp = await fetch("/api/v2/auth/refresh", {
          method: "POST",
          credentials: "include",
          headers: fallbackJti
            ? { "Content-Type": "application/json" }
            : undefined,
          body: fallbackJti
            ? JSON.stringify({ refresh_token: fallbackJti })
            : undefined,
        });
        if (cancelled) return;
        if (resp.ok) {
          const body = await resp.json();
          if (body && typeof body.user_id === "number") {
            persistLoginResponse(body);
            setBootState("ok");
            return;
          }
        }
      } catch {
        // Network failure → fall through to denied; the user can
        // retry from /login.
      }
      if (!cancelled) setBootState("denied");
    })();
    return () => { cancelled = true; };
  }, [identityFromStorage]);

  if (bootState === "checking") {
    return <Loading />;
  }
  if (bootState === "denied") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }
  return <>{children}</>;
}
