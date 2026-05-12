# DineroBook — Request Lifecycle

> Last updated: 2026-05-12
> Audience: anyone touching auth, routing, observability, or the
> Flask/FastAPI strangler split.

## Why this doc exists

The codebase is mid-migration: legacy Flask Blueprints serve the
HTML / form-POST surface, FastAPI under `/api/v2/*` serves the SPA.
Both share one process, one DB connection pool, and one Sentry +
structured-logs pipeline. New contributors land in this stew and
ask the same question — "where does a request actually go?" — so
this doc traces it end-to-end.

If you change auth, observability, or the dispatcher routing, **come
back here and update this doc.** Out-of-date diagrams are worse than
no diagram.

## Bird's-eye view

```
   Browser (SPA / classic form)
      │
      ▼
   Cloudflare DNS (dinerobook.com → Render edge)
      │
      ▼
   Render edge (TLS termination, HTTP/2)
      │
      ▼
   gunicorn  -k uvicorn.workers.UvicornWorker
      │   (Render service "dinerobook", spawned per render.yaml)
      ▼
   asgi.py  →  async def asgi_app(scope, receive, send)
      │            │
      │            ├─ scope["type"] == "lifespan"
      │            │       → forward to FastAPI for startup/shutdown
      │            │
      │            ├─ path starts with /api/v2/...
      │            │       → strip mount prefix
      │            │       → FastAPI native ASGI  (api/main.py)
      │            │
      │            └─ everything else
      │                    → a2wsgi WSGIMiddleware
      │                    → Flask Blueprint  (blueprints/*.py)
      ▼
   SQLAlchemy session (one db = Flask-SQLAlchemy 3.1; FastAPI
   modules pull `db.session` from app.py too)
      │
      ▼
   PostgreSQL ("dinerobook-db" on Render; SQLite in dev/CI)
```

That's the happy path. The rest of this doc fills in what happens
at every arrow.

## The dispatcher: `asgi.py`

Production runs `gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker`.
`asgi_app` is a hand-rolled ASGI router (≈90 lines). It exists to
**bypass the leaky `a2wsgi.ASGIMiddleware` bridge** that the original
Flask-dispatcher chain used — that bridge was accumulating asyncio
tasks in a background thread and causing `WORKER TIMEOUT` crashes on
`/api/v2/*` requests in production.

Routing rules:

| Scope type | Path | Routed to |
|---|---|---|
| `lifespan` | n/a | FastAPI's lifespan handlers |
| `http` / `websocket` | starts with `/api/v2` | FastAPI ASGI direct (`api/main.py`) |
| `http` / `websocket` | everything else | Flask WSGI via `a2wsgi.WSGIMiddleware` |

For `/api/v2/*` requests, `asgi.py` strips the mount prefix (FastAPI
routes are declared relative — `/health`, not `/api/v2/health`) and
sets `root_path` on the scope so OpenAPI URLs still reflect the
mount point.

**Why two app objects?** Flask owns the legacy HTML / form-POST
surface; FastAPI owns the SPA's JSON API. Both share one Python
process, one DB pool, and (importantly) one Sentry / structured-logs
pipeline so traces stay coherent across the boundary.

## Flask side — Blueprint routing

Once `asgi.py` decides a request is not `/api/v2/*`, it hands the
ASGI scope to `a2wsgi.WSGIMiddleware`, which converts it back to a
WSGI environ and invokes the Flask app from `app.py`.

`app.py` is small now (≈7,500 lines after the D2 split): models,
helpers, decorators, the SPA fallback routes, and the two webhooks.
**Every form-handling route lives under `blueprints/`** — see the
table at the top of `BACKLOG.md` D2 for the full list.

A typical request flow:

```
WSGI request
   │
   ▼  app.py middleware (Flask global)
   │  - inject_trial_context        (context processor)
   │  - X-Request-ID install        (api/Core/Observability)
   │  - structlog contextvars bind
   │
   ▼  Blueprint dispatch
   │  e.g. "POST /admin/settings" →
   │       blueprints/admin_settings_form.view
   │
   ▼  Decorator chain (executed in declared order, top-down)
   │  @admin_required → @login_required → @csrf_protect
   │  (each can short-circuit with a redirect / 403)
   │
   ▼  Handler body
   │  - validates request.form
   │  - calls helper(s) imported lazily from app.py
   │  - db.session.commit()
   │  - flash() + redirect()  OR  render_template()
   │
   ▼  Flask response → a2wsgi → asgi.py → uvicorn → client
```

