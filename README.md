# DineroBook

Multi-tenant bookkeeping SaaS for money-service businesses (MSBs).
Each Store has admins + employees; multi-store Owners connect via
invite codes; the platform runs under one Superadmin.

> First time on this codebase? Read [docs/architecture/request-lifecycle.md](docs/architecture/request-lifecycle.md)
> before opening a PR. It traces a request end-to-end so the
> Flask / FastAPI split below makes sense.

## Stack at a glance

| Layer | Tech | Where |
|---|---|---|
| Browser SPA | React 19, Vite, TanStack Query, React Router 7 | `frontend/` |
| Legacy HTML chrome | Flask 3.0 + Jinja2 | `app.py` + `blueprints/` + `templates/` |
| JSON API (new) | FastAPI mounted at `/api/v2/*` | `api/` |
| Database | SQLAlchemy 3.1 (SQLite dev, Postgres prod) | `_ADDED_COLUMNS` + Alembic |
| Billing | Stripe Checkout + Billing Portal + webhooks | `blueprints/billing.py`, `app.py` webhook |
| Auth | Cookie session for Flask, JWT for FastAPI; TOTP + WebAuthn | `blueprints/auth.py`, `api/Modules/Auth/` |
| Observability | Sentry (opt-in via DSN), structlog, X-Request-ID | `api/Core/Observability/` |
| Tests | pytest + pytest-flask + Playwright (optional) | `tests/` |

## Quick start

```bash
# 1. Install deps (Python + Node)
pip install -r requirements.txt
( cd frontend && npm install )

# 2. Run the dev server (Flask + mounted FastAPI on :5000)
python app.py

# 3. Run the SPA in dev mode against the API (optional, hot reload)
cd frontend && npm run dev    # opens :5173, proxies /api/v2 → :5000

# 4. Run tests
pytest tests/                  # full suite (~2,440 tests, 3-4 min)
pytest tests/ -x -q            # stop on first failure, quiet

# 5. SPA build + lint
cd frontend && npm run build   # writes to frontend/dist/
cd frontend && npm run lint    # eslint --max-warnings 0
```

First boot seeds a superadmin (`superadmin / super2025!`) and a demo
store admin (`admin / cambio2025!`). Override the seed passwords via
`SUPERADMIN_PASSWORD` / `ADMIN_PASSWORD` env vars in prod.

## Project layout

```
.
├── app.py                  # Flask app + models + helpers. Slim now
│                             after the D2 Blueprint split — almost
│                             every route lives under blueprints/.
├── asgi.py                 # ASGI dispatcher. Routes /api/v2/* to
│                             FastAPI, everything else to Flask via
│                             a2wsgi.WSGIMiddleware.
├── blueprints/             # Flask Blueprints (auth, billing, owner,
│                             admin_settings_form, bank_redirects, …)
│                             — one file per logical surface.
├── api/                    # FastAPI strangler-fig.
│   ├── main.py             #   FastAPI app factory + router includes
│   ├── Core/               #   Cross-cutting infra
│   │   ├── Config.py       #     Pydantic settings
│   │   └── Observability/  #     Sentry / structlog / request-IDs
│   └── Modules/            #   One folder per domain (Reports,
│                           #     Customers, Transfers, BankSync,
│                           #     Auth, DailyBook, Owners, …).
│                           #     Each has Controllers / Services /
│                           #     Repositories / Models.
├── templates/              # Jinja2 templates. Most are auth-only
│                             post-SPA cutover; the SPA shell lives
│                             at /app/* served by Flask catch-all.
├── static/                 # Design tokens + legacy stylesheets
│                             (loaded by both Jinja templates AND the
│                             SPA's index.html).
├── frontend/               # React 19 SPA.
│   ├── src/
│   │   ├── routes/         #   One file per page.
│   │   ├── components/     #   ui/ holds the design-system primitives
│   │   │                   #     (PageShell, KpiCard, EmptyState, …).
│   │   ├── api/            #   TanStack Query hooks per FastAPI module
│   │   └── lib/            #   auth, chartOptions, sentry, helpers
│   └── public/
├── tests/                  # pytest. Mirror api/Modules/ for the
│                             FastAPI side; root files for legacy.
├── docs/architecture/      # ADRs + runbooks. Start with
│                             request-lifecycle.md.
├── CLAUDE.md               # Engineering invariants. READ THIS before
│                             touching auth / billing / migrations.
├── BACKLOG.md              # Deferred work, "Before going live"
│                             checklist.
└── render.yaml             # Production service + DB declaration.
```

## "Where do I look to do X?"

