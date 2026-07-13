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

Resolution order in `_resolve_grants(role, store_id)`:
1. Per-store rules (domain matches) → use exclusively
2. Global rules (domain = "global") → fallback
3. `RBAC_DEFAULTS` hardcoded → boot-time/Casbin-down fallback

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
