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
- Flask 3.0 (intentionally monolithic; all routes in `app.py`).
- SQLAlchemy 3.1, SQLite in dev, Postgres in prod.
- No migrations framework — see "Migrations" below.
- Jinja2 templates + a single shared stylesheet (`static/app.css`).
- Stripe for billing (Checkout Sessions + Billing Portal + webhooks).
- pytest + pytest-flask.

## Running locally
```bash
pip install -r requirements.txt
python app.py             # dev server on :5000
pytest tests/             # full suite
flask purge-expired-stores  # deletes inactive stores past retention
```
First boot seeds a superadmin (`superadmin / super2025!`) and demo store
admin (`admin / cambio2025!`). Override via `SUPERADMIN_PASSWORD` /
`ADMIN_PASSWORD` env vars in prod.

## Critical invariants — don't break these

1. **One stylesheet** — every template `<link>`s `static/app.css`. Use
   the CSS vars (`--navy`, `--gold`, `--red-dark`, `--green-dark`,
   `--yellow-bg`, etc.) and utility classes (`.banner-*`, `.info-box`,
   `.info-row`, `.empty-state`, `.coming-pill`, `.modal-*`). Do not
   re-define these inline.
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
5. **Customer upsert** — `find_or_upsert_customer()` is the only path
   that creates or updates `Customer` rows from the transfer form.
   Lookup order: explicit `customer_id` → `(store, phone_country,
   phone_number)` → else create. Newest values overwrite. Do not add
   ad-hoc Customer creation elsewhere.
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
11. **`db.session.get(Model, id)`** — never `Model.query.get(id)` (legacy
    SQLAlchemy 2.0 API, emits deprecation warnings).

## Migrations (no framework)
New columns on existing tables go in `_ADDED_COLUMNS` (list at bottom of
`app.py`):
```python
("table_name", "column_name", "<DDL after ADD COLUMN>"),
```
`_ensure_added_columns()` runs on boot and is idempotent — safe on every
restart. New **tables** are picked up by `db.create_all()`. **Never drop
a column from a running database** — rename/backfill in a follow-up
deploy if you really need to remove one.

## Section map (app.py)
Search for the `# ── HEADER ──` block comments. Rough order:

| Section | What it owns |
|---|---|
| Models | All `db.Model` classes + `_ADDED_COLUMNS` |
| Auth decorators | `login_required`, `admin_required`, `owner_required`, `superadmin_required`, `_TRIAL_EXEMPT` |
| Trial status | `get_trial_status`, `inject_trial_context` |
| Superadmin helpers | `record_audit`, `store_feature_enabled`, `stripe_health_check`, `active_announcements` |
| SimpleFIN | Bank sync via access URL |
| Login / signup / forgot-password | all auth routes |
| Subscribe / billing portal / cancel | `/subscribe`, checkout, cancel, billing portal |
| Dashboard | admin / employee / superadmin |
| Customers + autocomplete API | `find_or_upsert_customer`, `/api/customers/search`, `PHONE_COUNTRY_CODES` |
| Transfers | new, edit |
| Daily / Monthly reports | |
| ACH batches | |
| Admin settings / users | Store info, password, team, owner invites |
| Superadmin controls | `/superadmin/controls` tabs + all mutate endpoints + CSV export |
| Announcements | Global banner system |
| Stripe webhook | `checkout.session.completed`, `customer.subscription.deleted` |
| Data retention purge | `flask purge-expired-stores` CLI |
| Init / seed | Feature flags, superadmin + demo store |

## Templates
- `base.html` — admin/employee chrome (sidebar + topbar + banner zone).
- `base_owner.html` — multi-store owner chrome (same design system).
- `static/app.css` — all shared styling including dark mode.
- Logged-out auth pages (`login.html`, `signup.html`, `signup_owner.html`,
  `forgot_password.html`, `reset_password.html`) are standalone — they
  link `static/app.css` for tokens but don't extend a base template.

## Tests
```bash
pytest tests/          # 92 tests currently
pytest tests/ -x -q    # stop on first failure, quiet
```
Fixtures live in `tests/conftest.py` and set up an in-memory SQLite with
a seeded superadmin + one trial store. **When I add features via chat
smoke tests, those need to graduate into committed tests** — tracked in
BACKLOG.md.

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
- ❌ Drop columns or tables from a running DB.
- ❌ Skip `record_audit()` on a superadmin mutation.
- ❌ Remove `allow_promotion_codes=True` from Stripe checkout.
- ❌ Use `Model.query.get(id)` — use `db.session.get(Model, id)`.
- ❌ Add a new `Store.plan` value without updating `get_trial_status`
  and the trial context processor.
- ❌ Add a per-store data model without adding it to
  `_STORE_OWNED_MODELS` (the retention-purge list).
- ❌ Commit without `pytest tests/` passing.
- ❌ Leak the raw password-reset token to the DB or logs on success —
  only log on SMTP-fallback and only the URL.

## Deferred work
See `BACKLOG.md`. Items under **Before going live** are gates for public
launch; the rest can land on any cadence.
