# ADR-002 — JWT-only auth (retire Flask cookie sessions)

> **Status:** PROPOSED.
> **Last updated:** 2026-05-11
> **Authors:** Claude (drafting).
> **Tracked by:** BACKLOG.md item D3.
> **Depends on:** ADR-001 (SPA migration shipped).

## Context

Today the product runs two auth transports in parallel:

1. **Flask cookie session** — set by `/login`, `/login/2fa/verify`,
   `/login/passkey/finish`. Used by the legacy Flask routes that
   still serve form-POST mutations (some drill-into-Stripe webhook
   flows, the `/tv/*` kiosk, a handful of admin settings endpoints
   that never got a FastAPI counterpart).
2. **JWT in `localStorage`** — issued by `/api/v2/auth/login` and the
   2FA finalizers. The SPA reads it from localStorage and sends it
   in the `Authorization: Bearer …` header on every `/api/v2/*` call.

`/api/v2/*` accepts **both** — there's a dual-auth dependency in
`api/Modules/Auth/Services/` that resolves to a `User` from either
transport. That was the right call during the SPA migration window
(ADR-001) because Flask routes were redirecting to SPA routes, and a
redirect from a logged-in Flask page needed to land the user on a
logged-in SPA page without re-authenticating.

That window has now closed. After ADR-001 every authenticated user
session originates in the SPA. The cookie transport survives only as
a side effect of the legacy login routes still issuing them, and a
small number of legacy Flask mutate endpoints still reading them.

Maintaining two transports has real costs:

- **Two CSRF stories.** Cookie auth needs CSRF tokens on every form-
  POST; JWT in Authorization headers doesn't. The current code base
  has CSRF enforcement on the Flask side and none on FastAPI — fine
  because the two surfaces don't overlap, but easy to get wrong if
  someone adds a Flask route that mirrors a FastAPI endpoint.
- **Two logout paths.** "Log out" has to clear the cookie *and* the
  localStorage token; the current SPA does both, but a bug here
  silently keeps a stale session alive.
- **Two MFA finalizers.** Every passkey / TOTP / recovery-code flow
  has to know which transport it's issuing — duplicate code in
  `app.py` and `api/Modules/Auth/Services/login_service.py`.
- **localStorage is XSS-fragile.** A successful XSS on any page can
  exfiltrate the JWT. HttpOnly cookies block that. MIGRATION_ADR.md
  §6 prescribed HttpOnly cookies; we shipped localStorage to keep
  ADR-001 moving.

## Decision

**Move to a single auth transport: a JWT in an HttpOnly, Secure,
SameSite=Lax cookie**, issued exclusively by FastAPI. Retire the
Flask cookie session entirely.

Concretely:

- The login finalizers (`/api/v2/auth/login`, `/api/v2/auth/2fa/
  verify`, `/api/v2/auth/passkey/finish`) issue a JWT and Set-Cookie
  it as `db_session` (or similar) with `HttpOnly; Secure;
  SameSite=Lax; Path=/`.
- The SPA stops touching `localStorage` for the access token. It
  relies on the browser to attach the cookie automatically.
- `/api/v2/*` reads the JWT from the cookie (and accepts the
  `Authorization` header as a fallback for non-browser clients —
  CLI tools, future mobile, etc.).
- Flask's `@login_required` is rewritten to validate the same JWT
  (calling into the same `Auth/Services/decode_token` function). The
  Flask-Login session object disappears.
- The handful of Flask form-POST endpoints that survived ADR-001
  either (a) get a FastAPI counterpart and the Flask version becomes
  a 301, or (b) keep the Flask handler but switch to JWT validation.
  We pick path (a) wherever the SPA can issue the request directly.

## Consequences

What gets simpler:

- **One login flow.** Password + 2FA / passkey → JWT cookie → done.
- **CSRF is uniform.** SameSite=Lax + a per-request CSRF token on
  state-changing endpoints (FastAPI dependency). No double standard.
- **Logout is one Set-Cookie with an expired date** plus a JWT
  revocation (jti to a small Redis/DB blacklist, per
  MIGRATION_ADR.md §6 Q2).
- **No XSS-exfiltratable access token.** Cookies are HttpOnly.

What gets harder:

- **CORS isn't relevant today** (SPA + API on the same origin), but
  if we ever split them onto different domains we have to set
  `SameSite=None; Secure` and re-add explicit CORS allow-list. Not
  in scope for this ADR.
