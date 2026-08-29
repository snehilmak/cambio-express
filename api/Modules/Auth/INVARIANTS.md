# Auth — Invariants

> **Read this before editing anything in `api/Modules/Auth/`,
> `api/Core/PasswordHash.py`, or any frontend file under
> `frontend/src/api/auth.ts` / `frontend/src/lib/auth.ts` /
> `frontend/src/routes/Login*.tsx`.**
>
> Auth is the highest-risk surface in the codebase. A regression
> here is not a P&L drift you can correct on Monday — it's an
> open door. Casual edits to "simplify" the login flow can
> silently turn a mandatory-2FA role into a 1-factor account, or
> let a pending-token-holder access a JWT-gated endpoint, or
> leak "user exists but disabled" via a different error string.
>
> Every rule below is enforced by tests in
> `tests/Modules/Auth/`. Breaking one of these invariants will
> break a test. If you find yourself needing to break a rule,
> the change deserves its own design discussion + a separate
> PR — don't sneak it in as a "small fix".


## What this module is

Owns user authentication end-to-end:

- Password login (per-store + cross-store)
- 2FA (TOTP enrollment + verification + recovery codes)
- Passkey registration + management (NOT yet used for login —
  see "Passkey carve-out — forward invariant" below)
- Password reset (email + token + Render-shell recovery for
  superadmin)
- JWT issuance + verification
- Session activity tracking
- Profile + notification preferences

The DB is the trust boundary. Password hashes, TOTP secrets,
recovery-code hashes, and passkey public keys all live in DB
columns; we treat the rest of the stack as untrusted input.


## Data model

| Table | What it holds |
|---|---|
| `user` | `username`, `password_hash` (scrypt), `role`, `store_id`, `is_active`, `totp_secret` (base32 plaintext), `totp_enrolled_at`, `full_name`, `theme_preference`, notification preferences |
| `recovery_code` | One row per unused / used recovery code. `code_hash` = sha256 of normalised raw code; `used_at` = NULL until consumed. |
| `passkey` | `(user_id, credential_id, public_key, sign_count, aaguid, name)`. `credential_id` is unique across the table. |
| `password_reset_token` | `token_hash` = sha256(raw token), 1-hour expiry, single-use (`used_at` set after consumption). |
| `login_event` | Audit row per login attempt: timestamp, user_id (when known), username (raw input), succeeded, ip, user_agent. |


## The role / permissions matrix

Permissions live in **Casbin** (migrated from custom tables in
PR #761; legacy tables dropped in PR #763). The single source
of truth has two layers:

1. **`api/Core/Permissions/__init__.py`** holds the constants —
   `RBAC_RESOURCES`, `RBAC_ACTIONS`, `RBAC_DEFAULTS` (per-role
   defaults seeded into Casbin on first boot), and
   `LEGACY_ROLE_PERMISSIONS` (coarse-grained legacy claims
   still emitted in JWTs for backward compat):

   ```python
   "superadmin": ["platform.admin", "store.admin", "store.employee", "owner.read"]
   "support":    ["platform.support"]
   "owner":      ["owner.read", "owner.admin"]
   "admin":      ["store.admin", "store.employee"]
   "employee":   ["store.employee"]
   ```

2. **`casbin_rule` table** holds the live, editable policy
   rows — `(role, domain, resource, action)`. The domain is
   ``"global"`` for default rules and ``str(store_id)`` for
   per-store overrides. Superadmin / admin / owner edit these
   via the per-store-permissions UI; live enforcement reads them
   on every request (no JWT-staleness anymore).

Resolution order (R-1 added the per-USER layer on top):
1. **Per-user overlay** — rows whose subject is `user:<id>` in
   the store's domain (written by `set_user_permissions`, read
   in `resolve_user_grants(user_id, role, store_id)`). Same
   per-resource mention semantics as the store layer: user rows
   govern only the resources they mention (`__none__` = all
   actions off); unmentioned resources fall through to the
   role's resolved grants. **This is a SECURITY boundary** —
   unlike `User.module_access`, which only hides nav (UX). The
   "custom access" user (e.g. HR + money services but no
   financials) is expressed here.
2. Per-store role rules (domain matches) → **per-resource
   overlay**: they govern only the resources they mention. A
   save writes every CURRENT resource explicitly — grant rows,
   or a `__none__` marker row when all of a resource's actions
   are off — so "explicitly off" is distinguishable from
   "resource didn't exist when this matrix was saved".
