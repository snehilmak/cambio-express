// Authentication helpers — JWT storage + identity claims for
// the SPA. We keep the access token in localStorage so it
// survives a page refresh; that's the same trust boundary as
// `document.cookie` on the legacy site (XSS still wins, the
// attacker has the session either way), and it lets us send
// the bearer token from JS without a server-set cookie path.
//
// When the JWT cutover for refresh tokens lands, we'll layer
// silent-refresh on top of this — for now sessions live for
// `expires_in` seconds (default 30 minutes) and a 401 from any
// API call clears the token and bounces to /app/login.

const TOKEN_KEY = "db.access_token";

export interface IdentityClaims {
  user_id: number;
  username: string;
  full_name: string;
  role: string;
  store_id: number | null;
  permissions: string[];
}

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    // Storage can throw in a sandboxed iframe / private mode.
    // Treat as "no token" — the SPA bounces to /app/login.
    return null;
  }
}

export function setAccessToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore */
  }
}

export function clearAccessToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

// Decode the payload from a JWT. Pure base64url decode + JSON
// parse — no signature verification (the server has already
// verified by the time the token reaches the client; we only use
// the claims for rendering chrome). Returns null on any parse
// error so callers can treat it as "no identity".
export function decodeJwtClaims(token: string): IdentityClaims | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1]
      // base64url → base64
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

export function getCurrentIdentity(): IdentityClaims | null {
  const token = getAccessToken();
  if (!token) return null;
  return decodeJwtClaims(token);
}
