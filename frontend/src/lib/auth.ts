// Authentication helpers — JWT lives in an httpOnly cookie now
// (set by the backend on /auth/login + /signup) so XSS can't
// exfiltrate the token. We keep a separate **identity cache** in
// localStorage with the non-secret claims (role, store_id, etc.)
// so the React shell can render user chrome on first paint without
// a network roundtrip. That cache is just a hint — the cookie is
// the actual auth — so even if XSS reads it, no privilege escalation.
//
// PR #559: moved the JWT off localStorage. Old name
// ``db.access_token`` is now ``db.identity`` and stores a parsed
// claims object instead of a raw token. Code paths that used to
// read ``getAccessToken()`` either go away (the bearer header
// isn't needed; the cookie travels automatically) or call
// ``hasIdentity()`` which is a non-secret check.

const IDENTITY_KEY = "db.identity";

export interface IdentityClaims {
  user_id: number;
  username: string;
  full_name: string;
  role: string;
  store_id: number | null;
  permissions: string[];
}


function _read(): IdentityClaims | null {
  try {
    const raw = window.localStorage.getItem(IDENTITY_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as IdentityClaims;
    if (typeof parsed.user_id !== "number" || typeof parsed.role !== "string") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}


function _write(claims: IdentityClaims): void {
  try {
    window.localStorage.setItem(IDENTITY_KEY, JSON.stringify(claims));
  } catch {
    /* sandboxed iframe / private mode — chrome will re-render unauthed */
  }
}


function _clear(): void {
  try {
    window.localStorage.removeItem(IDENTITY_KEY);
  } catch {
    /* ignore */
  }
}


export function getCurrentIdentity(): IdentityClaims | null {
  return _read();
}


export function setCurrentIdentity(claims: IdentityClaims): void {
  _write(claims);
}


/**
 * Hard sign-out helper. Drops the local identity hint and asks
 * the server to clear the httpOnly cookie via POST /auth/logout.
 * Caller is responsible for navigating to /app/login afterwards
 * (or letting the next 401 from a stale page do it).
 */
export async function logout(): Promise<void> {
  _clear();
  try {
    await fetch("/api/v2/auth/logout", {
      method: "POST",
      credentials: "include",
    });
  } catch {
    /* Cookie still drops on the next 401; nothing more to do */
  }
}


/**
 * Stash the LoginResponse from /auth/login into the identity
 * cache. The httpOnly cookie was set by the server in the same
 * response; we just persist the public-safe claims for chrome
 * rendering.
 */
export function persistLoginResponse(body: {
  user_id: number;
  username: string;
  full_name: string;
  role: string;
  store_id: number | null;
  permissions: string[];
}): void {
  _write({
    user_id: body.user_id,
    username: body.username,
    full_name: body.full_name,
    role: body.role,
    store_id: body.store_id,
    permissions: body.permissions,
  });
}


// ── Back-compat aliases for the localStorage-token era ─────────
//
// Routes still call ``setAccessToken(result.access_token)`` after
// login. The token is now stored server-side as an httpOnly
// cookie; what the SPA caches in localStorage is just the
// non-secret claims (role, store_id, permissions, ...) for chrome
// rendering. Decode the JWT body locally — no signature verify
// needed; the cookie is the auth — and persist the claims.

function _decodeJwtClaims(token: string): IdentityClaims | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/");
    const padded = payload.padEnd(
      payload.length + ((4 - (payload.length % 4)) % 4),
      "=",
    );
    const json = JSON.parse(atob(padded));
    return {
      user_id: Number(json.sub),
      username: String(json.username ?? ""),
      full_name: String(json.name ?? ""),
      role: String(json.role ?? ""),
      store_id:
        json.store_id === null || json.store_id === undefined
          ? null
          : Number(json.store_id),
      permissions: Array.isArray(json.perms) ? json.perms.map(String) : [],
    };
  } catch {
    return null;
  }
}

/** @deprecated kept for back-compat — only returns the parsed
 *  payload, never the token itself. New code reads via
 *  ``getCurrentIdentity()``. */
export const decodeJwtClaims = _decodeJwtClaims;

/** @deprecated The token lives in an httpOnly cookie now; this
 *  always returns ``null``. Auth checks should go through
 *  ``getCurrentIdentity()`` (chrome state) or a fetch to a
 *  protected endpoint (real auth). */
export function getAccessToken(): string | null {
  return null;
}

/** Cache the non-secret claims locally. Decodes the JWT payload
 *  from the login response so old call sites that pass
 *  ``result.access_token`` keep working — the cookie is already
 *  set server-side, we just need the chrome bits client-side.
 *  @deprecated prefer ``persistLoginResponse(result)`` which
 *  reads the response body fields directly. */
export function setAccessToken(token: string): void {
  const claims = _decodeJwtClaims(token);
  if (claims) {
    _write(claims);
  }
}

/** Drop the local identity cache. Doesn't clear the server-side
 *  cookie — for that, call ``logout()``. */
export function clearAccessToken(): void {
  _clear();
}
