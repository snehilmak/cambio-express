// Tiny API client used by every SPA fetch. Wraps `fetch` so:
//   • the bearer JWT (if present) is added to every request
//   • a 401 response clears the token and triggers a redirect to
//     /app/login (saves callers from threading auth-state errors
//     through every component)
//   • non-2xx becomes a thrown ApiError with the parsed body
//   • JSON request bodies get the right Content-Type
//
// We intentionally don't import any HTTP library — `fetch` is
// browser-native, smaller bundle, and good enough for the SPA's
// needs. TanStack Query handles caching/retries on top.

import { clearAccessToken, getAccessToken } from "./auth";

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

export async function api<T = unknown>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const init: RequestInit = { ...options, headers };
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(options.json);
  }

  const resp = await fetch(path, init);
  const ct = resp.headers.get("content-type") ?? "";
  const parsed = ct.includes("application/json")
    ? await resp.json()
    : await resp.text();

  if (!resp.ok) {
    if (resp.status === 401) {
      // Token is expired or invalid. Drop it so the next paint
      // sees an unauthed identity and bounces the user to login.
      clearAccessToken();
      // Hard navigation to avoid a stale React tree referencing
      // the cleared token. Skip the redirect when we're already
      // on /app/login (e.g. a bad-creds POST shouldn't reload).
      const onLogin = window.location.pathname === "/app/login";
      if (!onLogin) window.location.assign("/app/login");
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
// browser won't attach our Authorization header on a top-level
// navigation. Instead, fetch the bytes with the bearer token,
// turn the response into a Blob, and trigger a download with a
// synthetic anchor click. Memory-bound, but report CSVs are tiny.
export async function downloadCsv(
  path: string,
  filename: string,
): Promise<void> {
  const headers = new Headers();
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const resp = await fetch(path, { headers });
  if (!resp.ok) {
    if (resp.status === 401) {
      clearAccessToken();
      const onLogin = window.location.pathname === "/app/login";
      if (!onLogin) window.location.assign("/app/login");
    }
    let body: unknown = null;
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