Notable Flask invariants (full list in `CLAUDE.md`):

* `db.session.get(Model, id)` — never `Model.query.get(id)`.
* Every superadmin mutation calls `record_audit(...)`.
* Trial-exempt endpoints are enumerated in `_TRIAL_EXEMPT` and use
  blueprint-namespaced names (e.g. `billing.subscribe`).

## FastAPI side — module routing

`api/main.py` builds a `FastAPI()` app on import. It registers ~14
module routers (Reports, Customers, Transfers, BankSync, Auth,
DailyBook, Batches, Monthly, Admin, ReturnChecks, Owners,
Superadmin, Billing, Announcements, FeatureFlags, …) each at its
own prefix. The router list grows by one module per PR during the
strangler-fig migration.

The per-module layout (`api/Modules/<Name>/`):

```
Controllers/     — FastAPI routers; HTTP shape only (no business
                   logic).
Services/        — pure functions. Take a SQLAlchemy session +
                   plain args; return plain values. Unit-tested
                   without HTTP.
Repositories/    — SQLAlchemy queries. Single-responsibility:
                   "fetch this thing", "insert that row".
Models/          — Pydantic schemas for request/response (and
                   sometimes thin re-exports of SQLAlchemy ORM
                   classes from app.py).
```

A typical FastAPI request flow:

```
ASGI request (already inside FastAPI)
   │
   ▼  FastAPI middleware stack (set up in api/main.py)
   │  - RequestIDMiddleware (api/Core/Observability)
   │  - structlog contextvars bind
   │  - SentryAsgiMiddleware (only if SENTRY_DSN set)
   │
   ▼  Route resolution
   │  e.g. "GET /api/v2/transfers/recent" →
   │       api/Modules/Transfers/Controllers.recent_transfers
   │
   ▼  Dependency injection
   │  - bearer_jwt() → decode JWT, return identity
   │  - get_db_session() → yields a SQLAlchemy session
   │  - role/plan gates ride on top of bearer_jwt
   │
   ▼  Controller body
   │  - Pydantic-validates the request (path/query/body)
   │  - calls one Service function with explicit args
   │  - returns a Pydantic response model
   │
   ▼  FastAPI serializes → asgi.py → uvicorn → client
```

Notable FastAPI invariants:

* **Never put `/api/v2` in a FastAPI route declaration.** The mount
  carries it. Route paths are relative (`/health`, not
  `/api/v2/health`).
* All endpoints live under `/api/v2/*`. The SPA hits relative URLs;
  the dispatcher's mount prefix is the source of truth.
* Auth is Bearer JWT (HS256). Tokens are minted by Flask's
  `/login/2fa/finish` (legacy) and by `api.Modules.Auth.Controllers`
  (new); both produce the same shape so the SPA can use either.

## Observability — Sentry + structured logs + request IDs

All three pieces live under `api/Core/Observability/` and initialise
once at process boot.

### Request IDs

Every inbound request gets a stable ID:

1. `X-Request-ID` header from the client (if present), OR
2. A fresh UUIDv4 (if absent).

The ID is bound to the structlog contextvars **for the duration of
the request** so every `log.info(...)` call in the stack includes
`request_id=…` automatically. It's also echoed in the response
header so the client can correlate.

Installed on both sides:

* **Flask:** `install_request_id(flask_app)` registers a
  `before_request` hook + `after_request` hook.
* **FastAPI:** `RequestIDMiddleware` is added to the FastAPI app
  in `api/main.py` before any router includes.

### Structured logs

`init_logging()` configures structlog + stdlib logging. The encoder
flips based on `settings.log_format`:

* **Production (`json`):** every line is a single JSON object with
  `ts`, `level`, `event`, `request_id`, plus any contextual keys
  the call site attached.
* **Dev (`console`):** the same fields rendered with colour and
  indentation for readability.

Both modes share the same processor chain so log fields are
consistent regardless of encoder. **Don't** call `print()` or the
plain `app.logger.info(...)` — use `from api.Core.Observability
import get_logger; log = get_logger(__name__)`.

### Sentry

