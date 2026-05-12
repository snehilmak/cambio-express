# Backlog

Tracked work we're deferring. Anything in **Before going live** must be
closed out before public / paid launch; the other sections can happen on
any cadence.

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
- [ ] **C2. Move inline styles to CSS Modules or Vanilla Extract.**
      Each route file has 100–300 lines of `const xStyle: CSSProperties
      = {...}`. Type-checked CSS Modules will give us scoped styles,
      better DX, smaller JS bundle. (A2/C3 swept the worst offenders
      into shared primitives; remaining inline styles are
      page-specific.)
- [x] **C3. Shared `<Page>` layout component.** Landed (PR #439) —
      `<PageShell>` / `<PageHeader>` / `<Section>` enforce the
      padding scale on every route.
- [x] **C4. Per-route error boundaries.** Landed (PR #435) —
      `<RouteErrorBoundary>` (Sentry-aware) wraps every route's
      `<Outlet />`.

### D. Backend cleanup (legacy Flask half)

The SPA migration left the Flask side intact (form-POST handlers
still serve mutation traffic for many of the 301'd routes). These
items decompose the monolith.

- [x] **D1. Delete the 16 remaining Jinja templates that are no
      longer rendered.** Landed (PR #424).
- [x] **D2. Split `app.py` into Flask Blueprints.** Landed in 29
      phases (PRs #433–#460, #461, #462, this PR). Every
      form-handling route now lives under `blueprints/`. Only the
      SPA fallback routes (`/app/*`), the two webhooks
      (`/webhooks/{resend,stripe}`), and helper / model / init code
      remain in `app.py`. Files under `blueprints/`:
      `account`, `admin_extras`, `admin_redirects`,
      `admin_settings_form`, `admin_settings_mutations`, `auth`,
      `auth_redirects`, `bank_mutations`, `bank_redirects`,
      `billing`, `bookkeeping_mutations`, `bookkeeping_redirects`,
      `customers_api`, `landing`, `owner`, `push`, `pwa`,
      `spa_cutover`, `spa_redirects`, `subscription`,
      `superadmin_extras`, `superadmin_misc_mutations`,
      `superadmin_redirects`, `superadmin_store_mutations`,
      `transfers_redirects`, `tv`, `tv_board`, `tv_pair`.
- [ ] **D3. Retire `@login_required` cookie-session path on routes
      the SPA has fully replaced.** Once we audit what still POSTs
      to Flask, convert remaining form-POST handlers to FastAPI
      endpoints, then delete the session-cookie path entirely.
      (Requires BACKLOG #1 cookie JWT first.)
- [x] **D4. Adopt Alembic.** Landed (PR #430) — baseline migration
      `99691740424c_baseline_2026_05` pins the current schema;
      `_ADDED_COLUMNS` still primary but Alembic now available for
      drops / renames / backfills.
- [ ] **D5. Background job queue** for Stripe webhooks, email send,
      ACH retries, retention purge. RQ + Redis is the lowest-cost
      path on Render. Today every webhook does its Stripe SDK calls
      + audit insert + email send synchronously inside the HTTP
      request.
- [x] **D6. Edge rate limiting.** Landed —
      `Flask-Limiter` 3.8 on the Flask side + `slowapi` 0.1.9 on
      the FastAPI side. Both share the same `RATELIMIT_STORAGE_URI`
      env var (in-memory in dev, Redis in prod) and the same
      `RATELIMIT_ENABLED` kill-switch. Tunings:
      - Auth burst: 10/min + 50/hour per IP — applied to every
        `auth.*` Flask Blueprint endpoint and to
        `/api/v2/auth/login`.
      - Forgot/reset password: 5/min + 20/hour per IP (lower
        because each request triggers an SMTP send).
      - Signup: 5/hour + 20/day per IP (signup is rare; an
        attacker minting stores at scale is the threat).
      - Webhooks (`/webhooks/{stripe,resend}`): 120/min per IP.
        Signature verification is the real defense; this is just a
        flood ceiling.
      Regression guards in `tests/test_rate_limiting.py` (4 tests)
      use a subprocess-with-fresh-env trick so they exercise the
      decorator path even though the conftest disables the limiter
      for the rest of the suite. See the file docstring for why.

### E. Observability + ops

- [x] **E1. Sentry on Python + React.** Landed (PR #429) — opt-in
      via DSN env vars.
- [x] **E2. Structured JSON logs.** Landed (PR #429) — structlog +
      X-Request-ID middleware in `api/Core/Observability/`.
- [x] **E3. Build SPA in CI.** Landed (PR #426).
- [x] **E4. Coverage tracks `api/` too.** Landed (PR #425) —
      `coverage --source=app,api`.
- [ ] **E5. mypy strict on `api/Modules/*`** — Pydantic types make
      this easy.
- [x] **E6. eslint --max-warnings 0** in CI on frontend. Landed
      (PR #426).
- [ ] **E7. Generate TS types from FastAPI OpenAPI.** (BACKLOG #6.)
- [ ] **E8. E2E smoke tests** with Playwright on the SPA — login,
      log a transfer, view a report. Would have caught the SPA-
      build-missing-in-CI class of issues that bit us during
      migration.

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
       of localStorage. Closes the XSS-exfil risk and lets legacy Flask
       + SPA share the same auth so users don't have to log in twice
       during the transition. ~1 PR.
2. [ ] **Refresh tokens.** Today access tokens are 30 min with no refresh
       — users get bumped mid-workflow. Add `/auth/refresh` endpoint +
       rotation; SPA fetches a new access token before the old one
       expires. ~1 PR.
3. [ ] **CI builds the SPA.** Add `npm ci && npm run build` (and ESLint)
       to `.github/workflows/ci.yml`. A TypeScript regression sails
       through today. ~1 PR.
4. [ ] **Sentry + structured (JSON) logging.** Errors today go to stdout;
       no aggregation, no alerting, no per-user breadcrumbs. ~1 PR each.

### P1 — do before/during full SPA cutover
5. [ ] **Coverage tracks `api/` too.** `--source=app` only covers `app.py`
       — every new FastAPI module is invisible to the `--fail-under=60`
       threshold. New code can ship at 0% coverage and CI is happy.
       Change `--source=app` → `--source=app,api`. Trivial.
6. [ ] **Generate TS types from FastAPI OpenAPI schema.**
       `frontend/src/api/*.ts` has hand-written interfaces mirroring
       `Requests/*.py` Pydantic — drift is inevitable. Add
       `openapi-typescript` to the SPA build, single source of truth.
       ~1 PR.
7. [ ] **Retire the WSGI-wraps-ASGI bridge — promoted to BLOCKER.**
       `a2wsgi.ASGIMiddleware` runs FastAPI inside Flask's sync WSGI
       worker — every request goes sync→async→sync, every API call
       creates an asyncio task that the WSGI worker can't cleanly
       reap. **This isn't theoretical anymore**: a May 2026 deploy
       turned the SPA-cutover redirect on by default and the site
       went unusably slow + login-network-error timeouts under
       prod traffic. The cutover flag is now default OFF (see
       `SPA_CUTOVER_ENABLED` in app.py); the SPA stays available
       at `/app/*` for opt-in. Until this bridge is retired, any
       page that fans out multiple `/api/v2/*` calls (the SPA's
       first paint typically does ~3) compounds the problem.
       Fix: run `uvicorn api.main:api_app` as its own Render
       service with nginx routing `/api/v2/*` → FastAPI,
       `/app/*` → static SPA build, `/` → Flask. Multi-file but
       mechanical. **Do this before the next attempt at flipping
       SPA_CUTOVER_ENABLED on.**

### P2 — quality of life as the codebase grows
8. [ ] **Alembic for migrations.** `_ADDED_COLUMNS` is pragmatic for
       solo work but can't drop, rename, backfill atomically, or roll
       back. The cost shows up the first time you need to alter an
       existing column. ~1 PR + ongoing.
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
11. [ ] **Postgres in dev** (docker-compose). SQLite hides FK constraint
       differences, transaction-isolation differences, JSON op
       differences, full-text search differences. Bites codebases like
       this regularly. ~1 PR (compose file + dev README).
12. [ ] **Code-split the SPA.** Bundle is 437kB / 113kB gzip already;
       without `React.lazy` per-route splitting it'll grow past 1MB
       once owner dashboard + superadmin controls + TV land. ~1 PR.

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
- [x] **Rate limiting** — landed (BACKLOG D6). Flask-Limiter on
      every auth Blueprint endpoint + the two webhooks; slowapi on
      `/api/v2/auth/{login,forgot-password,reset-password,signup}`.
      Both share `RATELIMIT_STORAGE_URI` (Redis in prod) and
      `RATELIMIT_ENABLED` kill-switch. Tests in
      `tests/test_rate_limiting.py`.
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
- [x] **Data retention cron** — landed. `render.yaml` now declares
      a `type: cron` service `dinerobook-data-retention-purge`
      that runs `flask purge-expired-stores` daily at 03:15 UTC.
      Shares the production DB via `fromDatabase:` and reads the
      same `SECRET_KEY` as the web service (so the prod-secret
      safety gate in `app.py` doesn't reject the cron boot). CLI
      is idempotent — re-running on a quiet day is a no-op.
      Regression guard in `tests/test_data_retention_cron.py`.
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
      committed; only documented dev-fallback values for
      `SECRET_KEY` + the two seed passwords. Added two prod
      safety gates in `app.py`:
      - `RuntimeError` at boot if `APP_BASE_URL` starts with
        `https://` and `SECRET_KEY` is missing (forces a real
        signing key in prod).
      - CRITICAL-level log when `SUPERADMIN_PASSWORD` /
        `ADMIN_PASSWORD` are missing in prod (loud but doesn't
        block deploy).
      Tests in `tests/test_secrets_audit_safety_gate.py` (5
      subprocess tests).
- [x] **CSRF protection** — landed. Flask-WTF's `CSRFProtect`
      installs a `before_request` hook that rejects any
      POST/PUT/PATCH/DELETE on a Flask route without a valid
      `csrf_token` form field (or `X-CSRFToken` header). Token is
      derived from the session, so cross-origin forgeries can't
      forge it. Every `<form method="POST">` in the legacy
      templates renders `{{ csrf_token() }}`. Webhook
      (`/webhooks/{stripe,resend}`) + WebAuthn passkey JSON
      routes are `csrf.exempt(...)`-listed because their callers
      don't have a session token (webhook signatures + the
      session cookie are the actual auth). FastAPI side is moot:
      JWT in Authorization header isn't cross-site-attachable.
      Kill-switch `WTF_CSRF_ENABLED=False` for the test conftest.
      Regression guard in `tests/test_csrf_protection.py`.
- [x] **Session cookie hardening** — `Secure`, `HttpOnly`,
      `SameSite=Lax` set in `app.py` after the SQLAlchemy config
      block. `Secure` gates on `APP_BASE_URL` starting with
      `https://` so dev / CI / sqlite mode keeps working over HTTP.
      Also bounds `PERMANENT_SESSION_LIFETIME` to 7 days. Regression
      guard in `tests/test_session_cookie_hardening.py`.

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
- [ ] Backfill script for `federal_tax` on historical transfers — they
      currently default to 0 but some of those fee amounts secretly
      included tax.
- [ ] Dedicated `/customers` page with search / edit / merge-duplicates.
- [ ] Recipient autocomplete (same pattern as sender) if repeat
      recipients become common in the data.
- [ ] Rich text / markdown links in announcements.
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
- [ ] CSV export on the customer directory.
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
- [ ] **Inline-CSS audit (mostly done; vestigial).** D1 (PR #424)
      retired 16 of the 17 templates the original audit flagged.
      Surviving templates with inline styles today (2026-05):
      - `templates/admin_settings.html` — 43 attrs. Only rendered
        on validation failure (GET 301s to `/app/settings`); low
        impact.
      - `templates/error.html` — 4 attrs.
      - `templates/base.html` — 3 attrs.
      - `templates/_base_chrome.html` — 2 attrs.
      - `templates/login.html` — 1 attr.
      Total inline-style count dropped from ~300 to 53. Cleaning
      `admin_settings.html` would close this entry — but the
      surface is rarely seen and the SPA-side
      `frontend/src/routes/Settings.tsx` is the canonical
      settings page, so this is firmly nice-to-have.
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
- [ ] `pytest-cov` report + target ≥ 80% line coverage.
- [x] Split `app.py` (~13k lines) into Flask blueprints. **Done**
      via D2 above — 29 phases of extraction shipped between
      PRs #433–#476. Every form-handling route now lives under
      `blueprints/`; `app.py` is down to ~7,500 lines (models,
      helpers, init, SPA-fallback routes, and the two webhooks).
      The reports module noted as "priority slice" was ported to
      FastAPI under `api/Modules/Reports/` rather than carved
      into a new Flask blueprint.
- [ ] Replace the PR description smoke-test lists with committed tests
      so the "Test plan" checklist can stay short.
- [ ] **Data-fn unit tests for 5 superadmin reports** still missing
      coverage: `_sa_churn_cohort_data`, `_sa_trial_expiry_timing_data`,
      `_sa_bank_sync_adoption_data`, `_sa_tv_display_adoption_data`,
      `_sa_login_activity_data`. Pattern lives in
      `tests/test_superadmin_reports.py` — each test seeds 2-3 stores /
      events, calls the data fn directly, asserts on the returned rows
      + totals shape.
- [ ] **SQLAlchemy 2.0 migration** — ~50 sites still use legacy
      `Model.query.filter_by(...).first()` / `.all()` instead of
      `db.session.execute(select(...)).scalar_one_or_none()`. The
      `db.session.get(Model, id)` invariant is already enforced; the
      `.query.*` API works but emits deprecation warnings and will
      break on a future SQLAlchemy major. `grep -nE '\.query\.(filter|all|first|count|order_by)' app.py` to find them.
- [ ] **Hex sweep on `daily_list.html`** — the calendar still inlines
      `#2d2410`, `#0f1d3f`, `#0f2e1f`, `#86efac`, `#2d1215`, `#fca5a5`
      for dark-mode shades. Add the missing semantic tokens to
      `design-tokens.css` (e.g. `--db-cal-today-bg-dark`,
      `--db-cal-hover-bg-dark`, `--db-pill-over-bg-dark`,
      `--db-pill-over-fg-dark`, `--db-pill-short-bg-dark`,
      `--db-pill-short-fg-dark`) and replace the inline hex.

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
- [ ] **Announcement-broadcast email** — when a superadmin posts an
      announcement, optionally email the full audience. Pairs with an
      opt-out toggle on `/account/notifications` + a new email template
      (`emails/announcement.html`). Fanout strategy is the real work:
      at 500 stores × 3 users = 1,500 emails, inline in the webhook POST
      is fine. At higher scale it'd need a queue.
- [ ] **Daily summary email** — cron-based per-store nightly digest of
      transfers, totals, new customers. New toggle on notifications
      page + new template + new `flask send-daily-summaries` CLI.
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
- [ ] **Sessions / active devices** — "you're signed in on 3 devices,
      sign out the others." Needs a session-store table; pairs with
      passkeys nicely as a security-signal feature.
- [ ] **Audit log (mine)** — filtered view of `TransferAudit`
      showing everything the current user did. Data already exists;
      just a scoped-query page.
- [ ] **Personal API tokens** — scoped tokens for scripts /
      integrations. Postpone until someone asks.
- [ ] **Connected accounts (Google / Apple SSO)** — premature today;
      passkeys cover most of the "sign in without a password" need.

### Store (`/admin/settings`)
- [ ] **Store timezone** — one column on `Store`. Fallback chain for
      date rendering: user TZ → store TZ → UTC. Today we render
      everything UTC. Small schema change, bigger refactor if we want
      it to flow through every `.strftime()` in the codebase — so
      start with one high-value page (daily report) and spread from
      there.
- [ ] **Store hours** (open/close per day) — gate "no transfers
      outside business hours" rule; useful for peak-hour heatmap.
- [ ] **Receipt customization** — logo + footer text + tax-ID line.
      Customers already ask for this.
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

### Owner umbrella (`/owner/settings` — doesn't exist yet)
- [ ] **Cross-store defaults** — apply a fed-tax rate / company list /
      receipt template to all my stores at once.
- [ ] **Bulk user management** — add an admin to multiple stores at
      once.
- [ ] **Consolidated billing** — one Stripe customer for N stores
      instead of one-per-store. Big architectural change, meaningful
      revenue upside.
- [ ] **Business legal info** — legal name, EIN, address. Avoid
      duplicating on each store.
