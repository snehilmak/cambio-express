# DineroBook — Engineering Context

> This file is read automatically by Claude Code at the start of every
> session. Keep it short, accurate, and update it whenever an invariant
> changes. The goal is **no quiet regressions** on the rules below.

## What this is
A multi-tenant bookkeeping SaaS for money-service businesses (MSBs —
small shops that send remittances via Intermex / Maxi / Barri and keep
daily cash-ledger + monthly P&L). Each **Store** has admins + employees;
multi-store **Owners** connect via invite codes; the platform runs under
one **Superadmin**.

## Stack
- FastAPI / Starlette on ASGI (uvicorn). Flask was removed in
  PR #550 — `app.py`, `blueprints/`, and `api/Flask/` no longer
  exist; `asgi.py` is the single entry point. Every route lives
  under `api/Modules/<domain>/Controllers/` and the SPA shell
  serves from `api/spa.py`.
- SQLAlchemy 3.1, SQLite in dev, Postgres in prod.
- Alembic is the sole source of schema truth (see "Migrations").
- Jinja2 templates + a 3-layer stylesheet split:
  - `static/design-tokens.css` — dark+neon tokens (`--db-*`) + legacy aliases.
  - `static/content.css` — overrides for every legacy content class
    (cards, stats, tables, forms, badges, banners, buttons).
  - `static/shell.css` — sidebar + topbar overrides.
  - `static/app.css` — legacy stylesheet, still loaded for layout
    utilities and dark-mode semantic tokens (`--surface`, `--text`,
    `--border`). The navy/gold/cream palette it originally shipped
    is retired but its dark-mode block is still in use.
- Stripe for billing (Checkout Sessions + Billing Portal + webhooks).
- Casbin (`pycasbin` + `casbin-sqlalchemy-adapter`) for RBAC.
  Replaced custom `RolePermission` / `StoreRoleOverride` tables in
  PR #761; legacy tables dropped in PR #763. Live enforcement
  (no JWT staleness) — see `api/Core/Permissions/`.
- pytest for the Python suite; Vitest + Testing Library for the SPA.

## Design system — READ BEFORE TOUCHING ANY UI
**Source of truth: [`docs/design-system/`](docs/design-system/).** Any
visual/UX change — new page, new component, restyle — starts there.
The bundle was exported from `claude.ai/design` and captures the
**dark-first, Robinhood-inspired** direction (near-black surfaces,
single neon-green `#3fff00` accent, Space Grotesk + Inter +
JetBrains Mono, inline stroke SVG nav icons).

Non-negotiables:
- **Dark by default; light is opt-in.** ``data-theme`` flips
  between ``"dark"`` (default) and ``"light"`` (per-user
  preference, stored on ``User.theme_preference``). The light
  palette deliberately darkens the neon accent so links + active
  nav stay readable on white. New surfaces must work in BOTH
  themes — use semantic tokens (``--db-surface``, ``--db-text``,
  ``--db-border``) instead of fixed hex so values flip with the
  theme attribute. The toggle lives in the topbar
  (``ThemeToggle.tsx``); the per-device cache + before-paint
  restore live in ``frontend/src/lib/theme.ts`` +
  ``frontend/index.html``.
- **One saturated color.** Neon green `#3fff00` — reserved for CTAs,
  positive values, active nav indicators, primary chart strokes.
  Second accents = jewel tones (`--db-co-intermex/maxi/barri`) or
  state (`--db-info/warning/negative`). **Never** introduce another
  brand color.