3. Global rules (domain = "global") → fallback for resources the
   store overlay never mentions. **This is what lets a NEW
   platform resource (lottery, day_close, catalog…) reach stores
   whose matrix predates it** — the old wholesale-replacement
   semantics froze such stores out of every later resource (the
   "admin can't see new modules" bug).
4. `RBAC_DEFAULTS` hardcoded → boot-time/Casbin-down fallback

Per-user overlay contract (R-1):
- `principal.has_permission` threads `claims["sub"]` into
  `check_permission(..., user_id=…)`, so overlays are enforced
  LIVE on every request — not only baked into the token.
- JWT baking passes `user_id` at login, refresh, and signup
  (`permissions_for(role, store_id=…, user_id=…)`), so a
  restricted user's `perms` claim never exceeds their overlay.
- **Owner switch-store tokens deliberately skip the overlay**
  (`permissions_for("admin", store_id=…)`, role-only): owners
  entering their own store are never restricted, and no code
  path writes overlay rows for owner user ids.
- Every overlay write (`PUT`/`DELETE /admin/users/{id}/
  permissions`) must: 404 opaquely cross-store, refuse
  self-edit, write an audit entry, and call
  `invalidate_sessions_for_user` so tokens carrying the old
  perms die immediately.
- Dashboard summary blocks are permission-gated per resource
  (`_admin_summary` / `_employee_summary`) — an overlay that
  denies e.g. `day_close.read` removes the numbers from the
  landing payload itself, not just the UI.

Legacy compatibility: a lone `__override_active__` sentinel row
(the old all-off save format) still means zero access; old
partial snapshots have no markers, so their switched-off
resources fall back to global once and re-freeze on next save.

**Defensive fallback (PR #768):** if Casbin throws (DB hiccup,
adapter fault) both `permissions_for` and `check_permission`
catch the exception and return `RBAC_DEFAULTS` for the role.
Login never 500s on a permissions-system fault.

Unknown roles get `[]` — defensive against future role tiers
that aren't in the matrix yet.

**Changing the defaults or adding new resources/actions is a
security-sensitive change.** Open a PR that's explicit about
what's moving and why.


## The 2FA gate — `needs_totp` is THE single role check

```python
# api/Modules/Auth/Services/totp.py
_TOTP_REQUIRED_ROLES = ("superadmin",)

def needs_totp(user: User | None) -> bool:
    return bool(user and user.role in _TOTP_REQUIRED_ROLES)
```

**Every login path consults this predicate.** Do NOT scatter
role checks ("if user.role == 'superadmin' …") through the
login routes — funnel everything through `needs_totp`. If you
need to extend 2FA to another role (e.g. owner), change THIS
tuple and only this tuple.

The current set is `("superadmin",)` — pinned by
`test_totp_required_roles_is_superadmin_only` in
`test_auth_invariants.py`.

**The `support` platform role is deliberately NOT in this
tuple** (product decision, Aug 2026): support logins are
password-only, and the trade-off is a HARD 7-day login window —
`refresh_ttl_for_role("support")` issues the refresh chain with
a 7-day TTL, and `reuse()` never extends `expires_at`, so the
session dies 7 days after login no matter how active it is
(everyone else gets the 14-day default). See
`api/Modules/Auth/Services/refresh.py`.


## The `support` platform role — tickets-only scope

A store-less (`store_id IS NULL`) platform login minted ONLY by
`POST /superadmin/platform-users` (superadmin-gated, audited).
Scope rules, all pinned by `tests/Modules/Support/
test_support_role.py`:

- Passes `PLATFORM_STAFF_ROLES` in the **Support module only**
  (full cross-store ticket access, "staff" chat bubbles, the
  superadmin audit sink for per-person attribution, ticket
  claim/release).
- **Never** passes `_require_superadmin` /
  `resolve_superadmin_user`, and is **never** added to the
  Casbin superadmin bypasses in `check_permission` /
  `require_permission` / `permissions_for`.
- Usernames are globally unique across the platform — the
  cross-store login lookup is first-match-by-username, so a
  collision would shadow an account.
