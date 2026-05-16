# DineroBook

Multi-tenant bookkeeping SaaS for money-service businesses (MSBs).
Each Store has admins + employees; multi-store Owners connect via
invite codes; the platform runs under one Superadmin.

> First time on this codebase? Read [docs/architecture/request-lifecycle.md](docs/architecture/request-lifecycle.md)
> before opening a PR. It traces a request end-to-end through
> ``asgi.py`` → FastAPI → SQLAlchemy → Postgres.

## Stack at a glance

| Layer | Tech | Where |
|---|---|---|
| Browser SPA | React 19, Vite, TanStack Query, React Router 7, react-hook-form + Zod | `frontend/` |
| JSON API | FastAPI on Starlette/ASGI (uvicorn) at `/api/v2/*` | `api/` |
| Database | SQLAlchemy 2.0 (SQLite dev, Postgres prod) + Alembic migrations | `api/Core/Database/`, `alembic/` |
| Billing | Stripe Checkout + Billing Portal + webhooks | `api/Modules/Billing/`, `api/Modules/Webhooks/` |
| Auth | JWT (httpOnly cookie + rotating refresh), password + TOTP + WebAuthn | `api/Modules/Auth/` |
| Observability | Sentry (opt-in via DSN), structlog, X-Request-ID middleware | `api/Core/Observability/` |
| Tests | pytest (~1,770) + Playwright browser smoke (optional) | `tests/`, `tests/smoke/` |

Flask was retired in PRs #546–#550 — ``asgi.py`` is the single
entry point and FastAPI handles every request.

## Quick start

```bash
# 1. Install deps (Python + Node)
pip install -r requirements.txt
( cd frontend && npm install )

# 2. Run the API dev server
uvicorn asgi:asgi_app --reload --port 5000

# 3. Run the SPA in dev mode against the API (optional, hot reload)
cd frontend && npm run dev    # opens :5173, proxies /api/v2 → :5000

# 4. Run tests
pytest tests/                  # full suite (~1,770 tests, ~2 min)
pytest tests/ -x -q            # stop on first failure, quiet
pytest tests/ --ignore=tests/smoke   # skip browser tests if no Chromium

# 5. SPA build + lint
cd frontend && npm run build   # writes to frontend/dist/
cd frontend && npm run lint    # eslint --max-warnings 0
```

First boot seeds a superadmin (`superadmin / super2025!`) and a demo
store admin (`admin / cambio2025!`). Override the seed passwords via
`SUPERADMIN_PASSWORD` / `ADMIN_PASSWORD` env vars in prod.

### Postgres in dev (optional, recommended for DB-heavy work)

The default dev loop runs against a local SQLite file. That's fast
for UI iteration, but SQLite differs from prod Postgres in ways that
silently change behavior: foreign-key enforcement, transaction
isolation, JSON path operators, full-text search syntax. Anything
touching reservations, retention purge, anomaly aggregation, or
report queries should be exercised against Postgres before opening
a PR.

```bash
# 1. Start Postgres in a container
docker compose up -d

# 2. Point the app at it (matches the compose service)
export DATABASE_URL=postgresql://dinerobook:dinerobook@localhost:5432/dinerobook

# 3. Apply the schema
alembic upgrade head

# 4. Run the dev server as usual
uvicorn asgi:asgi_app --reload --port 5000

# 5. When done
docker compose down          # keeps data volume
docker compose down -v       # wipe data volume too
```

The volume `dinerobook-pgdata` persists across `up`/`down` so re-
seeding isn't required on every restart.

## Project layout