- **Token hierarchy.** Prefer `--db-*` tokens from
  `static/design-tokens.css`. If you need something not in the palette,
  add it there with a comment, don't inline hex. Legacy `--sky/--gold/
  --navy/--blue` are aliased to neon/near-black — they still work but
  prefer `--db-*` for new code.
- **Three fonts only.** Space Grotesk (display), Inter (body),
  JetBrains Mono (money/dates/IDs). No other faces.
- **Component reuse.** Check
  `docs/design-system/project/ui_kits/{marketing,admin_app,auth}/`
  for the closest existing pattern before hand-rolling. The mapping
  between kit components and live code lives in
  `docs/design-system/README.md`. Code-level primitives live in
  `frontend/src/components/ui/index.tsx` — `PageShell`,
  `PageHeader`, `Section`, `Card`, `Field`, `Input`, `Select`,
  `Textarea`, `Button`, `ButtonLink`, `Alert`, `Pill`, `Pager`,
  `Table`, `EmptyState`, `ErrorState`, `KpiCard`, `KpiGrid`,
  `FormActions`, `RowActions`. Reach for these before writing
  inline styles.
- **Per-row actions** use `<RowActions>` — the kit primitive
  that renders inline buttons on desktop and collapses into a
  bottom-sheet menu on narrow viewports (`@media (max-width:
  36rem)`). The sheet renders through `createPortal` so
  `position: fixed` pins to the viewport (the `.ds-page`
  entry animation otherwise establishes a containing block
  and traps the sheet inside the page flow). Use this anywhere
  a table or list row has 2+ actions — keeps mobile UX
  consistent across the SPA. `AdminTimeClock.tsx` is the
  canonical example.
- **Inline styles vs CSS Modules.** New routes should reach for
  kit primitives first. Anything left over (page-specific layouts,
  one-off treatments) goes into a co-located `<Route>.module.css`
  file rather than `style={{ ... }}` constants at the bottom of
  the route. The canonical example post-migration is
  `frontend/src/routes/AdminUserForm.tsx` +
  `AdminUserForm.module.css` — every input/button/alert is a kit
  primitive; only the card header row + checkbox row are in the
  module. Vite's `vite/client` types already handle `.module.css`
  imports, no config change needed. Forms use `<Field error=...
  hint=...>` for field-level validation + inline help; server-
  level errors render through `<Alert tone="error">`.
- **Forms.** `react-hook-form` + `zod` is the standard stack
  (PR #562). One `useForm()` per page, schema co-located with
  the route. Plain inputs use `register("field")`; custom
  components (autocompletes, etc.) wrap in `<Controller>`.
  `useWatch({ control, name })` for fields the rest of the form
  shouldn't re-render against. The canonical example for the
  full layout-+-form stack is
  `frontend/src/routes/NewTransfer.tsx`.
- **Emoji is retired from nav.** Replace any new emoji nav icon with
  an inline stroke SVG matching the existing set
  (`stroke-width:2; stroke-linecap:round; fill:none; currentColor`).
  Emoji survives only in status/eyebrow prefixes (`⏳ ✅ 🔴 📣`) and
  the landing hero's `$` mark.
- **Motion is part of the design system.** Every interactive surface
  should transition between states — no instant pop-ins, no abrupt
  swaps. Cards lift on hover, buttons scale-press on click, inputs
  glow on focus, dropdowns + modals fade-scale on open, tab content
  slides in on swap, flash banners slide-down on mount, page
  navigations fade-up. Durations are tight (≤200ms) so the app
  feels responsive, not laggy.

  **When you build a new dropdown / modal / tab / popover:**
  - Reuse the existing patterns rather than inventing your own.
  - Dropdown / popover: server-render with `hidden`, JS toggles a
    `.is-open` class with a delayed `hidden` re-set after the
    transition. CSS animates `.is-open` (see `.user-dropdown` in
    `static/shell.css` for the canonical example).
  - Modal: `.modal-backdrop` + `.modal-card` + `.open` class. CSS
    keyframes in `static/content.css` (`db-modal-backdrop-in` /
    `db-modal-card-in`) handle the fade-scale. Just give the markup
    the right classes.
  - Tab bar (server-rendered, full reload per tab): use `.tab-bar` +
    `.tab-link` (in `static/content.css`). No per-template style
    duplication. The page-entrance animation handles the swap.
  - Tab bar (in-page JS swap): use the daily-book pattern — JS
    toggles a `.is-active` class on the visible panel, CSS animates
    via a `db-tab-swap` keyframe. Trigger `void el.offsetHeight`
    between class clear + add to re-fire the animation.
  - Honor `prefers-reduced-motion: reduce` — there's a global rule
    at the bottom of `static/content.css` that strips animations +
    transitions. Don't write inline `style="transition: …"` that
    bypasses it.

  **Don't:**
  - Use `display: none` ↔ `display: block` toggles without a
    bridging class — display can't transition.
  - Add long animations (>250ms) on workflow paths.
  - Animate properties that cause layout shift (height/width,
    margin) on elements above the user's reading position.

## Production deploy target (single source of truth)
- **Web service**: `dinerobook` on Render → `https://dinerobook.com` (custom domain; the underlying Render hostname `dinerobook.onrender.com` is no longer canonical)
- **Database**: `dinerobook-db` on Render (linked via `fromDatabase:` in `render.yaml`)
- The older `cashnet` service / `cambio-db` database are decommissioned.
  Never add references to them, never point env vars at them, never run
  migrations against them. If a new service is ever needed it must be
  declared in `render.yaml` and auto-deploy from `main`.

## Running locally
```bash
pip install -r requirements.txt
uvicorn asgi:asgi_app --reload --port 5000   # dev server on :5000
pytest tests/                                # full suite
python -m scripts.purge_expired_stores       # deletes inactive stores past retention
python -m scripts.send_trial_reminders       # daily cron — trial-ending emails
python -m scripts.send_daily_summaries       # daily cron — per-store close-out summary
python -m scripts.send_missed_shift_digest   # daily cron — missed planned shifts
python -m scripts.broadcast_announcement N   # resend announcement #N
python -m scripts.backfill_federal_tax       # one-shot — recompute Transfer.federal_tax
```
Set `DEV_RELOAD=1` for hot-reload on Python edits. The Vite dev
server (port 5173) handles SPA reload on its own.
First boot seeds a superadmin (`superadmin / super2025!`) and demo store
admin (`admin / cambio2025!`). Override via `SUPERADMIN_PASSWORD` /
`ADMIN_PASSWORD` env vars in prod.

Passkey env (optional): `WEBAUTHN_RP_ID` pins the WebAuthn Relying
Party ID in prod (set to `dinerobook.com`, the canonical custom
domain). Dev falls back to `request.host` with the port stripped,
so `localhost:5000` works out of the box. **Changing this value
invalidates every existing passkey** — they're bound to the rpId
that was active at registration time.

## Critical invariants — don't break these

### Per-module `INVARIANTS.md` — read these first

Money-flow modules carry a co-located `INVARIANTS.md` file that
captures the rules NOT obvious from the code (field categories,
locked-day semantics, math formulas, cross-module dependencies,
the 422-trap field list).

**Before editing a file in one of these modules, read the local
`INVARIANTS.md`:**