- `change-role` refuses support targets (a store role needs a
  `store_id` the row doesn't have). Deactivate + recreate
  instead.


## The login flow — what's actually wired today

The SPA's login flow lives entirely in the FastAPI routes under
`/api/v2/auth/login*`. There is NO Flask login surface anymore;
the legacy `/login/passkey/finish` referenced in older
documentation does NOT exist in the codebase today (see
"Passkey carve-out" below for the forward invariant).

### The shapes returned by `authenticate_password`

```python
LoginResult         # → 200, payload includes access_token (JWT)
LoginPendingResult  # → 200, payload includes pending_token + 2FA fields
                    #         (NOT a real access token — purpose-bound)
```

Plus three exception types:

```python
AuthenticationError          # → 401, opaque "Invalid username or password"
TotpEnrollmentRequired       # → 200 with enroll_required=True
                             #    (subtype of LoginPendingResult path —
                             #    superadmin with no totp_secret yet)
```

### Opaque-error-message rule (anti-enumeration)

`AuthenticationError` is raised with the SAME message for ALL
of these failure modes:

- Unknown username
- Wrong password
- Disabled user (`is_active=False`)

**Never split the message** to indicate which condition failed.
Doing so leaks account existence + status, defeating the
opacity. Pinned by `test_auth_errors_are_opaque`.

### The pending-token contract

`LoginPendingResult.pending_token` is a JWT issued by
`issue_pending_2fa_token(user.id)`:

- `purpose: "totp-pending"` claim
- 5-minute expiry
- Can ONLY be presented to `/auth/login/totp`,
  `/auth/login/recovery`, or `/auth/login/totp/enroll/*`
- Cannot be used as a full access token (purpose claim
  prevents it — JWT verifier rejects)

The full access token, by contrast:

- `purpose: "access"` (implicit / no purpose claim — different
  from pending)
- Cannot be presented to `/auth/login/totp` as the pending
  token slot — purpose mismatch rejects.

Pinned by `test_login_totp_rejects_access_token_used_as_pending`
and `test_pending_token_rejected_by_authed_endpoint` in
`test_login_totp_flow.py`.

### Cross-store login + employee carve-out

`/auth/login` accepts a `store_id` (per-store) or no
`store_id` (cross-store; picks first matching username across
all stores). The cross-store path **rejects employees** because
the legacy flow did — employees must use their store's slug-
scoped page. Pinned by `test_login_cross_store_*` and
`test_verify_password_cross_store_*` in `test_login_service.py`.


### Owner store-switching (`/auth/switch-store`) — derived tokens

The single-dashboard principle (owner directive, 2026-08-27): an
owner ENTERS a store and sees exactly the same store view as the
users they create. `/auth/switch-store` implements it by minting
a **store-scoped admin token** for the selected store. Rules:

- The derived token is minted ONLY from an already-full access
  token (`get_principal` refuses pending/`purpose` tokens) whose
  subject is an **active `role=owner` user**; the target store
  must be in the owner's umbrella (`StoreOwnerLink` rows ∪ the
  owner's own home `store_id`) and active. This is NOT a
  privilege escalation: the owner owns the store.
- The derived token carries `role=admin`, `store_id=<target>`,
  the admin permission set for that store, `sub=<owner user id>`
  (audit rows attribute to the owner), and an **`owner_id` claim**
  marking it owner-context — the SPA keeps offering the switcher,
  and `/auth/switch-store` accepts re-switching from it.
- `issue_access_token(extra=…)` merges auxiliary claims but can
  NEVER override reserved claims (`sub`/`role`/`store_id`/
  `perms`/`exp`/…) or set `purpose`.
- Every switch writes an `owner_enter_store` operator-audit row
  at the target store.
- Refresh re-mints from the User row (base owner token) — the SPA
  re-enters the remembered store after refresh; the server never
  persists switch state.
- **Post-login auto-enter (U-4a) is purely client-side.** After an
  owner login the SPA calls `/auth/my-stores` and then the normal
  `/auth/switch-store` (remembered store → `is_home` store → first
  store) so the owner lands on the same store dashboard their team
  sees. No new token path exists for this — `is_home` on the
  my-stores row is data only, and an owner with zero active stores
  simply stays on the base owner token (owner overview).


## TOTP enrollment + verification

For roles where `needs_totp(user)` is True:

1. **First login** → `LoginPendingResult(enroll_required=True)`.
   SPA renders the QR/secret page.
2. `/auth/login/totp/enroll/start` mints `user.totp_secret`
   (base32, 32 chars from `pyotp.random_base32()`). Idempotent
   — refreshes return the same secret until the user finishes
   enrollment.
3. `/auth/login/totp/enroll/finish` verifies the user's first
   6-digit code, sets `user.totp_enrolled_at`, mints **10
   one-shot recovery codes** (`generate_recovery_codes`).
   The plaintext codes are returned to the SPA exactly once
   — they're never retrievable later.
4. `/auth/login/totp/enroll/confirm` flips the pending token
   for a real access token after the user confirms they've
   saved the codes.

**Subsequent logins**: pending token → `/auth/login/totp` with
the 6-digit code → real access token.

**Lost the codes**: `/auth/login/recovery` with one of the 10
codes. The code is consumed (`used_at` set) on success — they
are single-use.

### Recovery codes

- `RECOVERY_CODES_PER_USER = 10` (constant in `totp.py`)
- Stored as `sha256(normalised(raw))` — normalisation strips
  whitespace, hyphens, and uppercases. Pasting `abcd-efgh` or
  `ABCDEFGH` or ` abcd efgh ` all match the same stored hash.
- Single-use: `consume_recovery_code` sets `used_at` and the
  filter excludes used rows. Pinned by
  `test_login_recovery_code_is_single_use`.
- Re-enrollment wipes all existing codes for the user before
  minting fresh ones (`generate_recovery_codes` deletes
  first). The user is expected to discard the old printed
  sheet.

### TOTP verification window

`TOTP_VALID_WINDOW = 1` — accepts the current 30-second step
plus the immediate prev / next step (±30s). Forgives slow
phone clocks + network latency without enabling brute-force.

### Superadmin TOTP escape hatch

If a superadmin loses their authenticator AND their recovery
codes, the email-based reset is deliberately disabled (see
"Password reset" below). Recovery is the Render shell command:

```bash
python -m scripts.reset_superadmin                 # password only
python -m scripts.reset_superadmin --reset-2fa     # password + wipe TOTP
```

(The legacy `flask reset-superadmin` CLI was removed with Flask in
PR #550 — `scripts/reset_superadmin.py` is the standalone replacement.)

The `--reset-2fa` flag clears `totp_secret` + `totp_enrolled_at`
so the next login goes through enrollment again.


## Passkey carve-out — forward invariant

> ⚠️ **The passkey-bypasses-TOTP-at-login rule documented in
> CLAUDE.md invariant #13 describes a FORWARD invariant for a
> flow that does NOT exist in the codebase today.** The legacy
> Flask `/login/passkey/finish` endpoint was removed when Flask
> was removed (PR #550); a SPA equivalent has not been built.
> When/if that endpoint lands, it MUST follow the rules below.

### What IS active today

Passkeys are a *registered factor* on the user account, not a
login factor. The active endpoints are:

- `POST /api/v2/auth/passkeys/register/{begin,finish}` —
  SPA settings page enrolls a new passkey on the logged-in
  user.
- `GET /api/v2/auth/passkeys` — list the user's registered
  passkeys (metadata only — never the raw credential_id or
  public_key).
- `DELETE /api/v2/auth/passkeys/{id}` — remove a passkey
  (scoped to the authenticated user).

The TimeClock module has its own passkey assertion flow for
cashier clock-in/clock-out, which is a separate surface and
does NOT bridge to user authentication.

### TOTP-first rule on registration

Passkey registration for a TOTP-required role REQUIRES that
the user has already enrolled TOTP:

```python
# api/Modules/Auth/Controllers/__init__.py :: passkey_register_begin_route
if needs_totp(user) and not is_enrolled(user):
    raise HTTPException(403, "Enroll TOTP before adding a passkey.")
```

This guarantees the user always has a non-passkey backup factor
in case the passkey device is lost. Pinned by
`test_passkey_register_begin_rejects_unenrolled_superadmin`.

### Forward invariant — when passkey login lands

If a passkey-LOGIN flow is ever added to the FastAPI side, it
MUST follow these rules:

1. **Passkey verification is phishing-resistant MFA by
   construction.** A successful WebAuthn assertion satisfies
   the same security goal as TOTP — device-bound +
   user-presence-proven + rpId-bound. Stacking TOTP on top of
   passkey adds friction without adding security.
2. The single rule: **full-auth promotion (issuing an access
   token) requires EITHER a TOTP factor verified OR a passkey
   assertion verified.** No third condition. No alternative
   path that sets `user_id` (or its JWT equivalent) without
   one of these.
3. `sign_count` from the authenticator must be greater than or
   equal to the stored value. Equal accepts clones poorly;
   strictly greater is the textbook rule. We deliberately
   accept equal because some real authenticators are buggy
   and don't increment monotonically — clones would still get
   caught by the next login.
4. The rpId at verification time must equal the rpId at
   registration time. **Changing `WEBAUTHN_RP_ID` invalidates
   every existing passkey** — they're bound to the rpId that
   was active at registration.

### `WEBAUTHN_RP_ID` configuration

- Prod: `dinerobook.com` (set via env var on Render)
- Dev: falls back to `request.host` with the port stripped
  (`localhost:5000` → `localhost`)

The fallback exists ONLY so `localhost` works out of the box.
Production MUST set the env var explicitly — if it ever falls
back in prod, every user gets a fresh enrollment prompt
because the rpId silently switched.


## Password reset

- `/auth/password-reset/request` — accepts an email, **always
  responds with "Check your email"** whether the account
  exists or not (anti-enumeration). When the account exists
  and is reset-eligible, a token email is sent.
- `/auth/password-reset/confirm` — accepts the raw token +
  new password. The DB stores `sha256(raw)` — the raw token
  never hits the DB or the logs (except on SMTP fallback,
  where ONLY the URL is logged for debugging).
- Tokens are 1-hour, single-use (`used_at` set after
  consumption).
- **Superadmin is deliberately excluded.** An attacker who
  compromises the superadmin mailbox would bypass 2FA via the
  email reset. Recovery goes through
  `python -m scripts.reset_superadmin` on the Render shell instead.


## Rate limiting

Every auth endpoint (`/login*`, `/password-reset/*`,
`/passkeys/register/*`) is bucketed by slowapi. The shared
singleton is `slow_limiter` in `api/Core/RateLimit.py`. See
CLAUDE.md invariant #15 for storage backend + test-disable
semantics.

Loosening limits is safer than tightening — the integration
tests and Stripe webhook retries both burn rate budget.


## What's safe to change

- Adding a new permission to an existing role's defaults in
  `RBAC_DEFAULTS` (after a security review) — note that the
  change only affects new stores / users who haven't customized
  their override matrix; existing per-store overrides keep
  their explicit grant set.
- Adding new account-management endpoints behind
  `get_principal` (e.g. update full_name) — `require_permission`
  (Casbin-backed) handles authorization.
- Changing the recovery-code formatting / display.
- Adding a passkey-LOGIN flow — see "Forward invariant" above
  for the rules it must follow.

What needs a security discussion FIRST:

- Adding a new role to `_TOTP_REQUIRED_ROLES`.
- Removing the opaque-error-message rule.
- Splitting login by `is_active` vs unknown-user vs
  bad-password (any of these leaks account existence).
- Changing the `purpose` claim semantics on the pending vs
  access tokens.
- Adding a new auth path that issues an access token (must
  follow the existing 2FA gate + same opaque-error contract).
- Touching the password-reset email gating (superadmin
  exclusion + always-200 response).
- Changing `WEBAUTHN_RP_ID` or `TOTP_VALID_WINDOW`.
- Renaming or removing any column on `User` / `RecoveryCode`
  / `Passkey` — there's no migration path that doesn't lose
  data here.


## Test surface

`tests/Modules/Auth/` covers:

- `test_login_service.py` — `authenticate_password`,
  `authenticate_password_cross_store`,
  `verify_password_cross_store`, the permissions matrix.
- `test_login_totp_flow.py` — pending-token issuance,
  enroll-start / enroll-finish / enroll-confirm,
  TOTP verify, recovery-code verify, single-use enforcement,
  the access-token-vs-pending-token purpose separation.
- `test_totp_service.py` — `needs_totp` per role,
  `is_enrolled`, `verify_totp_token`, recovery-code minting +
  hashing + consumption.
- `test_passkey_endpoints.py` — list / delete CRUD,
  cross-user isolation, no-leak of credential_id / public_key.
- `test_passkey_service.py` — `rp_id` / `origin` /
  `exclude_credentials` / `is_eligible`.
- `test_password_reset_service.py` — token hashing, expiry,
  single-use.
- `test_password_change_service.py` — current-password verify,
  new-password hashing.
- `test_jwt_issuer.py` — claims shape, expiry, decode.
- `test_auth_repository.py` — `find_user_by_username`,
  `find_user_by_username_in_store`.
- `test_sessions_endpoint.py` + `test_sessions_service.py` —
  active-session listing + revocation.
- `test_auth_invariants.py` — focused regression sweep
  pinning the rules in this doc that weren't otherwise tested
  end-to-end (role tuple, opaque errors, passkey-register
  TOTP-first, permissions matrix).

Before changing this module, run:

```bash
pytest tests/Modules/Auth/ -v
```

If any test fails, you've broken an invariant. Either:
1. Your change is wrong — fix it.
2. The invariant has genuinely changed (security-sensitive) —
   update the test AND this document AND open a PR that's
   EXPLICIT about the contract change. Auth changes deserve
   an explicit review header in the PR description.