```
.
├── asgi.py                 # Production ASGI entrypoint. Mounts the
│                             FastAPI app at /api/v2/*, serves the SPA
│                             shell at /app/*, /static/* assets, and
│                             handles cutover redirects from legacy
│                             paths. gunicorn -k UvicornWorker in prod.
├── api/                    # FastAPI app + modules.
│   ├── main.py             #   create_app() factory + lifespan + router
│   │                       #     registration. Each module's router
│   │                       #     gets mounted here.
│   ├── spa.py              #   Serves the React build from /app/* and
│   │                       #     proxies unknown paths to the SPA shell.
│   ├── PublicRoutes.py     #   Landing, PWA manifest, TV display, pair-
│   │                       #     code API (unauth surfaces).
│   ├── SpaCutover.py       #   Pure function mapping legacy URLs to
│   │                       #     their /app/* equivalents for redirects.
│   ├── Core/               #   Cross-cutting infra:
│   │   ├── Boot.py         #     init_db() + warn_default_seed_passwords
│   │   ├── Bootstrap/      #     Alembic upgrade + safety nets
│   │   ├── Config/         #     Pydantic-settings env loader
│   │   ├── Database/       #     SQLAlchemy engine + SessionLocal + get_db
│   │   ├── Jobs.py         #     RQ-backed enqueue() with sync fallback
│   │   ├── Observability/  #     Sentry / structlog / X-Request-ID
│   │   ├── PasswordHash.py #     stdlib-only werkzeug-compat hasher
│   │   └── RateLimit.py    #     slowapi singleton + decorator
│   └── Modules/            #   One folder per domain (Auth, Admin,
│                           #     Announcements, Audit, BankSync,
│                           #     Batches, Billing, Customers, DailyBook,
│                           #     Dashboard, FeatureFlags, Monthly,
│                           #     Notifications, Owners, Reports,
│                           #     ReturnChecks, Superadmin, Tenancy,
│                           #     Transfers, TVDisplay, Webhooks).
│                           #     Each has Controllers / Services /
│                           #     Repositories / Models / Requests.
├── templates/              # Jinja2 templates — only the public-facing
│                             auth pages (landing, login, signup,
│                             forgot-password, …) + email templates.
│                             Authed surfaces all render from the SPA.
├── static/                 # Design tokens + content/shell stylesheets.
│                             Loaded by both the SPA shell AND the
│                             remaining Jinja templates.
├── frontend/               # React 19 SPA.
│   ├── src/
│   │   ├── routes/         #   One file per page. Each route can have
│   │   │                   #     a co-located <Route>.module.css for
│   │   │                   #     page-specific styles.
│   │   ├── components/     #   ui/ holds the design-system primitives
│   │   │                   #     (one file per component: PageShell,
│   │   │                   #     Card, Button, Alert, KpiCard, …),
│   │   │                   #     plus feature components (AppShell,
│   │   │                   #     UserMenu, SenderAutocomplete, …).
│   │   ├── api/            #   TanStack Query hooks per FastAPI module
│   │   │                   #     + auto-generated openapi.d.ts types.
│   │   └── lib/            #   auth, api client, chart options, …
│   └── public/
├── scripts/                # One-shot CLI scripts (purge_expired_stores,
│                             send_trial_reminders, broadcast_announcement,
│                             backfill_federal_tax, reset_superadmin, …).
├── alembic/                # Schema migrations. Sole source of truth.
├── tests/                  # pytest. Mirrors api/Modules/ for unit
│                             coverage; tests/smoke/ is the Playwright
│                             layer (skipped if Chromium isn't installed).
├── docs/architecture/      # ADRs + runbooks. Start with
│                             request-lifecycle.md.
├── CLAUDE.md               # Engineering invariants. READ THIS before
│                             touching auth / billing / migrations.
├── BACKLOG.md              # Deferred work + "Before going live"
│                             checklist.
├── docker-compose.yml      # Local Postgres for the dev loop (optional).
├── .env.example            # Env-var reference for local setup.
└── render.yaml             # Production service + DB declaration.
```

## "Where do I look to do X?"