- `api/Modules/DailyBook/INVARIANTS.md` — daily ledger. Field
  categories (operator-editable / line-item-derived /
  cross-table-derived), lock rules, the 422 trap, the math
  formulas. `frontend/src/routes/EditDailyBook.tsx` +
  `frontend/src/api/dailybook.ts` count as "DailyBook files" too.
- `api/Modules/Transfers/INVARIANTS.md` — transfer ledger. The
  money math (`total_collected = send_amount + fee + federal_tax`),
  the server-computed federal-tax rule, the Customer upsert
  chain across the owner umbrella, status semantics, audit
  contract, employee attribution, cross-module dependencies
  (Batches / Monthly / DailyBook). `api/Modules/Customers/
  Services/customers.py` upsert + `frontend/src/routes/
  NewTransfer.tsx` + `EditTransfer.tsx` count as "Transfers
  files" too.
- `api/Modules/Monthly/INVARIANTS.md` — monthly P&L. Field
  categories (operator-editable / daily-derived /
  cross-table-derived), the 422 trap for every read-only field,
  the income / expense / net-profit formulas, the auto-derive
  contract ("trust the ledger, never the stored value"), and the
  `bank_charges_total` conditional-lock rule that Basic-plan
  stores depend on for manual entry.
  `frontend/src/routes/EditMonthly.tsx` +
  `frontend/src/api/monthly.ts` count as "Monthly files" too.
- `api/Modules/Auth/INVARIANTS.md` — login, 2FA, recovery codes,
  passkeys. The `_TOTP_REQUIRED_ROLES` single role gate, the
  Casbin-backed permissions matrix (privilege escalation
  surface — `RBAC_DEFAULTS` + the `casbin_rule` table), the
  opaque-error-message rule (anti-enumeration), the pending vs
  access token purpose separation, the passkey-register
  TOTP-first rule for superadmin, the forward invariant for a
  passkey-LOGIN flow (when it lands, must follow the documented
  rules), and the `WEBAUTHN_RP_ID` invalidate-everything rule.
  Auth changes deserve an explicit review header in the PR
  description.

When more INVARIANTS docs land (Batches), add them to
this list. The point: a `frontend/src/routes/Bank.tsx` edit
needs the Bank invariants in scope; a daily-book edit needs
the daily-book ones; a transfer edit needs the transfer ones;
a monthly P&L edit needs the monthly ones.

### Code-level invariants

1. **Design system is the source of truth.** See
   [`docs/design-system/`](docs/design-system/) and the "Design
   system" section above. Dark-only, neon `#3fff00` as sole accent,
   Space Grotesk + Inter + JetBrains Mono. The rest of this invariant
   #1 is historical context — follow the design system first; the
   legacy tokens below are still loaded but mostly supplanted.

   Every template `<link>`s `static/design-tokens.css` +
   `static/content.css` + `static/shell.css` (via `base.html`); the
   legacy `static/app.css` still loads for layout utilities (`.banner-*`,
   `.info-box`, `.info-row`, `.empty-state`, `.coming-pill`, `.modal-*`,
   `.section-box`, `.sb-row`, `.sb-label`, `.sb-input`, `.sb-total`,
   `.info-row`, `.empty-state`, `.coming-pill`, `.modal-*`,
   `.section-box`, `.sb-row`, `.sb-label`, `.sb-input`, `.sb-total`,
   `.sb-auto-badge`, `.sb-summary-box`, `.mt-table`, `.sticky-save-bar`,
   `.quick-links-grid` + `.quick-link-card`) rather than rolling your own.

   **`.quick-link-card` is the standard for any "pick where to go"
   landing grid** — icon tile + title + one-line description, hovers
   into the brand blue with a subtle lift. Use it whenever you'd
   otherwise be tempted to write a `<ul>` of plain links: superadmin
   tab landings, store admin settings hubs, "what next?" prompts on
   wizard finish pages, etc. See the Quick Links section on
   `superadmin_controls?tab=overview` for the canonical example.

   **For ANY surface, text, or border that should respect the light/dark
   toggle, use the semantic tokens** — they are the only tokens that
   flip in `[data-theme="dark"]`:
    - `--surface`        (card / box background)
    - `--surface-2`      (subtle inset: totals rows, read-only fields)
    - `--surface-sticky` (sticky save bars)
    - `--text`           (primary body text)
    - `--text-muted`     (secondary labels)
    - `--border`         (component borders)
    - `--border-strong`  (button outlines, focus rings)

   The fixed tokens (`--navy`, `--blue`, `--gold`, `--white`, `--gray1`,
   `--gray2`, `--gray4`, `--dark`, `--cream`, `--paper`) are brand /
   mode-agnostic colors — only reach for them when you specifically want
   a color that does NOT flip (e.g. a navy hero, a gold accent band).
   **Never use `--white` / `--gray1` / `--dark` for a surface or text
   that should adapt to dark mode** — that's the bug we keep regressing
   on. Likewise: no hardcoded hex for backgrounds/text; pick a
   semantic token or a brand token.

   For section-box header accent colors, set the `--sb-accent` custom
   property inline (`style="--sb-accent: var(--blue);"`) — don't
   override `background:` directly. New report-like pages should reuse
   `.section-box` + `.sb-*` rather than define their own family.
2. **Sidebar groupings** (admin) — **Workspace · Books · Finance ·
   Account**. Superadmin gets a **Platform** section with **Controls**.
   New pages belong to exactly one section; add the nav link in
   `templates/base.html`.
