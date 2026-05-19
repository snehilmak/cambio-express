# Backlog

Tracked work we're deferring. Anything in **Before going live** must be
closed out before public / paid launch; the other sections can happen on
any cadence.

## Flask removal — complete

**Status (May 2026): Flask is fully removed.** Production runs on
``asgi:asgi_app`` only — FastAPI + Starlette + Pure SQLAlchemy.
``app.py``, ``api/Flask/``, ``blueprints/``, ``flask`` /
``Flask-WTF`` / ``Flask-Limiter`` / ``werkzeug`` are all gone from
the repo and the dep tree.

PRs that closed out the multi-month arc:

* **#546** — delete dead Flask-Limiter / CSRF / session /
  context-processors (no live consumers after blueprint migrations)
* **#547** — migrate 65 CSV report routes to FastAPI; SPA uses
  fetch + blob download for JWT-authed CSV exports
* **#548** — move SPA-cutover redirects + error handlers off Flask
  into the ASGI layer
* **#549** — migrate test fixtures from ``Flask.test_client`` to
  ``httpx + ASGITransport``
* **#550** — delete ``app.py``, ``blueprints/``, ``api/Flask/``;
  drop ``flask`` + ``pytest-flask`` from requirements
* **#551** — sweep test suite from ``Model.query.X`` to
  ``db.session.query(Model).X`` (SQLA 2.0 invariant #11)
* **#552** — trim residual Flask scaffolding from the conftest
  (CSRF, logger, root_path, config shims)
* **#553** — replace 1030 ``flask_app.app_context()`` blocks with
  honestly-named ``db_session()`` context manager
* **#554** — collapse ``tests/_db_shim.py`` + ``tests/_models.py``
  into ``tests/_app.py``
* **#555** — replace bare ``TestClient(api_app)`` with yield
  fixtures; drop the autoclose monkey-patch
* **#556** — drop ``werkzeug`` dep; replace with stdlib-only
  ``api/Core/PasswordHash.py`` that reads/writes the same
  ``scrypt:N:r:p$salt$hex`` format (no migration, no forced
  password rotation)

## Post-SPA-migration cleanup (new — work top-down)

The SPA migration finished in May 2026 (PRs #395–#419). Every landing
+ all 35 report drilldowns are on React. This section captures the
follow-up work surfaced during + immediately after that migration. PRs
should reference the item number for traceability.

### A. UX polish (USER-VISIBLE, do these first)

The migration was scope-controlled — get every surface onto React,
ship redirects, retire templates. Visual fit-and-finish was
deliberately deferred. None of these change behavior; they're all
the kind of thing that makes the product feel premium vs. functional.

- [x] **A1. Animations & transitions per CLAUDE.md design system.**
      Landed in two waves:
      - `frontend/src/components/ui/ui.css` (PR #431) — `.ds-card`
        hover lift, `.ds-btn` scale-press + hover tint, `.ds-input`
        focus glow, `.ds-link` underline reveal, `.ds-page`
        fade-up entry, `.ds-skel` shimmer, `.ds-pill--pulse`.
        Every `<Card>` / `<Button>` / `<Input>` / `<PageShell>` in
        `components/ui/index.tsx` opts in by default.
      - Motion fallback (this PR) — global `transition` baseline on
        every raw `<button>`/`<a>`/`<input>`/`<select>`/`<textarea>`
        so pages with hand-rolled inline-style elements still
        animate. Raw buttons get `opacity` shift on hover/active.
        New `.ds-popover` class for dropdown fade-scale-in,
        applied to `SenderAutocomplete`.
      Honors `prefers-reduced-motion: reduce` via the global rule
      in `frontend/src/styles.css`.
- [x] **A2. Padding / spacing consistency.** Landed — `<PageShell>`,
      `<PageHeader>`, `<Section>`, `<Card>`, `<KpiCard>`,
      `<KpiGrid>`, `<Table>` live in
      `frontend/src/components/ui/index.tsx`. Inline `pageStyle` /
      `cardStyle` blocks were swept (PR #439).
- [x] **A3. Typography consistency.** Landed alongside A2 — type
      ramp lives in `static/design-tokens.css` (`--db-text-*`) and
      `frontend/src/lib/typography.ts`.
- [x] **A4. Empty states.** `<EmptyState>` ships in
      `frontend/src/components/ui/` (PR #431).
- [x] **A5. Loading skeletons.** `<TableSkeleton>` + `<Loading>`
      ship in `frontend/src/components/ui/` (PR #431).
- [x] **A6. Error states.** `<ErrorState>` ships with a retry button
      + route-level `<RouteErrorBoundary>` (PRs #431, #435).

### B. Missing charts on superadmin reports

I migrated owner dashboards + store detail with chart.js but the 20
superadmin BI reports go through a generic auto-rendering
component (`SuperadminBIDrilldown.tsx`) that ONLY shows KPIs + a
table. The user expected charts because the legacy Jinja superadmin
reports rendered ApexCharts inline.

- [x] **B1. Time-series chart on superadmin reports.** Landed
      (PR #423) — `SuperadminBIDrilldown.tsx` auto-detects date-like
      keys and renders a chart.js Line chart above the table for
      reports including `signup-funnel`, `dau-mau`, `mrr-arr`,
      `churn-cohort`, `login-activity`, `webhook-health`.
- [x] **B2. Bar charts** for categorical breakdowns. Landed
      alongside B1 (PR #423) using the same auto-detection heuristic.
- [x] **B3. Owner dashboard chart hover tooltips + axis formatting.**
      Landed (PR #436) — shared `moneyChartOptions` / `countChartOptions`
      helpers in `frontend/src/lib/chartOptions.ts` give consistent
      tooltips, currency Y-axis, gridline opacity, etc.
- [x] **B4. Add chart toggle.** Landed —
      `SuperadminBIDrilldown.tsx` now renders a 3-state segmented
      control (Chart / Table / Both) above the chart, defaulting
      to "Both". User's choice persists to localStorage per-report
      slug (`dinerobook.bi.view-mode.<slug>`). When a report has
      no detectable chart shape (no numeric column or no
      date/string identity column) the toggle is hidden and the
      view falls back to table-only.

### C. SPA architectural cleanup

- [x] **C1. Code-split the bundle by route.** Landed (PR #428) —
      every `<Route element=>` now uses `lazy(() => import())` with
      a shared `<Suspense fallback={<Loading />}>` wrapper.
- [x] **C2. Move inline styles to CSS Modules or Vanilla Extract.**
      Landed in a long sweep across PRs #563-#581 (Apr–May 2026).
      Every route (33) and every SPA component (4) now uses kit
      primitives from `components/ui/` plus a co-located
      `<Route>.module.css` for page-specific styles. The
      `components/ui/` kit was also split into one-file-per-
      component (PR #569) to match modern design-system
      conventions. Two new kit primitives — `<Alert>` and
      `<Field error= hint=>` — absorbed the most-duplicated
      patterns. The codebase no longer contains a single
      page-level inline `const xStyle: CSSProperties = {...}`
      block. Pattern documented in CLAUDE.md under "Inline styles
      vs CSS Modules" and "Component reuse".
- [x] **C3. Shared `<Page>` layout component.** Landed (PR #439) —
      `<PageShell>` / `<PageHeader>` / `<Section>` enforce the
      padding scale on every route.
- [x] **C4. Per-route error boundaries.** Landed (PR #435) —
      `<RouteErrorBoundary>` (Sentry-aware) wraps every route's
      `<Outlet />`.

### D. Backend cleanup (legacy Flask half)

Most of this section closed out when Flask was retired (see the
top-level "Flask removal — complete" entry). What's left is
infrastructure that's still relevant in the FastAPI-only world.

- [x] **D1. Delete the 16 remaining Jinja templates that are no
      longer rendered.** Landed (PR #424).
- [x] **D2. Split `app.py` into Flask Blueprints.** Done as an
      intermediate step; the entire monolith + all blueprints
      were retired in PRs #546–#550 (see top of file).
- [x] **D3. Retire `@login_required` cookie-session path.**
      Closed by the Flask removal — the session-cookie auth path
      no longer exists. JWT in the Authorization header is the
      sole auth surface on `/api/v2/*`.
- [x] **D4. Adopt Alembic.** Landed (PR #430) — baseline migration
      `99691740424c_baseline_2026_05` pins the current schema;
      `_ADDED_COLUMNS` still primary but Alembic now available for
      drops / renames / backfills.
- [~] **D5. Background job queue** for Stripe webhooks, email send,
      ACH retries, retention purge. RQ + Redis is the lowest-cost
      path on Render. **Partial — scaffolding + first migration
      shipped, worker activation pending.**
      Done so far:
      * ``api/Core/Jobs.py`` — ``enqueue(fn, *args)`` wrapper with
        sync fallback (default) + RQ-backed queued mode (when
        ``JOB_QUEUE_ENABLED=1`` + ``REDIS_URL`` are set).
        ``tests/Core/test_jobs.py`` covers both modes.
      * ``/forgot-password`` SMTP send migrated — the route now
        ``enqueue``s ``send_password_reset_email(user_id,
        raw_token)``. Sync mode keeps prod behavior bit-for-bit
        identical until queuing is activated.
      * ``render.yaml`` — worker block staged commented with a
        4-step activation runbook embedded in the comments.
      Remaining (deferred — not blocking; the sync fallback keeps
      every existing route working at current latency):
      * Provision a managed Redis (Render or Upstash).
      * Set ``REDIS_URL`` + ``JOB_QUEUE_ENABLED=1`` on both web +
        worker services in the Render dashboard.
      * Uncomment the ``- type: worker`` block in ``render.yaml``
        + sync the blueprint.
      * Migrate the next SMTP / Stripe-SDK call sites (trial
        reminders, locked-day digest, announcement broadcast
        already migrated).
      Owner action when ready to activate: follow the 4-step
      runbook embedded as comments above the worker block in
      ``render.yaml``. Until then, the system is fully
      functional — D5 is a latency win, not a correctness fix.
- [x] **D6. Edge rate limiting.** Landed — `slowapi` 0.1.9 on every
      auth route + the two webhooks. The Flask-Limiter twin is
      gone (Flask itself is gone). Storage shared across workers
      via `RATELIMIT_STORAGE_URI` (in-memory in dev, Redis in prod);
      `RATELIMIT_ENABLED` is the kill-switch. Tunings:
      - Auth burst: 10/min + 50/hour per IP on
        `/api/v2/auth/login`.
      - Forgot/reset password: 5/min + 20/hour per IP (lower
        because each request triggers an SMTP send).
      - Signup: 5/hour + 20/day per IP (signup is rare; an
        attacker minting stores at scale is the threat).
      - Webhooks (`/webhooks/{stripe,resend}`): 120/min per IP.
        Signature verification is the real defense; this is just a
        flood ceiling.
      Regression guards in `tests/test_rate_limiting.py`.

### E. Observability + ops

- [x] **E1. Sentry on Python + React.** Landed (PR #429) — opt-in
      via DSN env vars.
- [x] **E2. Structured JSON logs.** Landed (PR #429) — structlog +
      X-Request-ID middleware in `api/Core/Observability/`.
- [x] **E3. Build SPA in CI.** Landed (PR #426).
- [x] **E4. Coverage tracks `api/` too.** Landed (PR #425) —
      `coverage --source=app,api`.
- [~] **E5. mypy strict on `api/Modules/*`** — partial.  Ratchet
      pattern lives in ``pyproject.toml`` — strict on a curated
      list of files; CI re-runs the same command (``python -m
      mypy``) on every push.  See CLAUDE.md "mypy — strict
      ratchet" for the workflow to add a file.
      Currently in the ratchet: **74 files clean** across
      ``api/Core``, ``Admin``, ``Announcements``, ``Audit``,
      ``Auth``, ``BankSync``, ``Batches``, ``Billing``,
      ``Customers``, ``DailyBook``, ``Dashboard``, ``Monthly``,
      ``Notifications``, ``Reports``, ``Superadmin``,
      ``TVDisplay``, ``Tenancy``, ``TimeClock``, ``Transfers``.
      Mostly Repositories, Requests (Pydantic schemas), and
      Services that don't mutate ORM rows.
      Switched ``api/Core/Database/session.py`` to the
      SQLAlchemy 2.0 ``class Base(DeclarativeBase)`` style —
      eliminated the "cannot subclass Any" error on every
      model declaration (5+ Models files immediately gained
      proper class-level typing).
      Remaining blockers for full strict coverage:
        * Controllers — ``@router.<verb>(...)`` decorators trip
          ``untyped-decorator`` on the current FastAPI stubs.
          Pin a newer FastAPI or selectively
          ``# type: ignore[misc]``.
        * Services that write to ORM rows — SQLAlchemy 1.x
          ``Column(...)`` declarations type assignments as
          ``Column[T]`` instead of ``T``. Migrating to
          ``Mapped[T] = mapped_column(...)`` is its own
          multi-PR effort.
- [x] **E6. eslint --max-warnings 0** in CI on frontend. Landed
      (PR #426).
- [x] **E7. Generate TS types from FastAPI OpenAPI.** Landed
      (PR #558). `openapi-typescript` runs via
      `npm run generate-types`; the SPA imports request/response
      shapes from `frontend/src/api/openapi.d.ts`. Regenerate after
      every Pydantic-schema edit (no CI gate — drift surfaces at
      the call site).
- [ ] **E8. E2E smoke tests** with Playwright on the SPA. Partial:
      `tests/smoke/test_chrome_smoke.py` covers chrome regressions
      (every authed route loads with no JS errors, the topbar
      avatar-dropdown opens, +New Transfer entry-point clickable,
      return-checks list has an Edit affordance). Still missing:
      end-to-end **flow** tests — full login → log a transfer →
      see it in the list → run a report — and CI wiring so the
      browser layer runs on every PR, not just locally when
      Chromium is installed.

### F. Documentation

- [x] **F1. `docs/architecture/` ADR index.** Landed.
      - [`README.md`](docs/architecture/README.md) — index + format spec.
      - [`ADR-001`](docs/architecture/ADR-001-spa-migration.md): SPA
        migration recap (ACCEPTED — executed).
      - [`ADR-002`](docs/architecture/ADR-002-jwt-only-auth.md):
        JWT-only auth (PROPOSED — tracks D3).
      - [`ADR-003`](docs/architecture/ADR-003-background-job-queue.md):
        Background job queue / RQ + Redis (PROPOSED — tracks D5).
      - [`ADR-004`](docs/architecture/ADR-004-alembic-adoption.md):
        Alembic adoption (PROPOSED — tracks D4).
- [x] **F2. Request-lifecycle doc.** Landed —
      [`docs/architecture/request-lifecycle.md`](docs/architecture/request-lifecycle.md).
      Traces a request end-to-end from Cloudflare → Render edge
      → gunicorn-uvicorn → `asgi.py` dispatcher → Flask Blueprint
      OR FastAPI module → SQLAlchemy → Postgres. Covers the
      observability layer (Sentry, structured logs, request-ID
      middleware on both Flask and FastAPI sides), the SPA →
      Flask vs SPA → FastAPI routing split, and common debugging
      tasks.
- [x] **F3. Frontend component catalog.** Landed at
      [`docs/architecture/component-catalog.md`](docs/architecture/component-catalog.md).
      Flat reference for every primitive in
      `frontend/src/components/ui/index.tsx` (layout, forms,
      tables, states, buttons, pills, tokens, motion classes)
      with usage notes + a "where to add new ad-hoc styling"
      decision tree. Storybook-as-screenshots is still nice-to-
      have but the markdown reference is the
      first-day-onboarding artifact.
- [x] **F4. Onboarding README.** Landed —
      [`README.md`](README.md). Covers stack-at-a-glance,
      quick-start commands, project layout, a "where do I look
      to do X?" table for the common new-route / new-column /
      new-report / new-rule cases, common workflows
      (single-test run, superadmin password reset, data-retention
      purge), production env vars, and cross-links to
      `CLAUDE.md`, `BACKLOG.md`, and the `docs/architecture/`
      ADRs + runbooks.

### How to use this list

- Cross out items as PRs ship (`- [x]`).
- Each PR should reference the item number in its description (e.g.
  "Closes A1, A2 from BACKLOG.md").
- A items are user-visible and should ship first.
- B items are user-visible and were a surfaced gap from the
  migration — chart.js is in the bundle, the rendering plumbing
  just doesn't fire on superadmin reports yet.
- C/D items are internal but high-leverage.
- E/F items are ongoing — don't block on them, but never let them
  fall to zero.

## Architecture roadmap (priority-ordered)

Honest review of the SPA migration architecture. Top of the list = highest
impact ÷ effort. Numbers are an estimate.

### P0 — do before public launch
1. [ ] **Cookie-based JWT** (httpOnly + Secure + SameSite=Strict) instead
       of localStorage. Closes the XSS-exfil risk — XSS would be able to
       read the access token from `localStorage` today. With Flask gone
       there's no "share with legacy Flask" angle; the only audience is
       the React SPA. ~1 PR.
2. [ ] **Refresh tokens.** Today access tokens are 30 min with no refresh
       — users get bumped mid-workflow. Add `/auth/refresh` endpoint +
       rotation; SPA fetches a new access token before the old one
       expires. ~1 PR.
3. [x] **CI builds the SPA.** Landed (PR #426). `npm ci && npm run lint
       --max-warnings 0 && npm run build` runs in `.github/workflows/
       ci.yml`; a TypeScript regression fails the PR.
4. [x] **Sentry + structured (JSON) logging.** Landed (BACKLOG E1 / E2,
       PR #429). Sentry Python + React opt-in via DSN env vars;
       structlog with X-Request-ID middleware in
       `api/Core/Observability/`.

### P1 — do before/during full SPA cutover
5. [x] **Coverage tracks `api/` too.** Landed in PR #550 — coverage
       source is now `--source=api` (app.py is gone). Total coverage
       is ~93% as of the last run.
6. [ ] **Generate TS types from FastAPI OpenAPI schema.**
       `frontend/src/api/*.ts` has hand-written interfaces mirroring
       `Requests/*.py` Pydantic — drift is inevitable. Add
       `openapi-typescript` to the SPA build, single source of truth.
       ~1 PR.
7. [x] **Retire the WSGI-wraps-ASGI bridge.** Closed by the Flask
       removal (PR #550). `asgi.py` is the production entrypoint —
       FastAPI runs as native ASGI under uvicorn; no a2wsgi anywhere
       in the request path. The SPA-cutover flag (`SPA_CUTOVER_ENABLED`)
       is also gone; cutover redirects live in the ASGI router
       (`api/SpaCutover.py`).

### P2 — quality of life as the codebase grows
8. [x] **Alembic for migrations.** Landed (PR #430). Baseline migration
       `99691740424c_baseline_2026_05` pins the current schema;
       `_ADDED_COLUMNS` is now a safety net rather than the primary
       schema mechanism.
9. [ ] **Shared SPA component library.** Every route file re-declares
       `cardStyle`, `inputStyle`, `pageStyle`, `pagerBtn`, etc. (~200
       lines of token boilerplate per route). Extract `<Card>`,
       `<Pill>`, `<EmptyState>`, `<Pager>`, `<Field>` into
       `frontend/src/components/`. Big readability win, no behavior
       change. ~1 PR.
10. [ ] **`react-hook-form` + Zod for forms.** Hand-rolled `useState`
       forms work for now; transfers has 10+ fields and the
       validation/dirty/error mapping bugs will start. Zod schemas
       can be generated from OpenAPI too — composes with #6. ~1 PR.

### P3 — defer until traffic / scale
11. [x] **Postgres in dev** (docker-compose). Landed — see the
       "Postgres in dev (optional)" block in `README.md` plus the
       `docker-compose.yml` at the repo root. Postgres 16-alpine
       bound to `127.0.0.1:5432`, persistent volume, healthcheck.
       Opt-in via `DATABASE_URL=postgresql://...`; the default
       dev loop and CI keep running on SQLite for speed.
12. [x] **Code-split the SPA.** Landed (BACKLOG C1, PR #428) —
       every `<Route element=>` uses `lazy(() => import())` with
       a shared `<Suspense fallback={<Loading />}>` wrapper, so
       each route ships as its own chunk. Verified by the per-
       route filenames in `dist/assets/` on every build.

## Before going live (public / paid launch)

> Items marked **(ops)** can't be closed by a code PR — they're
> Render dashboard or vendor-portal actions. Owner of each ops
> item lives in [`docs/architecture/deployment.md`](docs/architecture/deployment.md).

- [ ] **SMTP configured** (ops) — set `SMTP_HOST` / `SMTP_USER` /
      `SMTP_PASS` (optionally `SMTP_PORT` / `SMTP_FROM`) on Render
      → Environment so `/forgot-password` actually emails. Gmail +
      an app password works. Until this is set, reset URLs are
      logged at WARNING level and superadmin has to relay them
      manually. See [`deployment.md`](docs/architecture/deployment.md)
      §1 step 4 for the Gmail walkthrough.
- [x] **Error tracking** — landed (BACKLOG E1) in PR #429. Sentry
      Python + React with opt-in via DSN env vars. Both apps share
      one DSN so the Sentry UI shows traces that cross the
      Flask/FastAPI boundary as one event. See
      [`docs/architecture/deployment.md`](docs/architecture/deployment.md)
      §3 for the SENTRY_DSN env var setup.
- [ ] **DB backups verified** (ops) — confirm Render snapshots
      Postgres daily (verify on the current plan via Render →
      Database → Backups). Do a trial restore into a staging DB at
      least once before paid launch. See
      [`deployment.md`](docs/architecture/deployment.md) §4
      "Backups" for the trial-restore steps.
- [x] **Rate limiting** — landed (BACKLOG D6). slowapi on every
      auth route + the two webhooks (Flask-Limiter was retired
      alongside Flask itself in PR #546). `RATELIMIT_STORAGE_URI`
      → Redis in prod; `RATELIMIT_ENABLED` is the kill-switch.
      Tests in `tests/test_rate_limiting.py`.
- [x] **Employee action audit** — landed. Transfers, daily reports,
      batches, return-checks (create/update/delete/payment/loss/
      fraud/reopen), roster (create/reactivate/deactivate/rename),
      employee password resets, and owner-link redemption all
      append an `OperatorAuditLog` row via the in-app
      `record_op_audit()` helper. The full target-type +
      action vocabulary is documented on
      `api.Modules.Audit.Services.recorder.record_operator_action`.
      Regression tests in
      `tests/test_employee_action_audit.py` (7 tests covering
      the formerly-unaudited surfaces).
- [ ] **Stripe LIVE mode** (ops) — swap test → live keys, verify
      via the "Stripe connection" card at `/superadmin/controls`
      Overview. Confirm webhook endpoint is pointed at production
      `/webhooks/stripe`. Step-by-step verification:
      [`deployment.md`](docs/architecture/deployment.md) §3
      "Secrets rotation → Stripe live mode swap".
- [ ] **Re-enable cron services** (ops) — the two crons declared in
      `render.yaml` (`dinerobook-data-retention-purge`,
      `dinerobook-daily-summary`) were deleted from the Render
      dashboard pre-launch to stay under the free-tier instance
      cap (paid `starter` plan, no real users to email or expired
      stores to purge yet). Re-create them via Blueprint sync
      before public launch — the YAML is still the source of
      truth, so it's a single sync action plus filling in the
      `sync: false` SMTP envvars on the daily-summary cron. The
      web service is unaffected by their absence; both crons are
      idempotent so a missed day on either is a no-op.
- [x] **Data retention cron** — landed. `render.yaml` declares
      a `type: cron` service `dinerobook-data-retention-purge`
      that runs `python -m scripts.purge_expired_stores` daily at
      03:15 UTC. Shares the production DB via `fromDatabase:`. CLI
      is idempotent — re-running on a quiet day is a no-op.
      Regression guard in `tests/test_data_retention_cron.py`.
      (Originally invoked via `flask purge-expired-stores`; moved
      to the standalone script in PR #550 when Flask was retired.)
- [x] **CI/CD agents** — landed across PRs #425 (coverage source),
      #426 (SPA build + eslint --max-warnings 0 in CI), and the
      pre-existing "Syntax + Import + Tests" job. Every PR now
      runs:
      - `pytest tests/` (full Python suite ≥2,400 tests).
      - `npm run build` (SPA TypeScript + Vite production build).
      - `npm run lint` (ESLint --max-warnings 0).
      - Python import smoke check via the `Syntax + Import +
        Tests` job declared in `.github/workflows/`.
      Items still desired but not gating: secret-scanning (no
      tool wired yet — the `secrets-audit.md` recurring checklist
      is the manual stand-in), coverage-floor enforcement (we
      track coverage but don't fail PRs on regressions).
- [x] **Deployment runbook** — landed at
      [`docs/architecture/deployment.md`](docs/architecture/deployment.md).
      Covers the Render service / DB layout, first-time
      setup (Stripe webhook + custom domain + secret rotation),
      the routine deploy / roll-back flow, secret rotation
      (Stripe LIVE swap, SECRET_KEY, SMTP, WEBAUTHN_RP_ID),
      schema migrations + Alembic state, backup verification,
      data-retention purge cron, and an incident playbook
      indexed by symptom.
- [x] **Secrets audit** — landed at
      [`docs/architecture/secrets-audit.md`](docs/architecture/secrets-audit.md).
      Repo scan confirmed no live Stripe / AWS / bearer tokens
      committed; only documented dev-fallback values. The Flask-
      era SECRET_KEY safety gate is gone (no cookie session to
      sign) but the seed-password warning survives — fires a
      CRITICAL log line when `SUPERADMIN_PASSWORD` /
      `ADMIN_PASSWORD` are missing in prod (loud but doesn't block
      deploy). See `api/Core/Boot.py::warn_default_seed_passwords`.
      Tests in `tests/test_secrets_audit_safety_gate.py`.
- [x] **CSRF protection** — closed by the Flask removal. Flask was
      the only cookie-authenticated POST surface; `/api/v2/*` uses
      Bearer JWT in the Authorization header, which is naturally
      CSRF-immune (browsers don't attach it cross-origin). Webhook
      endpoints verify provider signatures (Stripe
      `Stripe-Signature`, Resend HMAC). If a cookie-authenticated
      POST surface is ever reintroduced, add CSRF protection at
      that point.
- [x] **Session cookie hardening** — closed by the Flask removal.
      Flask's session cookie was the only one we minted and it
      doesn't exist anymore. The remaining cookie (`ds_last_store`
      slug-tracker) is HttpOnly + SameSite=Lax + Secure (in
      `api/Modules/Auth/Controllers/__init__.py::
      _set_last_store_slug_cookie`).

## Nice to have (post-launch)
- [x] **Daily Book Money Transfers — editable per-company breakdown.**
      Landed. New `GET/PUT /api/v2/daily/{store}/{date}/mt-breakdown`
      endpoints back the Transfers tab: each row carries saved
      (operator's last entry) + auto (transfer-log aggregate) so
      the form pre-fills from saved-when-present, auto-otherwise.
      Save fires a bulk-replace into `MoneyTransferSummary` AND
      syncs the grand total into `DailyReport.money_transfer` in
      one transaction. Locked-day → 403. Service + Pydantic schemas
      + 9 unit tests (read defaults, auto/saved pull, unknown-company
      ordering, bulk-replace, idempotency, zero-row skip, locked guard,
      empty-rows-preserves-money_transfer).
- [x] **Multi-device auto-refresh on the Transfers list** — landed.
      `useTransfers` now accepts a `pollMs` parameter that wires
      TanStack Query's `refetchInterval`; the `/app/transfers`
      route passes 20_000ms by default. Polling pauses while a
      debounced search query is mid-flight (`qDraft !== q`) so we
      don't double-fetch on every keystroke, and the
      `refetchIntervalInBackground=false` default pauses the timer
      when the tab is hidden. The header carries a "Live · synced
      HH:MM" pill so the cashier sees the freshness at a glance.
- [x] Auto-fill `federal_tax` at the store's configured rate —
      landed. New/Edit Transfer forms now show a read-only
      "Federal tax preview" field that updates live as the
      cashier types. Mirrors the server-side rule in
      `api/Modules/Transfers/Services/tax.py` (exempt for Bill
      Payment / Top Up / Recharge, and for US-domestic recipients
      even on Money Transfer). The number is purely a preview;
      the server still recomputes on save per CLAUDE.md invariant
      #9. Hook + helper: `previewFederalTax` in
      `frontend/src/api/transfers.ts`.
- [x] Backfill script for `federal_tax` on historical transfers —
      landed. `python -m scripts.backfill_federal_tax` dry-runs by
      default + prints how many rows would change; pass
      `--commit` to write. Reuses the same `federal_tax_for`
      helper the create/edit routes use so the math can't drift
      from the live path. Honors Bill Payment / domestic-country
      exemptions and is idempotent (rerunning is a no-op). Tests
      in `tests/test_backfill_federal_tax.py`.
- [x] Dedicated `/customers` page with search / merge-duplicates —
      landed. ``/app/customers`` already had search + CSV export;
      this batch shipped the "Merge duplicates" mode + the
      backing endpoint. Admin / owner picks two customers, the UI
      shows winner / loser side-by-side, and confirming fires
      ``POST /api/v2/customers/{winner_id}/merge`` which:
      * re-points every ``Transfer.customer_id`` from loser →
        winner across the owner umbrella,
      * deletes the loser ``Customer`` row,
      * stamps an ``OperatorAuditLog`` entry (target_type=
        ``customer``, action=``merge``).
      Atomic — any failure rolls back the whole transaction.
      Cross-umbrella merges 404 (same shape as a non-existent
      id, so a cashier probing the API can't tell "this id exists
      somewhere" from "no such id"). Cashiers get 403 because the
      operation is destructive. Inline-edit (separate from merge)
      is still a backlog item.
- [x] Recipient suggestions — landed. When the cashier picks a
      sender (``customer_id`` set via SenderAutocomplete), a row
      of "recent recipients" chips appears above the
      ``recipient_name`` input. Each chip is one of the last 5
      distinct recipients that customer has sent to (umbrella-
      scoped, canceled / rejected transfers excluded). Tapping
      a chip fills name / country / phone in one action — the
      country only applies if it's still in the dropdown's
      canonical list, so legacy free-text values don't break
      validation. Component:
      ``frontend/src/components/RecipientSuggestions.tsx``;
      wired into both NewTransfer + EditTransfer. Backed by
      ``GET /api/v2/customers/{id}/recent-recipients``.
- [x] **Announcement banner in the SPA chrome** — landed. New
      `GET /api/v2/announcements/active` returns the slim
      `{id, message, level}` rows the banner needs (no audit /
      schedule fields leak to non-superadmin callers). Open to
      every authed role — admin, employee, owner, superadmin.
      `<AnnouncementBanner>` mounts inside `AppShell` between
      the topbar and the routed content; per-banner dismiss is
      stored in localStorage so a cashier closing it on one
      device doesn't suppress it on the back-office laptop.
      Polls every 5 minutes (pauses in background tabs). Tests
      in `tests/Modules/Announcements/test_announcements_controllers.py`
      cover the auth-open contract, slim shape, expired/scheduled/
      inactive omission.
- [x] Rich text / markdown links in announcements — landed.
      `<AnnouncementBanner>` auto-links bare `http(s)://...` URLs
      in the message body (trailing sentence punctuation is
      stripped so "see https://x.com/post." doesn't include the
      period). Anchors open in a new tab with `noopener`. No
      markdown parser pulled in — the only rich-text need
      operators actually surface is clickable links, and
      tokenising `http(s)` URLs covers ~100% of that.
- [x] Scheduled announcements — landed. The Announcement create
      endpoint accepts an optional `start_at_iso` (ISO-8601 UTC);
      omit / empty starts the banner immediately. expires_days is
      measured from start_at_iso so a scheduled banner gets its
      full visibility window. The existing `active_announcements`
      visibility helper already skipped not-yet-started rows.
      Superadmin → Announcements form has a "Schedule for later"
      datetime-local input; history table shows a "scheduled · in
      4h" pill for future rows. 5 new controller tests cover the
      future / past / empty / bad-parse / expiry-from-start_at
      cases.
- [ ] CAPTCHA on `/forgot-password` if bot traffic shows up.
- [x] Mask phone numbers in list views per compliance — landed.
      `maskPhone` helper in `frontend/src/lib/format.ts` keeps
      the last 4 digits + replaces the rest with middle dots.
      Applied to `/app/customers`, `/app/reports/top-customers`,
      and `/app/reports/top-senders`. Customer / transfer detail
      pages still show the full number on click-through.
- [x] CSV export on the customer directory — landed.
      `GET /api/v2/customers/export.csv` returns every customer
      in the owner umbrella alphabetically, admin-only. Frontend
      has an "Export CSV" button on `/app/customers` for admin /
      owner / superadmin roles. Tenancy from JWT (not query
      param) so cashiers can't pivot to another store. Tests in
      `tests/Modules/Customers/test_customers_controllers.py`.
- [x] **Email locked-day digest to owner** — landed. The FastAPI
      lock controller fires `send_locked_day_digest(report)` on a
      was-not-locked → locked transition; recipient query +
      static copy live in
      `api/Modules/Notifications/Services/locked_day_digest.py`,
      template at `templates/emails/locked_day_digest.html`,
      opt-out toggle on `User.notify_locked_day_digest` (default
      TRUE, flipped off on Resend complaint webhook).

## Compliance (gated on check-cashing feature)
- [ ] **OFAC SDN screening** — once we expand from remittance
      bookkeeping into check cashing (or any role where DineroBook
      acts as the regulated party rather than a pure ledger of what
      Intermex/Maxi/Barri already screened), implement weekly SDN
      list ingest + nightly customer-name match + flagged-customer
      review queue. Today this isn't required because the money-
      transfer companies do the screening upstream and DineroBook
      is downstream bookkeeping; if/when check cashing lands, this
      becomes a regulatory must-have and should ship in the same
      release.

## Stripe Issuing (research first, then build)
- [ ] **Phase 1: Research.** Stripe Issuing lets us mint virtual or
      physical cards tied to a funded Issuing balance. Open questions
      before any code: (a) money-transmitter licensing implications
      — does issuing a payment card to a store change DineroBook's
      regulatory category in any state where the store operates?
      (b) Cardholder vs. company card model — issue to the store
      entity, or to individual employees with spending limits per
      role? (c) Funding model — auto-sweep from the store's bank
      account (Stripe FC), pre-funded balance, or credit line?
      (d) Reconciliation flow — Issuing transactions land via
      webhook; do they auto-post to the daily book as expenses, or
      flow through bank-rule categorisation like FC transactions?
      (e) Liability for fraud / disputes / chargebacks — who eats
      the loss if a card is cloned? Until these are answered with
      legal + Stripe-account-manager input, do not start
      implementation.
- [ ] **Phase 2: Wiring (after research clears).** New
      `IssuedCard` + `IssuedCardTransaction` models, Stripe
      Issuing webhook handler, per-store cardholder onboarding
      flow on `/admin/settings`, transaction list + categorisation
      UI mirroring the bank-transactions page, monthly P&L
      auto-feed for Issuing-tagged categories. Ship behind
      `addon_issued_cards` feature flag (default False; turn on
      per-store as part of beta program).
- [x] Helpers (`simplefin_fetch`, `simplefin_claim_token`, `get_sfin_cfg`),
      routes (`/bank/setup`, `/bank/disconnect`, `/api/bank/refresh`),
      legacy `<details>` section on `/bank`, `bank_data`/`bank_error`/`cfg`
      context on the dashboard, and the CLAUDE.md section-map entry —
      all removed in 2026.
- [x] `SimpleFINConfig` model + `_STORE_OWNED_MODELS` entry removed.
      `simplefin_config` table dropped via `_drop_legacy_tables()` on
      next boot (idempotent, `DROP TABLE IF EXISTS`).

## Code quality
- [x] **Inline-CSS audit (closed by Flask removal).** D1 retired
      most templates; the rest (`base.html`, `_base_chrome.html`,
      `admin_settings.html`, `error.html`, `login.html`) all went
      away in PRs #546–#550 when Flask itself was removed. Only
      `templates/tv_display_public.html` + `templates/offline.html`
      survive — both standalone, both already on `--db-*` tokens.
- [ ] **Browser smoke layer — make CI green**. PR #200 added a
      Playwright-based smoke layer (`tests/smoke/`) that catches
      silent JS errors in chrome wiring. It runs locally (14 tests
      passing), but the "Install Playwright browser" step fails on
      ubuntu-latest with exit code 1 — root cause not yet visible
      from the public log reader. Steps are marked
      `continue-on-error: true` in `.github/workflows/ci.yml` so
      failures don't block PRs while we iterate. Most-likely
      culprits to investigate: (a) `playwright install chromium`
      download / network on the runner, (b) Python 3.12 wheel
      availability for the playwright version pip resolves, (c)
      missing OS deps that `--with-deps` would have provided
      (we removed it because the apt path was brittle locally).
      The current `set -ex` in the install step echoes each
      command, so the next failed run's log will pinpoint the
      exact failing line. Drop `continue-on-error` once smoke
      runs reliably for a week. Doesn't block the software —
      smoke layer adds value either way (devs can run it locally
      with `pytest tests/smoke/`).
- [ ] Graduate inline chat smoke tests to committed regression tests in
      `tests/`. Current gap: subscription, superadmin controls, customer
      directory, forgot-password flow.
- [x] `pytest-cov` report + target ≥ 80% line coverage. Landed —
      the CI workflow runs `coverage report --fail-under=80`
      (currently passing at ~93%, scope is `--source=api`).
- [x] Split `app.py` into Flask blueprints, then delete both.
      Blueprint split landed via D2 (29 phases); the entire
      monolith + blueprints + Flask itself were retired in
      PRs #546–#550 (see the "Flask removal — complete" entry
      at the top).
- [ ] Replace the PR description smoke-test lists with committed tests
      so the "Test plan" checklist can stay short.
- [x] **Data-fn unit tests for 5 superadmin reports** — closed
      out during the Reports → FastAPI migration. The functions
      moved to ``api/Modules/Superadmin/Services/reports.py``
      and gained coverage in the matching test modules:
      ``churn_cohort`` + ``trial_expiry_timing`` in
      ``test_mrr_churn_service.py`` / ``test_conversion_service.py``;
      ``bank_sync_adoption`` + ``tv_display_adoption`` in
      ``test_adoption_service.py``; ``login_activity`` in
      ``test_reports_service.py``.
- [x] **SQLAlchemy 2.0 migration** — landed (PR #551). 507
      ``Model.query.X`` sites across 127 test files swept to
      ``db.session.query(Model).X`` (filter_by / filter / all /
      first / one / count / delete / update / ...). ``.get(id)``
      sites rewritten to ``db.session.get(Model, id)``. The
      ``LegacyAPIWarning`` no longer appears in the suite output.
      The optional further step — moving to ``db.session.execute(
      select(...))`` — is a much smaller and cosmetic delta and
      can ride a separate cleanup whenever it's worth doing.
- [x] **Hex sweep on `daily_list.html`** — closed by Flask
      removal. The Jinja calendar template was retired in PRs
      #546–#550; the SPA's daily-book surfaces use `--db-*`
      tokens via co-located CSS Modules.

## AI helper bot ("Dino")
- [ ] **v1 — searchable help center (no LLM, $0 forever).** Floating
      bubble bottom-right on every authenticated page that opens a
      modal panel. Hard-coded Q&A pairs in a JSON/Python registry
      keyed by intent ("how do I add a transfer", "what does
      over/short mean", "how do I lock a daily book", etc.). Fuzzy
      client-side search (Fuse.js or a 30-line Levenshtein), render
      the answer with deep-links into the right page. Covers ~80% of
      "how do I X" questions and feels instant. This is the right
      first step — we get the UI surface, the muscle memory, and a
      structured answer registry that the LLM-backed v2 can also use
      as ground-truth context.
- [ ] **v2 — Claude Haiku 4.5 fallback** when the FAQ search has no
      good match. Single-turn Q&A; system prompt embeds the same
      answer registry plus DineroBook product facts (sidebar map,
      plan matrix, report catalogue). Use prompt caching on the
      system prompt so repeat questions are ~$0.0005 each. Rate-limit
      20 msgs/user/hour. Feature-flag `addon_ai_helper` (default
      True; gate behind Pro plan if cost grows). Tests mock
      `anthropic.Anthropic.messages.create`.
- [ ] **v3 — context-aware** — pass the current route + user role to
      Dino so "how do I do this?" on `/daily/2026-05-04` knows it's
      being asked about the daily book. Pure prompt-engineering on
      top of v2.

## Settings surface — roadmap

PR #94 landed `/account/profile` + `/account/security` as the per-user
pages every role reaches. The rest of the Settings surface still has
gaps. Ordered by "what I'd do next" at the top.

## Email deliverability polish
- [ ] **BIMI logo in Gmail** — the sender avatar currently shows as a
      gray circle. Fixing it takes three pieces of work, all small:
      (1) tighten the DMARC record from `p=none` to `p=quarantine` at
      Cloudflare DNS (safe given only Resend sends from `dinerobook.com`
      today); (2) host a DineroBook logo in SVG Tiny 1.2 format at a
      stable public URL (e.g. `https://dinerobook.com/static/bimi.svg`
      — needs a square viewBox, no raster images, no gradients);
      (3) add a BIMI DNS record at Cloudflare: `default._bimi.dinerobook.com`
      TXT `v=BIMI1; l=https://dinerobook.com/static/bimi.svg;`.
      Gmail starts showing the logo within a day or two once DMARC is
      enforced. A Verified Mark Certificate (~$1500/yr from DigiCert
      or Entrust) would make the logo appear on more clients, but
      Google's unverified variant is free and covers Gmail + Apple
      Mail for the vast majority of users. Defer the VMC until
      Gmail's unverified logo is actually live + we've seen real user
      impact.
- [x] **Resend delivery webhooks** — landed. `/webhooks/resend`
      verifies the Resend (svix) signature header and stamps an
      `EmailEvent` row per (event-type × recipient) tuple. Hard-
      bounce events set `User.email_bounced_at` so future
      `_send_email` calls skip the address; complaint events
      additionally flip every `notify_*` toggle to False. The
      route is `csrf.exempt`-listed (external caller, no session
      cookie) and rate-limited at 120/min (signature verification
      is the actual auth). See `app.py` `resend_webhook()` for
      the handler.
- [x] **Announcement-broadcast email** — landed. Ticking the
      "Also email all users" checkbox on the superadmin
      Announcements form now actually sends the email via the
      D5 enqueue path. ``broadcasts.broadcast_announcement``
      is the worker entry-point (top-level, primitive args so
      RQ can pickle it). In sync mode the orchestrator runs
      inline before the response returns; in queued mode
      (Redis activated) it pushes to RQ. Scheduled banners
      defer the broadcast until the schedule activates — the
      CLI replay is still available for that. Underlying
      ``broadcasts.run()`` was already idempotent on
      ``broadcast_sent_at`` so retries / replays are safe.
      Opt-out toggle on ``/account/notifications`` and the
      ``emails/announcement.html`` template were already
      shipped; this closes the missing trigger.
- [x] **Daily summary email** — landed. Per-store nightly close-out
      digest sent to opted-in admins + linked owners. Body carries
      transfer count, send volume, receipts, disbursements, over /
      short, and net position for the prior day. Quiet days (no
      transfer + no daily-report row) skip the email entirely so
      we don't spam zero-volume stores.

      Vertical slice landed:
      * Service: ``api/Modules/Notifications/Services/daily_summary.py``
        — ``compute_daily_totals``, ``eligible_recipients``,
        ``stores_with_activity``, ``run`` (orchestrator stamps
        ``Store.daily_summary_sent_for`` for idempotency), and
        ``send_daily_summary`` (D5 worker entry-point).
      * Template: ``templates/emails/daily_summary.html``.
      * CLI: ``scripts/send_daily_summaries.py`` with
        ``--date YYYY-MM-DD`` for backfills.
      * Cron: ``dinerobook-daily-summary`` in ``render.yaml`` at
        02:00 UTC daily.
      * Migration: ``7a1c93f0d2b8`` adds
        ``User.notify_daily_summary`` (opt-out, default True for
        admins/owners) + ``Store.daily_summary_sent_for`` (dedup).
      * Notifications endpoint exposes the toggle + a
        ``daily_summary_applies`` predicate (employees get a
        greyed-out informational row).
      * SPA toggle on ``/app/account/notifications`` next to the
        locked-day digest toggle.
      * Tests: 15 service tests + 3 toggle tests + 3 CLI tests.
- [ ] **DMARC reporting mailbox + dashboard** — once DMARC is tightened
      for BIMI, the `rua=` address receives daily XML aggregate reports
      from receivers. Parse them into a superadmin page showing which
      senders are passing/failing SPF/DKIM for our domain. Catches
      misconfigured Google Workspace setups before they break
      deliverability.

### Personal (`/account/*`)
- [ ] **Notifications page** — toggles for email + push. v1 below;
      follow-ups include announcement-broadcast email (needs a new
      sender in the superadmin announcement POST) and daily-summary
      email (needs a new cron). Ship the senders alongside the
      toggles, not before — empty toggles are a trust-eroder.
- [x] **Sessions / active devices** — landed.
      ``/app/account/sessions`` (new Devices sidebar entry under
      Account) lists every browser the current user is signed in
      on. Backed by the refresh-token chain: each ``/auth/login``
      call mints a stable ``session_id`` UUID that propagates
      forward through every ``rotate()``, so a chain of refresh
      tokens for one browser collapses to one panel row. The JWT
      now carries a ``sid`` claim so each request can identify
      its own session cheaply.
      Three endpoints:
        * ``GET /api/v2/auth/sessions``
        * ``DELETE /api/v2/auth/sessions/{session_id}`` (revoke one)
        * ``DELETE /api/v2/auth/sessions/others`` (revoke every
          session except the current one — "Sign out everywhere
          else").
      Per-row User-Agent + IP are captured on login and
      re-captured on every rotation. Migration ``9c5e21a4f8b3``
      adds the columns + an index on ``(user_id, session_id)``.
      Tests: 13 service tests + 11 endpoint tests cover the chain
      collapse, current-session flag, cross-user isolation,
      legacy-NULL bucket, and per-row JSON shape.
- [x] **Audit log (mine)** — landed.
      `GET /api/v2/auth/activity` returns the cross-store
      `OperatorAuditLog` + `TransferAudit` rows authored by the
      current user, paginated 50/page newest-first. Open to every
      authed role — a cashier sees their transfers, an admin sees
      their admin actions, a multi-store owner sees rows from
      every store with `store_name` attached for disambiguation.
      Frontend lives at `/app/account/activity` (new sidebar
      entry under Account). Service in
      `api/Modules/Audit/Services/my_activity.py`; tests in
      `tests/Modules/Audit/test_my_activity_endpoint.py` (10
      cases: auth gating, my-rows-only, store_name attachment,
      target/action filters, transfer-vs-other-target suppression,
      ordering, pagination).
- [ ] **Personal API tokens** — scoped tokens for scripts /
      integrations. Postpone until someone asks.
- [ ] **Connected accounts (Google / Apple SSO)** — premature today;
      passkeys cover most of the "sign in without a password" need.

### Store (`/admin/settings`)
- [x] **Store timezone** — landed. New ``Store.timezone`` column
      (whitelisted IANA strings, validated on PUT
      ``/api/v2/admin/store-info``) plus a settings-page dropdown
      so admins set the default for cashiers who haven't
      customized their own ``User.timezone``. SPA renders through
      a single ``frontend/src/lib/datetime.ts`` helper with the
      fallback chain ``user TZ → store TZ → browser default``.
      Audit log + my-activity feed + account profile + owner
      connect-code pages migrated; the remaining `.toLocaleString(…UTC…)`
      callsites (AdminUsers, TVDisplayAdmin) can adopt the helper
      on-touch.
- [~] **Store hours** (open/close per day) — schema + admin UI
      + read-side indicators landed.
      Schema: ``Store.store_hours`` is a JSON list of 7 entries
      (Mon-first, ``{day, open, close, closed}``); migration
      ``8a4b2e9d7c61`` adds the column idempotently.
      ``Admin.Services.store_hours`` owns validation (exactly 7
      entries, unique days, ``HH:MM`` 24-hour times, open<close
      unless closed), read-side coercion, and an ``is_open_at``
      predicate that powers both backend gates and SPA
      indicators. NULL on read renders a sensible Mon-Sat 9-6 /
      Sun closed default so the operator can save in one click.
      SPA: Dashboard carries an "Open now" / "Closed now" pill
      (uses store.timezone for the comparison), and the New
      Transfer form shows a soft yellow warning banner when the
      cashier is logging outside hours. ``getOpenStatus`` in
      ``frontend/src/lib/datetime.ts`` is the single source of
      truth.
      Server-side gating: ``Store.enforce_business_hours``
      boolean (default False, migration ``e5b4c3d2f1a9``) +
      a controller helper that calls ``is_open_at`` against
      ``store_now(store.timezone)`` and refuses transfer
      create / update with 422 when the toggle is on and
      outside hours. Settings page exposes the toggle right
      under the 7-day editor.
      Peak-hour heatmap landed too: new
      ``GET /api/v2/dashboard/peak-hours?days=N`` aggregates
      transfers into a 7×24 grid keyed on (weekday, hour-of-day)
      in the store's local timezone. Admin dashboard renders
      it via ``PeakHoursHeatmap`` — neon-green intensity ramp,
      dashed amber outline on cells outside the configured
      ``store_hours`` window so off-hours activity stands out.
      Excludes canceled / rejected transfers from the counts.
- [~] **Receipt customization** — built but currently HIDDEN.
      DineroBook is a ledger, not a money-transmitter, so the
      customer-facing receipt surface doesn't fit the product
      today. The full feature still lives in the codebase so
      enabling it later is a one-line revert.

      What's still in the repo (unused):
        * ``Store.receipt_logo_url`` / ``receipt_footer`` /
          ``receipt_tax_id`` columns (migration ``2d8f1e6c4a09``).
        * ``GET /api/v2/transfers/{id}/receipt`` + Pydantic
          schemas + the round-trip tests.
        * ``frontend/src/routes/TransferReceipt.tsx`` +
          ``.module.css``.
        * Read-/write-side adapters on the admin store-info
          endpoint (empty strings round-trip cleanly).

      What's hidden:
        * SPA route ``/app/transfers/{id}/receipt`` is not
          registered in ``App.tsx``.
        * "Print receipt" action on the edit-transfer page.
        * "Receipt customization" section on
          ``/app/settings``.

      To re-enable: revert the "hide receipt printing" commit.
      To wipe entirely: drop the route file + endpoint + the
      three columns (Alembic migration required).
- [ ] **Currency / locale** — hardcoded USD today. Needed before any
      non-US expansion.
- [ ] **Data export (`/admin/settings/export`)** — consolidate the
      scattered CSV exports. Useful for GDPR-style requests too.
- [ ] **Webhooks** — "notify my POS / accounting app when a transfer
      is saved."
- [ ] **Integrations (QuickBooks, Square, Zapier)** — big-ticket
      feature, high owner-operator value.
- [ ] **Receipt printer setup** — USB / Bluetooth thermal printer
      picker. Today cashiers print from the browser dialog.

### Time clock / payroll
- [~] **Time clock v1 + admin CRUD + approval workflow** —
      landed. Per-StoreEmployee shift tracking
      (``TimeClockEntry`` table, migrations ``f6e7a8b9c0d1``
      + ``a9c2b4e7d1f5``). Endpoints:
      ``POST   /api/v2/timeclock/clock-in``,
      ``POST   /api/v2/timeclock/clock-out``,
      ``GET    /api/v2/timeclock/status``,
      ``GET    /api/v2/admin/timeclock?from=&to=&store_employee_id=``
      (returns ``total_hours`` + ``approved_hours`` +
      ``pending_hours``),
      ``POST   /api/v2/admin/timeclock`` (admin back-fill),
      ``PUT    /api/v2/admin/timeclock/{id}`` (admin edit —
      can change ``status`` ∈ ``pending / approved / rejected``),
      ``DELETE /api/v2/admin/timeclock/{id}`` (admin remove),
      ``GET    /api/v2/admin/timeclock/{id}/history`` (per-entry
      audit chain).
      Schema columns: ``status`` (defaults ``pending`` on
      every fresh entry — clock-in, clock-out, admin back-fill)
      and ``adjusted`` (auto-set True on any non-no-op admin
      edit, including a pure status change). Only approved
      hours count toward payroll headlines.
      Server-side guards: one open shift per employee (409 on
      double-tap), inactive roster members can't punch,
      cross-tenant ids → 404, admin edits validate
      open<close, hours_worked recomputed on every clock-out
      / admin edit. Audit row per punch + per admin mutation;
      the admin ``admin_update`` summary carries a field-level
      diff so the per-entry history view replays what changed.
      SPA: ``/app/timeclock`` punch page for all roles,
      ``/app/admin/timeclock`` payroll history with:
        * 3 KPI tiles (Approved / Pending / Total hours)
        * per-employee grouping (one card per roster member,
          date-range header above each)
        * status + adjusted pills on every row
        * inline Edit / Logs / Delete on desktop, single
          "Actions" button that opens a Logs / Overview /
          Edit / Delete bottom sheet on narrow viewports
          (matches the inspiration screen)
        * status dropdown in the Edit modal
        * "+ New entry" modal for admin / owner
      Sidebar entries under Workspace (Time clock) and Finance
      (Payroll). v2 items below.
- [x] **Time clock v2 — passkey-required punch** — landed.
      Per-store ``timeclock_require_passkey`` toggle (default
      off) + new ``store_employee_passkey`` table that mirrors
      the existing user-side ``Passkey`` shape but keys on
      ``StoreEmployee.id`` (since cashiers share an
      ``employee`` ``User`` login). Migration
      ``b3d5e7f9a2c1`` adds both columns idempotently.
      Endpoints:
      ``POST /api/v2/timeclock/passkey/challenge`` (mints a
      WebAuthn assertion challenge for a roster member),
      and roster-credential management at
      ``GET/POST/DELETE /api/v2/admin/timeclock/credentials/*``
      (list, register/begin, register/finish, delete).
      Clock-in / clock-out gained optional ``assert_token`` +
      ``assertion`` body fields — required when the store
      toggle is on, ignored otherwise. The server verifies
      the assertion via ``webauthn.verify_authentication_response``
      against the roster member's stored credential, updates
      ``sign_count`` + ``last_used_at`` on success, and
      rejects backwards sign counts (cloned authenticator
      detection per WebAuthn §6.1.2).
      SPA: new ``/app/admin/timeclock/credentials`` page with
      a per-roster Enroll / Re-enroll / Remove flow that
      drives ``navigator.credentials.create()`` /
      ``.get()``. Settings → Store gains a "Block time-clock
      punches without a passkey" toggle, sitting under the
      business-hours enforce checkbox. The punch page does
      the WebAuthn round-trip transparently when the gate
      is on, and surfaces a helpful "ask admin to enroll
      your device" 422 when the cashier isn't registered.
      Windows Hello / Touch ID / Face ID / hardware key all
      flow through this same path natively — WebAuthn is the
      OS-level glue.
- [x] **Time clock v2 — geofence** — landed.
      ``Store.timeclock_geofence_lat/lng/radius_m`` +
      ``timeclock_require_geofence`` toggle. Punch flow reads
      ``navigator.geolocation`` and the server rejects with a
      distance hint when outside the radius (Haversine in
      ``api/Modules/TimeClock/Services/geofence.py``). Admin
      pins the location from /app/settings via "Use my current
      location" (or manual lat/lng entry); the passkey check
      stacks on top via a separate toggle so the two anti-
      buddy-punching gates are independently switchable. The
      browser permission prompt makes this a "soft" defense
      so the passkey check is the real anti-spoofing layer.
- [x] **Time clock v2 — break tracking** — landed.
      ``TimeClockEntry.break_started_at`` (DateTime, nullable;
      non-null = currently paused) + ``break_minutes`` (Float
      accumulator across pause/resume cycles within a shift),
      migration ``d2e6a4f1b8c3``. Endpoints:
      ``POST /api/v2/timeclock/break/start`` (opens a break;
      409 if not clocked in or already on break) +
      ``POST /api/v2/timeclock/break/stop`` (ends a break;
      409 if no break in progress). ``clock_out`` subtracts
      ``break_minutes / 60`` from elapsed wall-clock when
      computing ``hours_worked``, so a 9-to-5 shift with a
      60-min lunch records 7.0 hours. Auto-ends an open break
      at clock-out if the cashier forgot to tap "End break"
      so the time still gets accounted for. Audit rows for
      both ``break_start`` + ``break_stop`` actions.
      SPA: punch page shows "Start break" / "End break"
      button when the picked roster member is clocked in,
      labeled to match the current state; dropdown options
      flip to "(on break)" while paused. Paid-vs-unpaid
      distinction stays operator-managed via the notes field
      — uniform "break" semantics keeps the math simple.
- [~] **Time clock v2 — shift scheduling** — partial.
      v1 ships ``TimeClockShift`` (store_id, store_employee_id,
      shift_date Date, start_time Time, end_time Time, notes,
      created_at, created_by_user_id) + admin CRUD endpoints
      (``GET/POST/PATCH/DELETE /api/v2/admin/timeclock/shifts``)
      + a /app/admin/timeclock/schedule weekly grid (7-day
      columns, inline add/edit form per day, today highlight).
      Tenancy: every CRUD path resolves ``store_id`` from the
      JWT and 404s cross-tenant ids.  Times are store-local
      (Date + Time, no tz) so a schedule survives a timezone
      change.  Overnight shifts not v1 — split into two rows
      (one ending at 23:59, one starting at 00:00) until a real
      "spans midnight" follow-up.
      Remaining: late-arrival / no-show flags derived from
      joining ``TimeClockShift`` against ``TimeClockEntry`` at
      read time (admin payroll view + a "missed shift" digest).
- [ ] **Time clock v2 — late-arrival / no-show derivation**
      Joins ``TimeClockShift`` against ``TimeClockEntry`` at
      read time:
        * "Late by X min" badge on the payroll history page —
          for each shift, find the matching closed entry on
          the same date+employee, compute
          ``entry.clock_in_at - shift.start_time`` in
          store-local minutes. Surface as a pill on
          ``TimeClockEntryRow`` and as a "Late" filter on the
          /app/admin/timeclock list.
        * Daily "missed shift" digest — at end of each day,
          enumerate shifts with no overlapping entry and
          email the admin a per-store summary. Reuses the
          existing notifications pipeline (``Notifications``
          module) and the locked-day digest scheduler.
      Threshold (e.g. "late = > 5 min") becomes a per-store
      setting alongside the geofence radius — same Settings
      → Time clock section.
- [ ] **Notifications v1 — preferences UI**
      ``/app/account/notifications`` is registered in the nav
      and the topbar UserMenu but the page itself is currently
      a thin stub. v1 builds the toggle table:
        * Per-channel toggles (email + push) for each
          notification kind the SPA can produce: trial-ending
          reminder, daily missed-shift digest (above),
          locked-day digest, announcement broadcast,
          subscription receipt, password reset confirmation.
        * Backed by a new ``UserNotificationPref`` table keyed
          on ``(user_id, kind, channel)`` with a default-allow
          fallback so an opt-in matrix is the source of truth
          but unset entries still send (avoids a silent
          comms-blackout regression).
        * Push channel uses the existing service-worker
          subscription stored on the user row; UI shows a
          "Enable browser notifications" CTA when the
          subscription is missing.
      Backend: every emitting site (notifications dispatcher
      + scheduled jobs) reads through
      ``user_wants(kind, channel)`` before sending.
- [~] **Payroll check / paystub printing** — partial.
      Printable paystub view landed; check printing with MICR
      lines stays a separate item (needs Store-level bank
      account + routing).
      Shipped:
        * ``StoreEmployee.hourly_rate`` column + admin
          create / update plumbing (migration
          ``c4f8a2e6d3b9``, idempotent). Settings → Team gains
          a $/hr input per row.
        * ``GET /api/v2/admin/timeclock/paystub/{id}?from=&to=``
          returns the paystub payload (approved hours × rate
          = gross pay, plus the itemized shift list).
        * ``/app/admin/timeclock/paystub/:id`` print-CSS-clean
          paystub view; the AdminTimeClock employee group
          header has a "Print paystub" button that opens it
          in a new tab.
      Pending: MICR / check-number sequence for actual check
      printing (operator currently hand-writes the check
      from the paystub summary). Needs ``Store.bank_account``
      + ``Store.bank_routing`` + ``Store.check_number_next``
      columns.

### Owner umbrella (`/owner/settings` — doesn't exist yet)
- [x] **Cross-store defaults** — landed.
      ``POST /api/v2/owner/cross-store-defaults`` pushes the
      same field defaults (fed-tax-rate, timezone, business
      hours, enforce-hours, timeclock-require-passkey, phone,
      address) to every store in the owner's umbrella that
      the operator selects. Each store update goes through
      the same ``Admin.Services.store_info.update_store_info``
      guard the per-store settings page uses, so identical
      validation applies — bogus values surface as per-store
      ``rejected`` rows rather than failing the whole batch.
      Owner / superadmin only. Each successful update writes
      an ``OperatorAuditLog`` row (target_type=store,
      action=cross_store_update) so the per-store admin
      audit-log view shows when an owner pushed defaults.
      SPA: ``/app/owner/cross-store-defaults`` (sidebar entry
      under Owner). Form picks fields via per-field "Apply"
      checkboxes — unchecked fields stay untouched on every
      store. Result table renders per-store outcomes after
      submit, same pattern as Bulk add user.
- [x] **Bulk user management** — landed.
      ``POST /api/v2/owner/bulk-add-user`` creates the same
      login (username + password) at every store in the
      owner's umbrella that the operator selects. Per-store
      outcomes (created / skipped / rejected) come back in the
      response so the SPA can render a result table; one store
      collision doesn't fail the whole batch. Stores outside
      the umbrella surface as ``rejected`` rather than 403'ing
      the call. Each successful create writes an
      ``OperatorAuditLog`` row.
      SPA page at ``/app/owner/bulk-add-user`` (new sidebar
      entry under Owner). Form takes username + password +
      full name + role (admin / employee) + a multi-select of
      the owner's stores. Results table shows per-store
      status after submit.
      Today this creates N independent User rows sharing the
      same credentials — a single-row multi-store user (one
      ``User`` with many ``store_id`` values) is a separate
      architectural item.
- [ ] **Consolidated billing** — one Stripe customer for N stores
      instead of one-per-store. Big architectural change, meaningful
      revenue upside.
- [ ] **Business legal info** — legal name, EIN, address. Avoid
      duplicating on each store.