| You want to… | Start here |
|---|---|
| **Add a new SPA page** | `frontend/src/routes/NewPage.tsx` (+ co-located `NewPage.module.css` for page-specific styles) + register in `frontend/src/App.tsx` + matching FastAPI module in `api/Modules/<Name>/` (Controllers + Services + Repositories) + TanStack Query hook in `frontend/src/api/<name>.ts`. |
| **Add a new column to an existing table** | Update the SQLAlchemy model under `api/Modules/<Name>/Models/`, then `alembic revision --autogenerate -m "add foo.bar"`. Review the generated migration before committing — backfills + SQLite batch-mode quirks need a human read. |
| **Add a whole new table** | New SQLAlchemy class in the appropriate module's `Models/`. Generate the migration the same way. If it's per-store, ALSO add it to `_STORE_OWNED_MODELS` (in `api/Modules/Billing/Services/retention.py`) or the data-retention purge will leak it. |
| **Add a FastAPI endpoint** | Find or create the module under `api/Modules/<Name>/`. Controllers (FastAPI routers) in `Controllers/`, business logic in `Services/`, DB queries in `Repositories/`, Pydantic schemas in `Requests/`. Register the router in `api/main.py`. |
| **Add a new BI report** | Append an entry to `_BI_REPORTS` in `api/Modules/Reports/Services/__init__.py` (or the equivalent superadmin registry) with the slug + Service function. The SPA's `SuperadminBIDrilldown.tsx` auto-renders any new slug. |
| **Add a new bank-charge auto-rule** | Append to `BUILTIN_BANK_RULES` in `api/Modules/BankSync/Services/builtin_rules.py`. Read the "Bank-charge automation" section of `CLAUDE.md` first — accounts + descriptions are sensitive and a wrong slug misroutes money on live P&L. |
| **Tighten password / 2FA / passkey behavior** | `api/Modules/Auth/Controllers/__init__.py` for the request layer; helpers (`_needs_totp`, etc.) are alongside. Read invariant #13 in `CLAUDE.md` before touching the login state machine. |
| **Change a Stripe webhook reaction** | `api/Modules/Webhooks/Controllers/__init__.py` (ingest + signature verification) + `api/Modules/Billing/Services/webhook.py` (per-event handlers). Pairs with retention reset + referral credits. |
| **Toggle a feature for a single store** | `store_feature_enabled(store, key)` in `api/Modules/FeatureFlags/`. Defaults in `_DEFAULT_FEATURE_FLAGS`. Superadmin UI is at `/app/superadmin/controls` (Features tab). |
| **Audit a superadmin mutation** | `record_audit(action, target_type, target_id, details)` in `api/Modules/Audit/Services/recorder.py` — every mutation route already calls this; new ones MUST. |
| **Move slow work off the request path** | Wrap the call in `api.Core.Jobs.enqueue(fn, *args)`. Sync mode is the default (= direct call); flipping `JOB_QUEUE_ENABLED=1` + setting `REDIS_URL` makes the call go to the RQ worker. See CLAUDE.md invariant #16. |
| **Style something** | Read the "Design system" section of `CLAUDE.md`. Dark-only, neon `#3fff00` is the only saturated color, three fonts. SPA primitives in `frontend/src/components/ui/` (one file per component). Page-specific styles go in a co-located `<Route>.module.css`. |
| **Add a test** | Mirror the path: `api/Modules/X/Services/foo.py` → `tests/Modules/X/test_foo.py`. Browser smoke tests go in `tests/smoke/test_chrome_smoke.py`. Fixtures live in `tests/conftest.py` (+ `tests/smoke/conftest.py` for browser layer). |

## Common workflows

### Run a single test fast

```bash
pytest tests/test_admin_settings_spa.py -v
pytest tests/test_admin_settings_spa.py::test_specific_case -v
```

`tests/conftest.py` downgrades password hashing to 1 PBKDF2 iteration
for the suite so test setup stays under a few seconds.

### Apply a schema migration

Alembic is the sole source of schema truth. Generate a revision
with:

```
alembic revision --autogenerate -m "add foo.bar"
```