3. **Trial state machine** — `Store.plan ∈ {trial, basic, pro, inactive}`.
   `get_trial_status(store)` returns `active | expiring_soon | grace |
   expired | exempt`. Routes allowed during `expired` are enumerated in
   `_TRIAL_EXEMPT` — extend this set when you add routes that must stay
   reachable after the trial ends (subscribe, logout, billing portal,
   cancel, admin_subscription, the new password-reset routes).
4. **Data retention** — on Stripe `customer.subscription.deleted` we set
   `Store.data_retention_until = now + 180 days`. On resubscribe
   (`checkout.session.completed`) we clear it. `purge_expired_stores()`
   cascades through every per-store table (`_STORE_OWNED_MODELS`) before
   deleting the `Store` row. Add new per-store models to that list.
5. **Customer upsert (owner umbrella scope)** —
   `find_or_upsert_customer()` is the only path that creates or updates
   `Customer` rows from the transfer form. Lookup order:
   1. explicit `customer_id` (only reused if the target customer lives
      in a sibling store — the current store's owner umbrella);
   2. `(phone_country, phone_number)` across **every store that shares
      an owner with the current store** via `sibling_store_ids()` —
      so a cashier at Store B finds the sender that Store A logged;
   3. else create a new record pinned to the current `store_id`.
   A Customer row always stays pinned to its home store; transfers at
   sibling stores just point `customer_id` at it (no duplication). Newest
   values overwrite — edits from anywhere in the umbrella propagate.
   Unrelated stores (no owner overlap) remain fully isolated.
6. **Feature flags** — `store_feature_enabled(store, key)` resolves
   per-store override → global default → **fail-open** (undeclared flag
   returns True). New optional features should gate on a flag named
   `addon_<key>` (for add-ons) or a descriptive key (`bank_sync`,
   `multi_store_owner`). Declare defaults in `_DEFAULT_FEATURE_FLAGS`.
7. **Audit log** — every superadmin mutation calls `record_audit(action,
   target_type, target_id, details)`. Don't commit a superadmin route
   that mutates state without an audit entry.
8. **Stripe checkout** — `subscribe_checkout` passes
   `allow_promotion_codes=True`. Do not remove it: discount redemption
   depends on it.
9. **Fee vs Federal tax** — `Transfer.fee` is store revenue;
   `Transfer.federal_tax` leaves with the ACH withdrawal. Always:
   - `Transfer.total_collected = send_amount + fee + federal_tax`
   - `ACHBatch.transfers_total   = Σ (send_amount + federal_tax)`
10. **Password reset** — tokens are stored as `sha256(raw)` in
    `PasswordResetToken.token_hash`, single-use, 1-hour expiry. The raw
    token never hits the DB. `/forgot-password` always responds with
    "Check your email" regardless of whether the account exists.
    **Superadmin is deliberately excluded** from the email flow — an
    attacker who compromises the superadmin mailbox would bypass 2FA.
    Superadmin recovery goes through `flask reset-superadmin` on the
    Render shell (optionally `--reset-2fa` to also wipe TOTP if the
    recovery codes are lost).
11. **`db.session.get(Model, id)`** — never `Model.query.get(id)` (legacy
    SQLAlchemy 2.0 API, emits deprecation warnings).
12. **Referrals** — `ReferralCode` is one-per-store, minted lazily by
    `ensure_referral_code(store)` when an admin on a paid plan loads any
    page (context processor does this) and explicitly by the
    `checkout.session.completed` webhook. Credits are applied by
    `apply_pending_referral_credits(referee_store)` also inside that
    webhook — $50 to the referee, $100 to the referrer, via Stripe
    `create_balance_transaction`. Idempotent: `ReferralRedemption` is the
    lockout row and `Store.referee_credit_applied_at` gates retries. The
    topbar crown reads `my_referral_code` from the context processor —
    empty string hides it, so the button self-gates on role + plan.
13. **2FA (TOTP) is mandatory for superadmin — *unless* they sign in
    with a passkey.** Login routes are the only source of truth:
    - `/login` POST (password flow) → if creds valid AND
      `_needs_totp(user)` returns True, set
      `session["pending_auth_user_id"]` (NOT `user_id`) and redirect
      to `/login/2fa/enroll` (first time) or `/login/2fa`.
    - `/login/2fa/*` may call `_finalize_2fa_login(user)`, which
      promotes `pending_auth_user_id` → real `user_id`. **Never set
      `session["user_id"]` directly from the password-login path for
      a role that `_needs_totp` returns True for.**
    - **Passkey carve-out:** `/login/passkey/finish` sets
      `session["user_id"]` directly *after* successfully verifying a
      WebAuthn assertion, even when `_needs_totp(user)` is True. A
      passkey is phishing-resistant MFA by construction (device-bound,
      user-presence-proven, RP-ID-bound) — stacking TOTP on top adds
      friction without adding security. The invariant is: full-auth
      promotion requires either a TOTP factor OR a verified passkey
      assertion; no other code path may set `user_id` directly.
    - Recovery codes: 10 per user, sha256-hashed, single-use
      (`RecoveryCode.used_at`). Shown in plaintext exactly once on the
      post-enrollment recovery-codes page.
    - TOTP secret (`User.totp_secret`) is base32 plaintext in the DB —
      the DB is the trust boundary, same as `password_hash`.
    - Passkey storage: `Passkey` table holds `(user_id, credential_id,
      public_key, sign_count, aaguid, name)`. `credential_id` is
      unique and the lookup key at login time. `sign_count` is
      authenticator-reported; we accept equal-or-greater values and
      reject resets to protect against cloned authenticators.
    - To extend 2FA to other roles, change the single `_needs_totp()`
      predicate; do NOT scatter role checks through the login routes.
14. **Table search UX — live-search is the standard.** Every paginated
    table (transfers is the reference implementation; customers,
    batches, monthly list, etc. should follow) uses the debounced AJAX
    pattern — **never** a plain "type then click Search" form. Pattern:
    - Split the table + pager into a `_<name>_table.html` partial.
    - The route accepts `?partial=1`, returns JSON `{html, total, page,
      total_pages, page_amount?, page_fees?}`.
    - Page-level template wraps the partial in a stable swap container
      (e.g. `<div id="transfersResult">`) and includes a small `<script>`
      that: debounces at **300ms**, enforces a **2-char minimum** on the
      global `q` box, cancels in-flight fetches via **AbortController**,
      and updates the URL with `history.replaceState` so filters are
      shareable. Selects + date pickers fire immediately on `change`.
    - Focus must stay in the search input — the swap region lives below
      the input, not around it.
    - Reference: `templates/transfers.html` + `templates/_transfers_table.html`
      + `/transfers` route's `partial=1` branch.
15. **Rate limiting** — every auth route, password-reset route, and
    webhook ingest endpoint is bucketed by slowapi on the FastAPI
    side. The Flask-Limiter twin is gone — Flask has no remaining
    POST surface to limit.
    - Shared singleton `slow_limiter` in `api/Core/RateLimit.py`.
      Critical endpoints carry `@_rate_limiter.limit(...)`
      decorators on their controllers (look for `from
      api.Core.RateLimit import limiter as _rate_limiter` in
      `api/Modules/Auth/Controllers/__init__.py`).
    - Storage backend defaults to in-memory; prod sets
      `RATELIMIT_STORAGE_URI=redis://...` in `render.yaml` so the
      bucket holds across workers. `RATELIMIT_ENABLED=0` disables
      the limiter (the test conftest sets this — never set it in
      prod).
    - slowapi captures `enabled` at import time, so toggling the
      flag at runtime doesn't re-arm decorators that were created
      with `enabled=False`. Tests that exercise the 429 path spawn
      a subprocess (see `tests/test_rate_limiting.py`).
    - Don't tighten the limits casually — integration tests and
      Stripe webhook retries both burn rate budget. Loosening is
      always safer than the alternative.
16. **Background-job queue (BACKLOG D5)** — heavy / slow work in
    a request handler goes through ``api.Core.Jobs.enqueue(...)``,
    not a direct call. Examples: SMTP send (the
    ``/forgot-password`` flow already uses this — see
    ``send_password_reset_email`` in
    ``api/Modules/Auth/Controllers/__init__.py``), Stripe SDK
    round-trips that don't have to land before the response, and
    anything that fans out to N recipients.
    - Activation is opt-in via ``JOB_QUEUE_ENABLED=1`` +
      ``REDIS_URL`` env vars on both the web service and the
      worker. Either missing → sync execution (the default; same
      semantics as a direct call). This keeps the test suite + the
      default dev loop running without Redis.
    - Worker service is staged commented in ``render.yaml`` —
      see the 4-step activation runbook embedded in the YAML
      comments. Uncomment after Redis is provisioned and the env
      vars are set.
    - Args MUST be primitives (ids, dicts, strings) — not ORM
      objects. RQ pickles args for the worker, and the request
      session is closed by the time the worker runs. Worker
      functions open their own ``SessionLocal`` to reload state.
    - Worker functions are top-level (not closure-scoped) so RQ
      can pickle them by import path.
    - Tests in ``tests/Core/test_jobs.py`` exercise both modes
      (sync + queued) and the defensive partial-env fallback.
17. **CSRF protection** — Flask has no POST surface anymore so
    Flask-WTF is gone. The SPA talks to FastAPI over Bearer JWT
    in the Authorization header, which is naturally CSRF-immune
    (browsers don't attach it to cross-origin requests by
    default). Webhook endpoints verify provider signatures
    (Stripe `Stripe-Signature`, Resend HMAC) so they don't rely
    on session-cookie auth either. If you ever reintroduce a
    cookie-authenticated form-POST surface, add CSRF protection
    back at that point — don't bolt cookie auth onto a JSON
    endpoint without it.

## Migrations
**Every schema change is an Alembic revision.** Generate one with:
```bash
alembic revision --autogenerate -m "add foo.bar"
```
Review + edit the generated file under `alembic/versions/`
(autogenerate gets most things right but misses data backfills
and SQLite batch-mode quirks — read every line before committing).

`init_db()` runs `alembic upgrade head` on boot — that's the sole
schema mechanism. Fresh dev DBs are built by the baseline
migration + every subsequent revision; existing DBs upgrade in
place. There is no `db.create_all()`, no `_ADDED_COLUMNS` list.

**Never drop a column from a running database without a backfill
step** — rename it in one revision, copy data over, drop the old
column in a follow-up revision once the dual-write window has
elapsed.

## Bank-charge automation (built-in rules)
Standard bank charges from a known institution shouldn't require the
operator to set up their own rule. Examples: Nizari Progressive's
`REMOTE DEPOSIT FEE` always lands on the MSB ••0230 account; we
auto-categorise it and feed `MonthlyFinancial.bank_charges_230` so
the operator doesn't have to touch the monthly P&L for it.

This list will GROW. Read this section before adding a new entry —
production stores rely on it, and a wrong slug or account_last4
silently misroutes money on a live P&L.

### How to add a new built-in rule

1. **Edit `BUILTIN_BANK_RULES`** in
   `api/Modules/BankSync/Services/builtin_rules.py`. Each entry is
   a 3-tuple:
   ```python
   ("DESCRIPTION SUBSTRING", "ACCOUNT_LAST4_OR_BLANK", "TARGET_KIND"),
   ```
   - **Description** is matched case-insensitively, substring-style. Keep
     it specific enough to not collide (e.g. `"REMOTE DEPOSIT FEE"`,
     not `"FEE"`).
   - **Account last4** restricts the rule to one account. Use `""` to
     match any account. The Nizari case is account-specific — the
     same string on a different account would mean something else.
   - **Target kind** must be a slug in `BANK_CATEGORIES_NON_POSTING`
     OR `_LINE_ITEM_KINDS`. Today the only bank-charge slugs are
     `bank_charge_210` and `bank_charge_230`.

2. **Built-ins fire after operator rules**. Operator-managed rules in
   `BankRule` always take precedence. Built-ins only run on freshly-
   inserted, still-uncategorised rows during sync. Re-syncing existing
   rows preserves any operator override.

3. **Built-ins never create DailyLineItems** — `post_to_daily=False`
   in the call site. Bank-charge transactions feed the monthly P&L
   only, not the daily book. Don't change that without coordinating
   with the daily-book locked-fields contract.

### How the P&L feed works

The single point of truth is `_BANK_CATEGORY_PL_FIELD` — a registry
that maps a bank-transaction `category_slug` to a `MonthlyFinancial`
column name. Every category in the registry auto-flows to its mapped
P&L column with no per-field wiring in `monthly_report()`:

```python
_BANK_CATEGORY_PL_FIELD = {
    "bank_charge_210": "bank_charges_210",
    "bank_charge_230": "bank_charges_230",
    # Append a row here whenever a new built-in rule (or operator
    # rule) targets a category that should hit a P&L line.
}
```

- `_bank_charges_for_month(store_id, year, month, category_slug)` sums
  the absolute `amount_cents` of `BankTransaction` rows tagged with
  the slug for the given month, returns dollars. Generic over any
  category despite the historical name.
- `monthly_report()` iterates the registry and populates
  `auto[field_name]` for every entry. Then it iterates the registry
  again and adds each `field_name` to `LOCKED_FIELDS` **only when the
  auto value is > 0** — backward-compat guard so stores without bank
  sync (or months with no tagged transactions) keep their manually-
  entered P&L values. Don't unconditionally lock these or you'll wipe
  manual entries on Basic-plan stores.
- The template (`templates/monthly_report.html`) renders each mapped
  field through `pl_field(name, label, auto_key=…, locked=(auto.get(…)>0),
  locked_source='bank sync')`. New entries in the registry need a
  matching `pl_field` call in the template until we generalise the
  template too.

### Adding a new bank automation end-to-end

1. Append a `_BUILTIN_BANK_RULES` entry (description substring +
   account_last4 + target_kind) — OR let the operator categorise
   manually via `/bank/transactions`.
2. Append a `_BANK_CATEGORY_PL_FIELD` row mapping the slug to the
   `MonthlyFinancial` column name.
3. If the column doesn't exist on `MonthlyFinancial` yet, add it to
   the model + `_ADDED_COLUMNS` (idempotent on next boot).
4. Update the matching `pl_field` call in `monthly_report.html` to
   pass `auto_key=...` + `locked=(auto.get(...)>0)` +
   `locked_source='bank sync'` so the form actually displays the
   auto value.
5. Add a test like the ones in `tests/test_bank_charges_pl.py` that
   covers (a) the matcher firing, (b) the `_bank_charges_for_month`
   sum, (c) the rendered P&L showing the locked auto value.

Amounts can vary across statements — built-in rules match on
description substring (case-insensitive) + account, never on amount.
A "REMOTE DEPOSIT FEE" of $2.10 today and $5.00 tomorrow both match
the same rule.

### What to NOT do

- Don't add a built-in rule that targets a daily-book kind
  (`cash_expense`, `check_expense`, etc.) — built-ins are
  bank-side-only by contract; daily-book auto-creation is operator-
  managed via `BankRule.auto_post`.
- Don't reuse `bank_charge_210` / `bank_charge_230` for non-charge
  transactions. They feed the bank-charges P&L columns specifically.
- Don't lower the case-insensitive match to exact-match unless the
  bank's description is genuinely stable across statements.

### Test recipe

Every new rule needs at minimum:
1. A test asserting `_match_builtin_bank_rule(txn, account)` returns
   the expected slug for the matching description + account combo.
2. A negative test confirming the rule does NOT fire when the account
   filter is set and the wrong account is used.
See `tests/test_bank_charges_pl.py` for the canonical pattern.

## Module map (api/Modules)
Every domain owns four layers: `Models`, `Repositories`,
`Services`, `Controllers`. Controllers register on the FastAPI
router in `api/main.py`.

| Module | Owns |
|---|---|
| `Admin` | Store settings, team, owner invites, tax export |
| `Announcements` | Global banner system + email broadcast |
| `Audit` | Operator + superadmin audit logs, transfer audit |
| `Auth` | Login (password + TOTP + passkey), JWT issuance, password reset, notifications prefs |
| `BankSync` | Stripe Financial Connections, `BankTransaction`, `BankRule`, `BUILTIN_BANK_RULES` |
| `Batches` | ACH batch CRUD + linked transfers |
| `Billing` | Stripe checkout, subscriptions, addons, referrals, data retention |
| `Customers` | `find_or_upsert_customer`, autocomplete search, `PHONE_COUNTRY_CODES` |
| `DailyBook` | Daily report, line items, drops, deposits |
| `Dashboard` | Per-role landing data |
| `FeatureFlags` | Per-store overrides + global defaults |
| `Monthly` | P&L with auto bank-charge feed (see Bank-charge automation) |
| `Notifications` | SMTP send, email templates, trial reminders, locked-day digest |
| `Owners` | Multi-store owner umbrella + dashboard rollup |
| `Reports` | Per-store + platform reports, CSV exports (registry-driven) |
| `ReturnChecks` | Returned-check tracking + payments |
| `Superadmin` | `/superadmin/*` controls, anomalies, BI reports |
| `Support` | In-app support tickets (admin → superadmin) |
| `Tenancy` | `Store`, `User`, `StoreEmployee`, `StoreOwnerLink`, `OwnerConnectCode` |
| `TimeClock` | Employee shift clock-in / clock-out + admin payroll history |
| `Transfers` | Transfer CRUD + cancellation flow |
| `TVDisplay` | Rate-board addon, public display, Fire TV pairing |
| `Webhooks` | Stripe + Resend ingest |

Cross-cutting (under `api/Core/`):

| Module | Owns |
|---|---|
| `Audit` | `audit_operator`, `audit_superadmin`, `@audit_action` decorator — claims-aware wrappers around the recorder Services |
| `Boot` | `init_db()`, `warn_default_seed_passwords()` — called from `api/main.py` lifespan |
| `Bootstrap` | Alembic upgrade, index safety-net, legacy backfills |
| `Clock` | `utc_now()` — canonical UTC timestamp (single point to flip when migrating to tz-aware) |
| `Config` | Pydantic-settings env loader |
| `Csv` | `build_csv(headers, rows)` — string-based CSV construction helper |
| `Database` | SQLAlchemy engine + `SessionLocal` + `get_db` FastAPI dep |
| `Jobs` | RQ-backed ``enqueue(fn, *args)`` with sync fallback |
| `Observability` | structlog config, Sentry init, `RequestIDMiddleware`, `SecurityHeadersMiddleware` (CSP + frame options) |
| `Pagination` | `PaginationParams` + `paginate()` + `paginate_list()` — shared list-endpoint envelope |
| `PasswordHash` | bcrypt wrappers used by signup + change-password |
| `Permissions` | Casbin-backed RBAC — `check_permission`, `require_permission`, `permissions_for`, `set_store_permissions`, etc. |
| `RateLimit` | slowapi singleton + decorator |

Top-level files:

| File | Owns |
|---|---|
| `asgi.py` | Production ASGI router — FastAPI mount, SPA shell, `/static/`, PublicRoutes, cutover redirects |
| `api/main.py` | `create_app()` factory + lifespan + router registration |
| `api/spa.py` | Vite build serve (`/app/*`) |
| `api/PublicRoutes.py` | Landing, PWA, TV display, pair-code API |
| `api/SpaCutover.py` | Pure `redirect_target(path, qs)` for legacy URLs |
| `tests/_app.py` | Test-only re-export shim (`db`, `flask_app` stub, helpers) |

## Templates
- `base.html` — admin/employee chrome (sidebar + topbar + banner zone).
  Loads app.css → design-tokens.css → content.css → shell.css in that
  order. Don't reorder — shell must win the cascade.
- `base_owner.html` — multi-store owner chrome (same design system).
- `static/design-tokens.css` — dark+neon tokens + legacy aliases.
  **New tokens go here.**
- `static/content.css` — overrides for every legacy content class
  (`.card`, `.stat-card`, `.badge`, `.btn-*`, tables, forms, banners).
  Templates that extend `base.html` inherit this for free.
- `static/shell.css` — sidebar + topbar overrides. Loaded last.
- `static/app.css` — retained for layout utilities and the semantic
  dark-mode tokens (`--surface`, `--text`, `--border`). Don't add
  new brand colors here.
- Logged-out auth pages (`landing.html`, `login.html`, `signup.html`,
  `signup_owner.html`, `login_store.html`, `forgot_password.html`,
  `reset_password.html`, `offline.html`, `privacy.html`) are standalone
  and link `design-tokens.css` directly — they don't extend a base.
- 2FA pages use the shared `_login_chrome.html` + `_login_chrome_end.html`
  partials (login_totp, login_totp_enroll, login_totp_recover,
  login_totp_recovery_codes).

## OpenAPI → TypeScript types
The SPA reads request/response shapes from
`frontend/src/api/openapi.d.ts`, a file generated by
`openapi-typescript` from the FastAPI app's runtime OpenAPI spec.
**Don't edit it by hand.** Regenerate any time you change a
Pydantic schema or add/rename a route:

```bash
cd frontend && npm run generate-types
```

That chains `python -m scripts.dump_openapi` (dumps
`api_app.openapi()` to `openapi.json`) with `openapi-typescript`
(turns the JSON into the `.d.ts`). Both files are checked in
so the SPA build doesn't need a live backend. There's no CI
gate enforcing sync — regenerate after Pydantic-schema edits as
part of your normal commit. If the committed `.d.ts` is stale,
TypeScript will catch the drift at the call site when you
import a renamed/removed field.

Consume the types via `import type { components } from "./openapi"`:

```typescript
import type { components } from "./openapi";
type AnnouncementRow = components["schemas"]["AnnouncementRow"];
```

New code should use this pattern instead of hand-writing
interfaces. The 17 existing files in `frontend/src/api/*.ts`
migrate on-touch; `announcements.ts` is the canonical example.

## Tests
```bash
pytest tests/          # ~290 tests currently, plus ~20 skipped
pytest tests/ -x -q    # stop on first failure, quiet
```
Fixtures live in `tests/conftest.py` and set up an in-memory SQLite with
a seeded superadmin + one trial store. **When I add features via chat
smoke tests, those need to graduate into committed tests** — tracked in
BACKLOG.md.

## mypy — strict ratchet

```bash
python -m mypy   # runs against the curated file list in pyproject.toml
```

E5 (BACKLOG.md) — `pyproject.toml` enumerates the files held to
`--strict`. The rest of the tree is unchecked.  **Adding a file to the
ratchet** is the workflow:

1. Run `python -m mypy --strict --follow-imports=silent path/to/file.py`
   from the repo root.
2. Fix what fires (or add targeted `# type: ignore[error-code]` for
   the genuinely-untyped third-party seams).
3. Append the path to the `files = [...]` list in `pyproject.toml`.
4. `python -m mypy` (no args) re-runs the full ratchet — CI runs the
   same command.

Known traps:
- **SQLAlchemy 1.x `Column(...)` declarations** report attributes as
  `Column[T]` instead of `T`, which trips every assignment on a service
  that touches ORM rows. Either migrate the model to `Mapped[T] =
  mapped_column(...)` first (own PR) or keep the service out of the
  ratchet for now.
- **FastAPI `@router.<verb>(...)` decorators** fire `untyped-decorator`
  in older FastAPI stubs. Quarantined until we pin a newer FastAPI or
  selectively `# type: ignore[misc]`.

## Git & PR workflow
- Work on `claude/add-subscription-management-LdGPx` (the project's
  long-running feature branch) unless told otherwise. Sync from `main`
  before starting: `git pull --ff-only origin main`.
- One commit per coherent change. Commit messages explain *why*, not
  *what*; include a short "test plan" in PR descriptions.
- Never push to `main`. Always open a PR.
- Never bypass hooks (`--no-verify`, `--no-gpg-sign`) unless asked.

## What NOT to do
- ❌ Inline-style hex colors that duplicate `app.css`.
- ❌ Drop columns or tables from a running DB without a backfill
  step (rename in one revision, copy data, drop in a follow-up).
- ❌ Skip audit logging on a superadmin / admin mutation — use
  `audit_superadmin(db, user, ...)` or `audit_operator(db, claims, ...)`
  from `api.Core.Audit`.
- ❌ Remove `allow_promotion_codes=True` from Stripe checkout.
- ❌ Use `Model.query.get(id)` — use `db.session.get(Model, id)`.
- ❌ Add a new `Store.plan` value without updating `get_trial_status`
  and the trial context processor.
- ❌ Add a per-store data model without adding it to the
  retention-purge list in `api/Modules/Billing/Services/retention.py`.
- ❌ Add inline SQL in a Controller when a Repository helper exists
  (or could exist) — Owners, Superadmin, Admin, Transfers, Auth,
  TimeClock all have `Repositories/` packages.
- ❌ Commit without `pytest tests/` passing AND `python -m mypy` clean.
- ❌ Leak the raw password-reset token to the DB or logs on success —
  only log on SMTP-fallback and only the URL.
- ❌ Inline `db.query(...)` queries inside `Casbin` permission checks —
  use the `api.Core.Permissions` API (`check_permission`,
  `permissions_for`, `set_store_permissions`, etc.) so the Casbin
  enforcer singleton stays the only direct caller.

## Deferred work
See `BACKLOG.md`. Items under **Before going live** are gates for public
launch; the rest can land on any cadence.

## PR monitoring — auto-subscribe, auto-fix CI, address comments

For every PR you open (or find open) on a branch you're working on in this
repo, **automatically call `subscribe_pr_activity`** without asking first.
Do not ask "would you like me to watch this PR?" — just subscribe.

When PR activity events arrive:

- **CI failures (`get_check_runs` shows failing jobs, or a webhook event
  reports a failed check):** investigate the failing job's logs, push a fix
  commit to the same branch, and report what you changed. If the failure
  is flaky or outside the PR's scope, say so and skip rather than guessing.
- **Review comments (review threads, PR comments):** for each unresolved
  thread, read the comment, assess whether the suggestion is correct, and
  either (a) push a fix and reply briefly, or (b) reply with why the
  suggestion doesn't apply. Use `AskUserQuestion` only when a comment is
  genuinely ambiguous or would require a large refactor.
- Never skip hooks or force-push to address CI failures — fix the
  underlying problem.
- Stay on the PR's branch; never push unrelated changes.

When there is no open PR for the current branch and the user is done with
a set of changes, offer to open one so CI can run.