`init_sentry()` is a no-op when `settings.sentry_dsn` is empty
(local dev, CI). When the DSN is present the SDK installs
integrations for Flask, FastAPI, SQLAlchemy, and stdlib logging
exception capture. Both apps share one DSN so the Sentry UI
shows traces that cross the Flask/FastAPI boundary as one event.

The React SPA has its own Sentry init (`frontend/src/lib/sentry.ts`)
keyed by a separate env var (`VITE_SENTRY_DSN`); browser errors
and API failures still get correlated via the `X-Request-ID` header
that the SPA forwards.

## Database — one pool, two app instances

Both Flask and FastAPI talk to the **same SQLAlchemy session** via
Flask-SQLAlchemy 3.1's `db` object exported from `app.py`. FastAPI
module Services accept the session as an explicit argument:

```python
def recent_transfers(db: Session, store_id: int, limit: int) -> list[TransferRow]:
    return db.query(Transfer).filter_by(...).order_by(...).limit(limit).all()
```

FastAPI Controllers wire `db` via a dependency:

```python
def get_db_session():
    return db.session  # bound to the request via Flask-SQLAlchemy
```

Schema lives entirely in `app.py` model classes. `_ADDED_COLUMNS` is
still primary for additive migrations; Alembic baseline migration
`99691740424c_baseline_2026_05` pins the current schema for the
eventual cutover (BACKLOG D4 phase 1 shipped).

`purge_expired_stores()` is the only destructive query — it
cascades through `_STORE_OWNED_MODELS` before deleting a Store row.
Add new per-store models to that list or data retention will leak.

## SPA → Flask vs SPA → FastAPI

The React SPA is mounted at `/app/*` (Flask catch-all serves the
bundle). It talks to two surfaces depending on the operation:

| Operation | Endpoint | Why |
|---|---|---|
| Read data (lists, KPIs, charts) | `GET /api/v2/<module>/*` | FastAPI — typed, fast, JWT-only |
| Mutate data (POST/PATCH/DELETE) | `POST /api/v2/<module>/*` | FastAPI where the module has migrated |
| Mutate data (still on Flask) | `POST /<legacy-path>` | Flask Blueprint — usually a 30x redirect-back-to-SPA |
| Auth bootstrap (login → JWT) | `POST /api/v2/auth/login` | FastAPI |
| Auth bootstrap (passkey, TOTP) | Flask `auth.*` Blueprint | Mounted at `/login/passkey/*`, `/login/2fa/*` for cookie compat |
| File download (tax pack zip, CSVs) | `GET /<legacy-path>` | Flask Blueprint streams the file directly |
| Webhook ingest | `POST /webhooks/{stripe,resend}` | Flask — webhook contract predates FastAPI |
| SPA bundle, static assets | `GET /app/*`, `GET /static/*` | Flask catch-all + Flask static handler |

The split is intentional and temporary. D3 in the BACKLOG plans the
full cookie-session retirement; once that ships, the Flask side
collapses to webhook ingest + the SPA shell.

## Common debugging tasks

* **"Where does request X go?"** Grep for the URL path in
  `blueprints/` first. If no match, grep `api/Modules/*/Controllers/`.
  If still no match, the request 404s — check `templates/base.html`
  for a typo in a `url_for(...)` call.
* **"Why is this slow?"** Sentry's performance tab plus the per-
  request structlog output (filtered by `request_id`) show the
  full DB-call profile. The slow culprit is usually an N+1 in a
  Service that loops over rows fetching related objects one at a
  time.
* **"Why did this 500?"** Sentry receives the exception with the
  bound `request_id` so you can grep the structlog output for the
  preceding context. The Sentry breadcrumb chain also captures
  the SQL statements that ran before the crash.
* **"Why did this redirect twice?"** Almost always a Blueprint
  endpoint-name typo. Use `app.url_map.iter_rules()` to dump the
  full endpoint registry, then check the failing `url_for(...)`
  callsite against it.

## Diagrams that need rewriting if you change…

* `asgi.py` routing → "Bird's-eye view" + "The dispatcher" sections.
* Blueprint registration order in `app.py` → "Flask side" table.
* `api/main.py` router list → "FastAPI side" module list.
* `api/Core/Observability/*.py` → "Observability" section.
* Stripe / Resend webhook flow → "SPA → Flask vs FastAPI" table.

Out-of-date diagrams here will mislead — keep them honest.
