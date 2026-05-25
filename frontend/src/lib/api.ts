// Tiny API client used by every SPA fetch. Wraps `fetch` so:
//   • ``credentials: "include"`` ships the httpOnly access-token
//     cookie automatically (PR #559 — see ``./auth.ts`` for the
//     cookie-vs-localStorage rationale).
//   • a 401 first attempts a silent refresh via ``/auth/refresh``
//     (PR #560 rotating refresh tokens). If that succeeds, retry
//     the original request once. If the refresh itself 401s the
//     session is dead — clear the local identity hint and bounce
//     to /app/login. Callers don't see the hop.
//   • non-2xx becomes a thrown ApiError with the parsed body.
//   • JSON request bodies get the right Content-Type.
//
// We intentionally don't import any HTTP library — `fetch` is
// browser-native, smaller bundle, and good enough for the SPA's
// needs. TanStack Query handles caching/retries on top.

import { clearAccessToken, persistLoginResponse } from "./auth";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface ApiOptions extends Omit<RequestInit, "body"> {
  // JSON-serializable body. Use `null` (or omit) for GET/DELETE.
  json?: unknown;
}

// Single in-flight refresh promise — concurrent 401s from parallel
// requests (the SPA's first paint typically fires 3-4) get the
// same refresh round-trip rather than racing on the token.
let _inFlightRefresh: Promise<boolean> | null = null;

async function _silentRefresh(): Promise<boolean> {
  if (_inFlightRefresh) return _inFlightRefresh;
  _inFlightRefresh = (async () => {
    try {
      const resp = await fetch("/api/v2/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!resp.ok) return false;
      const body = await resp.json();
      // The refresh response carries fresh identity claims — keep
      // the local cache in sync so chrome re-renders correctly.
      if (
        typeof body === "object" && body &&
        typeof body.user_id === "number"
      ) {
        persistLoginResponse(body);
      }
      return true;
    } catch {
      return false;
    } finally {
      _inFlightRefresh = null;
    }
  })();
  return _inFlightRefresh;
}

function _bounceToLogin(): void {
  clearAccessToken();
  const onLogin = window.location.pathname === "/app/login";
  if (!onLogin) window.location.assign("/app/login");
}

export async function api<T = unknown>(
  path: string,
  options: ApiOptions = {},
  // Internal: prevents infinite recursion if the refresh itself
  // 401s. External callers always start with _retryAfterRefresh=true.
  _retryAfterRefresh = true,
): Promise<T> {
  const headers = new Headers(options.headers);

  const init: RequestInit = {
    ...options,
    headers,
    credentials: "include",  // ship the db_access_token httpOnly cookie
  };
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(options.json);
  }

  const resp = await fetch(path, init);

  // 204 No Content has no body — skip parsing entirely.
  if (resp.status === 204) return undefined as T;

  const ct = resp.headers.get("content-type") ?? "";
  const parsed = ct.includes("application/json")
    ? await resp.json()
    : await resp.text();

  if (!resp.ok) {
    if (resp.status === 401 && _retryAfterRefresh) {
      // Try a silent refresh. If it succeeds, retry the original
      // request exactly once (with retry disabled this time so a
      // second 401 doesn't loop forever).
      const refreshed = await _silentRefresh();
      if (refreshed) {
        return api<T>(path, options, /* _retryAfterRefresh = */ false);
      }
      _bounceToLogin();
    } else if (resp.status === 401) {
      _bounceToLogin();
    }
    let message = `Request failed (${resp.status})`;
    if (typeof parsed === "object" && parsed && "detail" in parsed) {
      const detail = (parsed as Record<string, unknown>).detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (
        detail &&
        typeof detail === "object" &&
        "message" in (detail as Record<string, unknown>)
      ) {
        // Field-level error envelope (e.g. /auth/change-password
        // returns {detail: {field, message}}).
        message = String(
          (detail as Record<string, unknown>).message,
        );
      }
    }
    throw new ApiError(resp.status, message, parsed);
  }
  return parsed as T;
}


// CSV downloads can't ride a plain <a href download> because the
// browser doesn't attach ``credentials`` on a top-level navigation
// the way it does on a fetch. Instead, fetch the bytes with the
// cookie attached (credentials: "include"), turn the response into
// a Blob, and trigger a download with a synthetic anchor click.
// Memory-bound, but report CSVs are tiny.
export async function downloadCsv(
  path: string,
  filename: string,
): Promise<void> {
  const tryFetch = () => fetch(path, { credentials: "include" });
  let resp = await tryFetch();
  if (resp.status === 401) {
    // Same silent-refresh dance as `api()`.
    const refreshed = await _silentRefresh();
    if (refreshed) {
      resp = await tryFetch();
    } else {
      _bounceToLogin();
    }
  }
  if (!resp.ok) {
    let body: unknown;
    try { body = await resp.json(); } catch { body = null; }
    throw new ApiError(
      resp.status, `CSV download failed (${resp.status})`, body,
    );
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Defer revoke so the browser has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