| You want to… | Start here |
|---|---|
| **Add a new SPA page** | `frontend/src/routes/NewPage.tsx` + register in `frontend/src/App.tsx` + matching FastAPI module in `api/Modules/<Name>/` (Controllers + Services + Repositories) + TanStack Query hook in `frontend/src/api/<name>.ts` |
| **Add a new column to an existing table** | Add the field to the SQLAlchemy model in `app.py`, then append to `_ADDED_COLUMNS` at the bottom of `app.py`. `_ensure_added_columns()` runs on boot. |
| **Add a whole new table** | Add the SQLAlchemy class in `app.py`. `db.create_all()` will pick it up. If it's per-store, ALSO add it to `_STORE_OWNED_MODELS` or retention purge will leak it. |
| **Add a Flask route** | Find the closest existing Blueprint under `blueprints/`. If the surface is new, add a new Blueprint file and register it in the import + `app.register_blueprint(...)` block near the top of `app.py`. |
| **Add a FastAPI endpoint** | Find or create the module under `api/Modules/<Name>/`. Controllers go in `Controllers/`, business logic in `Services/`, DB queries in `Repositories/`. Register the router in `api/main.py`. |
| **Add a new BI report** | Append an entry to `_BI_REPORTS` in `api/Modules/Reports/Services/__init__.py` with the slug + Service function. The SPA's `SuperadminBIDrilldown.tsx` auto-renders any new slug. |
| **Add a new bank-charge auto-rule** | Append to `_BUILTIN_BANK_RULES` in `app.py`. Read the "Bank-charge automation" section of `CLAUDE.md` first — accounts + descriptions are sensitive and a wrong slug misroutes money on live P&L. |
| **Tighten password / 2FA / passkey behavior** | `blueprints/auth.py` for the request layer; helpers (`_needs_totp`, `_passkey_eligible`, …) live in `app.py`. Read invariant #13 in `CLAUDE.md` before touching the login state machine. |
| **Change a Stripe webhook reaction** | `app.py` `/webhooks/stripe` route. Pairs with `apply_pending_referral_credits` and the data-retention reset logic — those four cases must stay coupled. |
| **Toggle a feature for a single store** | `store_feature_enabled(store, key)` + `_DEFAULT_FEATURE_FLAGS` in `app.py`. Superadmin UI is at `/superadmin/controls?tab=features`. |
| **Audit a superadmin mutation** | `record_audit(action, target_type, target_id, details)` — every mutation route already calls this; new ones MUST. Audit log + CSV export live in `blueprints/superadmin_extras.py`. |
| **Style something** | Read the "Design system" section of `CLAUDE.md`. Dark-only, neon `#3fff00` is the only saturated color, three fonts. Use `static/design-tokens.css` tokens, not raw hex. SPA primitives in `frontend/src/components/ui/index.tsx`. |
| **Add a test** | Mirror the path: `api/Modules/X/Services/foo.py` → `tests/Modules/X/test_foo.py`. Legacy Flask routes go in `tests/test_<surface>.py`. Fixtures live in `tests/conftest.py`. |

## Common workflows

### Run a single test fast

```bash
pytest tests/test_admin_settings_spa.py -v
pytest tests/test_admin_settings_spa.py::test_specific_case -v
```

`tests/conftest.py` downgrades password hashing to 1 PBKDF2 iteration
for the suite so test setup stays under a few seconds.

### Apply a manual migration

DineroBook uses `_ADDED_COLUMNS` (idempotent boot-time DDL) as the
primary migration mechanism. **Never drop a column from a running
database** — rename + backfill across a follow-up deploy if you
truly need to remove one.

Alembic is wired (baseline migration `99691740424c_baseline_2026_05`)
but dormant. See [`docs/architecture/migrations.md`](docs/architecture/migrations.md)
for the cutover plan.

### Reset the superadmin password (prod)

```
flask reset-superadmin --reset-2fa
```

Runs on the Render shell. `--reset-2fa` also wipes TOTP if the
recovery codes are lost. The forgot-password email flow is
deliberately disabled for the superadmin role.

### Purge expired stores (data retention)

```
flask purge-expired-stores
```

Cascades through `_STORE_OWNED_MODELS` before deleting the `Store`
row. Add any new per-store model to that list.

## Production deploy

The primary service is `dinerobook` on Render, hostnamed at
`https://dinerobook.com`. Database is `dinerobook-db` (Postgres),
linked via `fromDatabase:` in `render.yaml`. Every push to `main`
auto-deploys.

Required environment variables (set in the Render dashboard):

| Env var | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing |
| `DATABASE_URL` | Postgres connection string (Render injects) |
| `STRIPE_SECRET_KEY`, `STRIPE_BASIC_PRICE_ID`, `STRIPE_PRO_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` | Stripe Checkout + webhook verification |
| `APP_BASE_URL` | `https://dinerobook.com` — gates `SESSION_COOKIE_SECURE` and is used by SMTP / Stripe URL builders |
| `WEBAUTHN_RP_ID` | `dinerobook.com` — pins WebAuthn Relying Party ID. Changing invalidates every existing passkey. |
| `SUPERADMIN_PASSWORD`, `ADMIN_PASSWORD` | Override the dev seed passwords in prod |
| `SENTRY_DSN` (Python), `VITE_SENTRY_DSN` (SPA) | Optional — error tracking |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | Transactional email |
| `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` | Alternative to SMTP — managed transactional email |

The "Before going live" checklist in [`BACKLOG.md`](BACKLOG.md) is
the canonical pre-launch gate. Don't switch on Stripe LIVE keys
until every item there is closed out.

## More docs

* [`CLAUDE.md`](CLAUDE.md) — engineering invariants (auth, billing,
  data retention, design system, what NOT to do).
* [`BACKLOG.md`](BACKLOG.md) — deferred work + "Before going live"
  checklist.
* [`docs/architecture/`](docs/architecture/) — ADRs + runbooks.
* [`docs/architecture/request-lifecycle.md`](docs/architecture/request-lifecycle.md)
  — end-to-end trace of a request through asgi.py → Flask /
  FastAPI → SQLAlchemy → Postgres, plus observability hooks.
* [`docs/architecture/migrations.md`](docs/architecture/migrations.md)
  — Alembic + `_ADDED_COLUMNS` workflow.
* [`docs/architecture/deployment.md`](docs/architecture/deployment.md)
  — Render deploy runbook: env-var checklist, secret rotation,
  backup verification, incident playbook.

## Contributing

* Stay on a feature branch (`claude/<short-slug>` is the convention).
* One commit per coherent change; commit messages explain **why**,
  not what.
* `pytest tests/` + `cd frontend && npm run build && npm run lint`
  before pushing. CI runs both.
* PRs go to `main`. Don't push to `main` directly.
* Don't bypass hooks (`--no-verify`, `--no-gpg-sign`) unless asked.