- **Refresh-token rotation.** With 30-min access TTL (per
  MIGRATION_ADR.md §6 Q2) we need a refresh-token endpoint that
  re-issues the access cookie. Plan: a second HttpOnly cookie
  `db_refresh` with a longer TTL (14 days), rotated on every
  refresh, single-use, server-side jti tracking.
- **localStorage migration window.** SPA bundles in the wild may
  still try to send `Authorization: Bearer …` from localStorage.
  Plan: keep the header path supported for a release; the cookie
  takes precedence when both are present. Once one full release
  cycle passes, drop the header path.

What we accept:

- **A small server-side state surface** (jti blacklist + refresh-
  token tracking). Pure stateless JWT is appealing in theory but
  fails on revocation. The amount of state is tiny — one row per
  active session.
- **Slight extra request weight** because the cookie travels on
  every request (including static assets under the SPA bundle path).
  We mitigate by setting `Path=/api` so only API requests carry it,
  unless the Flask side still needs it (it does, until D1+D3 cleanup
  finishes — see Implementation).

## Alternatives

| Option | Why we didn't pick it |
|---|---|
| Keep localStorage JWT, harden everything else | Doesn't solve XSS exfiltration. MIGRATION_ADR.md §6 already committed to cookie storage. |
| Keep Flask sessions, drop JWT | Goes the wrong direction. JWT is the long-term plan (`/api/v2/*` is the customer-facing API surface). Customer-deployable backends (MIGRATION_ADR.md §3) need a stateless-by-default option. |
| OAuth2 with an external IdP (Auth0, Clerk, etc.) | Useful long-term for SSO / customer-managed identity. Not the right scope for this ADR — orthogonal to "retire the duplicate transport". |
| Pure stateless JWT (no jti blacklist) | Loses the ability to revoke a stolen token before TTL. MIGRATION_ADR.md §6 Q2 already committed to a blacklist. |

## Implementation

Suggested PR sequence. Each step ships independently.

1. **Add cookie-based JWT issuance.** `/api/v2/auth/login` and the
   2FA finalizers begin Set-Cookie'ing the access token *in addition
   to* returning it in the response body. SPA still reads from the
   body. Zero user-facing change.
2. **Switch SPA to cookie path.** The TanStack Query `api()` wrapper
   in `frontend/src/lib/api.ts` stops reading from localStorage; the
   browser attaches the cookie. Login response body still returns
   the JWT for now (one release of overlap).
3. **Refresh endpoint** `/api/v2/auth/refresh`. Reads
   `db_refresh` cookie, rotates it, re-issues access cookie.
   TanStack Query handles 401 by calling refresh and retrying once.
4. **Rewrite Flask `@login_required`** to validate the JWT cookie.
   `session["user_id"]` reads become "decode JWT, return user_id."
   Login routes on the Flask side delete `session["user_id"]`-setting
   code; cookie session goes away.
5. **Convert surviving Flask form-POST handlers** to FastAPI
   counterparts (or, where the SPA can issue the request directly,
   delete the Flask handler entirely). This is the same audit that
   D3 in the BACKLOG calls for; it should ship with this ADR rather
   than separately.
6. **Drop localStorage path entirely** from the SPA. Drop the
   `Authorization` header acceptance from `/api/v2/*` (or leave it,
   gated to non-browser clients via a config flag — TBD).
7. **Revocation surface** — small `revoked_jtis` table or a Redis
   set. Hooked into password-change, account-lock, and "log out
   everywhere" flows.

Out of scope here, will be follow-up ADRs:

- IP / device fingerprint binding on refresh tokens (security
  hardening — separate ADR if we do it).
- Per-tenant key rotation (irrelevant until single-tenant
  deployments ship).

## Open questions

- **Cookie Path scope** — `/` vs. `/api` while the Flask side still
  reads the same cookie. Probably `/` until D1+D3 cleanup finishes,
  then narrow to `/api`. Not a blocker for accepting this ADR.
- **Idle-session timeout vs. absolute timeout.** 30-min access /
  14-day refresh feels right for an internal-tool product; SaaS
  norms are 30-min / 30-day. Defer to the security review on the
  PR that ships step 1.

## Changelog

- **2026-05-11** — Initial draft, status PROPOSED.