Review the generated file under `alembic/versions/` before
committing — autogenerate handles most things but misses data
backfills and SQLite batch-mode quirks. `init_db()` runs
`alembic upgrade head` on every boot, so production picks up
the new revision on the next deploy.

**Never drop a column from a running database** — rename +
backfill across a follow-up deploy if you truly need to remove
one. See [`docs/architecture/migrations.md`](docs/architecture/migrations.md)
for the full workflow.

### Reset the superadmin password (prod)

```
python -m scripts.reset_superadmin --reset-2fa
```

Runs on the Render shell. `--reset-2fa` also wipes TOTP if the
recovery codes are lost. The forgot-password email flow is
deliberately disabled for the superadmin role (CLAUDE.md
invariant #10).

### Purge expired stores (data retention)

```
python -m scripts.purge_expired_stores
```

Cascades through `_STORE_OWNED_MODELS` before deleting the `Store`
row. Add any new per-store model to that list. Render's cron
service runs this daily at 03:15 UTC.

### Backfill historical federal_tax

```
python -m scripts.backfill_federal_tax              # dry-run
python -m scripts.backfill_federal_tax --commit     # write
```

Recomputes `Transfer.federal_tax` on every row via the same
helper the create/edit routes use. Idempotent.

## Production deploy

The primary service is `dinerobook` on Render, hostnamed at
`https://dinerobook.com`. Database is `dinerobook-db` (Postgres),
linked via `fromDatabase:` in `render.yaml`. Every push to `main`
auto-deploys.

Required environment variables (set in the Render dashboard):

| Env var | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing fallback when `AUTH_JWT_SECRET` is unset. |
| `AUTH_JWT_SECRET` | Dedicated HS256 secret for JWT issuance. |
| `DATABASE_URL` | Postgres connection string (Render injects via `fromDatabase:` in `render.yaml`). |
| `STRIPE_SECRET_KEY`, `STRIPE_BASIC_PRICE_ID`, `STRIPE_PRO_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` | Stripe Checkout + webhook verification + Financial Connections. |
| `APP_BASE_URL` | `https://dinerobook.com` — used by SMTP / Stripe URL builders + WebAuthn. |
| `WEBAUTHN_RP_ID` | `dinerobook.com` — pins WebAuthn Relying Party ID. Changing invalidates every existing passkey. |
| `SUPERADMIN_PASSWORD`, `ADMIN_PASSWORD` | Override the dev seed passwords in prod. |
| `SENTRY_DSN` (Python), `VITE_SENTRY_DSN` (SPA) | Optional — error tracking. |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | Transactional email (password reset, announcements, locked-day digest). |
| `RATELIMIT_STORAGE_URI` | Optional Redis URL for slowapi to share buckets across web workers. In-memory default works for single-worker. |
| `REDIS_URL`, `JOB_QUEUE_ENABLED` | Optional — when both set, `api.Core.Jobs.enqueue` pushes work to an RQ worker. Otherwise sync. See CLAUDE.md invariant #16. |

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
  — end-to-end trace of a request through asgi.py → FastAPI →
  SQLAlchemy → Postgres, plus observability hooks.
* [`docs/architecture/migrations.md`](docs/architecture/migrations.md)
  — Alembic workflow.
* [`docs/architecture/deployment.md`](docs/architecture/deployment.md)
  — Render deploy runbook: env-var checklist, secret rotation,
  backup verification, incident playbook.
* [`docs/architecture/component-catalog.md`](docs/architecture/component-catalog.md)
  — Flat reference for every SPA primitive (`PageShell`, `Card`,
  `KpiCard`, `Button`, etc.) + every `.ds-*` motion class.

## Contributing

* Stay on a feature branch (`claude/<short-slug>` is the convention).
* One commit per coherent change; commit messages explain **why**,
  not what.
* `pytest tests/` + `cd frontend && npm run build && npm run lint`
  before pushing. CI runs both.
* PRs go to `main`. Don't push to `main` directly.
* Don't bypass hooks (`--no-verify`, `--no-gpg-sign`) unless asked.
