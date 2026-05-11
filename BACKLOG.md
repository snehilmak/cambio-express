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

- [ ] **A1. Animations & transitions per CLAUDE.md design system.**
      The "Motion is part of the design system" section in CLAUDE.md
      specifies hover lifts, button scale-press, input focus glow,
      modal fade-scale, page fade-up, etc. Most SPA components I
      wrote during the migration have zero transitions. Audit every
      route under `frontend/src/routes/` and add `transition:` rules
      (≤200ms) per CLAUDE.md guidance. Honor `prefers-reduced-motion`
      (already wired in `content.css`).
- [ ] **A2. Padding / spacing consistency.** Every drilldown +
      dashboard component declares its own `pageStyle`, `cardStyle`,
      `kpiCard`, etc. Spacing varies. Extract `<Card>`, `<KpiCard>`,
      `<Page>`, `<Section>` into `frontend/src/components/` with one
      canonical padding scale (4/8/12/16/24 px ladder). Drop the
      inline style objects in each route. (Overlaps with BACKLOG
      item #9 "Shared SPA component library" — fold them together.)
- [ ] **A3. Typography consistency.** Currently each page picks its
      own font-size scale. Define a TypeScript `text` token (`xs / sm /
      base / lg / xl / 2xl`) in a shared module and route all `font-
      size:` through it.
- [ ] **A4. Empty states.** Every drilldown + list shows "No data in
      this period." with no illustration. Build a shared `<EmptyState>`
      with the inbox SVG (already on the design system) + a CTA slot.
- [ ] **A5. Loading skeletons** instead of bare "Loading…" text. Build
      one shared `<TableSkeleton rows={n}>` and `<KpiSkeleton>`.
- [ ] **A6. Error states.** Same as A4 — every fetch error renders a
      red inline `<p>`. Build `<ErrorState>` with a retry button.

### B. Missing charts on superadmin reports

I migrated owner dashboards + store detail with chart.js but the 20
superadmin BI reports go through a generic auto-rendering
component (`SuperadminBIDrilldown.tsx`) that ONLY shows KPIs + a
table. The user expected charts because the legacy Jinja superadmin
reports rendered ApexCharts inline.

- [ ] **B1. Time-series chart on superadmin reports that have a
      monthly/daily series.** Targets at minimum: `signup-funnel`,
      `dau-mau`, `mrr-arr`, `churn-cohort`, `login-activity`,
      `webhook-health`. Detection rule: if the row shape has a
      date-like key (`date` / `month` / `period`), render a Line
      chart above the table. Reuse the chart.js setup from
      `OwnerDashboard.tsx`.
- [ ] **B2. Bar charts** for reports where rows are a categorical
      breakdown (e.g. `active-stores-by-plan`, `trial-expiry-timing`,
      `payouts`). Heuristic: if no date key + numeric "count"-style
      column, render a Bar chart.
- [ ] **B3. Owner dashboard chart hover tooltips** are minimal —
      revisit chart.js options for nicer tooltips, axis formatting,
      currency on Y-axis.
- [ ] **B4. Add chart toggle.** Some reports are better as tables
      (audit log, refunds list). Let the user toggle chart / table
      view if both make sense.

### C. SPA architectural cleanup

- [ ] **C1. Code-split the bundle by route.** Bundle is now ~900 KB
      (240 KB gzipped) after chart.js. Convert every
      `<Route element={<X />}>` to `lazy(() => import(...))` + a
      shared `<Suspense fallback={...}>` wrapper. Especially big
      win for the superadmin BI drilldown (chart.js only loads for
      superadmin sessions). (See also BACKLOG #12.)
- [ ] **C2. Move inline styles to CSS Modules or Vanilla Extract.**
      Each route file has 100–300 lines of `const xStyle: CSSProperties
      = {...}`. Type-checked CSS Modules will give us scoped styles,
      better DX, smaller JS bundle.
- [ ] **C3. Shared `<Page>` layout component.** Standard
      header / actions / body slots. Use it on every route to enforce
      the design system padding scale.
- [ ] **C4. Per-route error boundaries.** A 500 from any API call
      currently crashes the whole route. Add an error boundary
      around `<Outlet />` in `AuthedShell`.

### D. Backend cleanup (legacy Flask half)

The SPA migration left the Flask side intact (form-POST handlers
still serve mutation traffic for many of the 301'd routes). These
items decompose the monolith.

- [ ] **D1. Delete the 16 remaining Jinja templates that are no
      longer rendered.** Surviving `reports.html`,
      `owner_reports.html`, `admin_settings.html`,
      `superadmin_controls.html` are unreachable after the GET 301s.
      Audit + delete.
- [ ] **D2. Split `app.py` (10,487 lines) into Flask Blueprints by
      the 80 `# ── HEADER ──` markers.** Suggested grouping:
      `flask/{auth,admin,superadmin,transfers,daily,monthly,bank,
       owner,tv,billing,reports,api_v1}.py`. Each becomes a Blueprint
      registered on `app`. No behavior change; pure refactor.
      Mechanical, ~5 PRs.
- [ ] **D3. Retire `@login_required` cookie-session path on routes
      the SPA has fully replaced.** Once D1 ships and we audit
      what still POSTs to Flask, convert remaining form-POST
      handlers to FastAPI endpoints, then delete the
      session-cookie path entirely. (Requires BACKLOG #1 cookie
      JWT first.)
- [ ] **D4. Adopt Alembic.** `_ADDED_COLUMNS` can't drop/rename/
      backfill. Pin current schema as baseline. (Already in
      BACKLOG #8 — promoting visibility.)
- [ ] **D5. Background job queue** for Stripe webhooks, email send,
      ACH retries, retention purge. RQ + Redis is the lowest-cost
      path on Render. Today every webhook does its Stripe SDK calls
      + audit insert + email send synchronously inside the HTTP
      request.
- [ ] **D6. Edge rate limiting** on `/login`, `/forgot-password`,
      `/api/v2/auth/*`, `/webhooks/stripe`. slowapi (FastAPI) +
      flask-limiter. (Also in BACKLOG "Before going live".)

### E. Observability + ops

- [ ] **E1. Sentry on Python + React.** (BACKLOG #4 — promoting.)
- [ ] **E2. Structured JSON logs.** Replace `app.logger.info(...)`
      with `structlog` or stdlib JSON formatter; add request-ID
      middleware. (BACKLOG #4 — second half.)
- [ ] **E3. Build SPA in CI** (BACKLOG #3). Catches TS regressions.
- [ ] **E4. Coverage tracks `api/` too** (BACKLOG #5).
- [ ] **E5. mypy strict on `api/Modules/*`** — Pydantic types make
      this easy.
- [ ] **E6. eslint --max-warnings 0** in CI on frontend.
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
- [ ] **F2. Request-lifecycle doc.** Diagram showing
      `client → CDN → Render → asgi.py → FastAPI / Flask
      Blueprint → SQLAlchemy → Postgres`, plus where Sentry +
      structured logs hook in.
- [ ] **F3. Frontend component catalog.** Once C2/C3 ship, document
      each shared component with a Storybook page (or simpler:
      a `frontend/docs/components.md` with screenshots).
- [ ] **F4. Onboarding README.** First-day-on-the-job runbook:
      clone → install → seed DB → run dev → test → deploy.
      The existing top-level README has install steps but no
      "where do I look to add a new report / route / table?"
      orientation.

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
- [ ] **SMTP configured** — set `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS`
      (optionally `SMTP_PORT` / `SMTP_FROM`) on the hosting platform so
      `/forgot-password` actually emails. Gmail + an app password works.
      Until this is set, reset URLs are logged at WARNING level and
      superadmin has to relay them manually.
- [ ] **Error tracking** — Sentry (free tier) so crashes surface without
      a friend having to tell us. Alternative: any APM the hosting
      platform offers.
- [ ] **DB backups verified** — confirm Render/Railway snapshots Postgres
      daily. Do a trial restore into a staging DB at least once.
- [ ] **Rate limiting** — Flask-Limiter on `/login`, `/forgot-password`,
      `/reset-password/<token>`, and `/api/customers/search`. Prevents
      brute-force and enumeration.
- [ ] **Employee action audit** — log who created / edited / deleted
      transfers, daily reports, batches. Superadmin actions already go
      through `record_audit()`; the employee side is unaudited.
- [ ] **Stripe LIVE mode** — swap test → live keys, verify via the
      "Stripe connection" card at `/superadmin/controls` Overview.
      Confirm webhook endpoint is pointed at production `/webhooks/stripe`.
- [ ] **Data retention cron** — wire `flask purge-expired-stores` to a
      daily scheduler so canceled stores actually age out at 6 months.
      Currently it only runs if invoked manually.
- [ ] **CI/CD agents** — unattended checks on every PR (syntax, tests,
      coverage floor, secret scan) running in GitHub Actions. Currently
      we rely on the existing "Syntax + Import + Tests" check plus
      manual `pytest` runs.
- [ ] **Deployment runbook** — document the env-var checklist, webhook
      config, first-boot seed, and how to recover from common failures.
- [ ] **Secrets audit** — confirm no hardcoded keys in the repo; the
      default passwords in `init_db()` (`super2025!`, `cambio2025!`)
      must be overridden via env vars in prod.
- [ ] **CSRF protection** — add Flask-WTF (or manual tokens) to every
      POST route. Currently unprotected.
- [ ] **Session cookie hardening** — `Secure`, `HttpOnly`, `SameSite=Lax`.

## Nice to have (post-launch)
- [ ] **Multi-device auto-refresh on the Transfers list** — two cashiers
      sharing the same employee login on different computers currently
      only see each other's edits after a page reload / filter change.
      Add a ~20s polling timer on `/transfers` that re-runs the existing
      `?partial=1` fetch so the table silently refreshes. Skip while the
      user is actively typing in the search box or has an unsaved form
      open. If this ever feels too laggy, upgrade to Server-Sent Events
      from the route that fires after `commit_transfer()`.
- [ ] Auto-fill `federal_tax` at 1% of send amount (or a per-company
      rate map) with an override field, so cashiers don't typo.
- [ ] Backfill script for `federal_tax` on historical transfers — they
      currently default to 0 but some of those fee amounts secretly
      included tax.
- [ ] Dedicated `/customers` page with search / edit / merge-duplicates.
- [ ] Recipient autocomplete (same pattern as sender) if repeat
      recipients become common in the data.
- [ ] Rich text / markdown links in announcements.
- [ ] Scheduled announcements (`Announcement.starts_at` already exists).
- [ ] CAPTCHA on `/forgot-password` if bot traffic shows up.
- [ ] Mask phone numbers in list views per compliance.
- [ ] CSV export on the customer directory.
- [ ] **Email locked-day digest to owner** — when a daily book is locked
      via the lock button, fire off a one-page HTML/PDF summary email
      to the store owner. Use `Store.locked_at` as the trigger so it
      fires for the right calendar day even when the book is locked
      late (cashiers often close out the next morning). Pairs with
      the notifications-toggle work in the personal-settings backlog.

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
- [ ] **Inline-CSS audit (rest of the codebase).** May 2026 PR
      cleaned up `subscribe.html` (34 inline `style="…"` attrs →
      page-scoped class set). 67 templates still carry inline styles;
      worst offenders by count: `superadmin_controls.html` (75),
      `daily_report.html` (47), `admin_settings.html` (43),
      `landing.html` (37), `monthly_report.html` (31). Pattern to
      follow: page-specific layout chrome goes in a
      `{% block head %}<style>...</style>{% endblock %}` block with
      a per-page namespace (e.g. `.subscribe-*`, `.daily-*`); colors
      come from `--db-*` design tokens, never hex; truly-shared
      components (cards, forms, banners, buttons) must use the
      classes already in `static/content.css`. Plan: tackle one
      template per PR, top-down by inline-style count, so each diff
      stays reviewable. Not a launch blocker — pages render fine —
      but every new feature on a noisy template duplicates more
      style strings until it gets cleaned up.
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
- [ ] Split `app.py` (~13k lines) into Flask blueprints once feature
      cadence slows down. Likely slices: `auth`, `billing`,
      `superadmin`, `transfers`, `reports`. **Priority slice:** extract
      the reports block (~3000 lines, roughly app.py:5500–8500 — every
      `_sa_*_data`, `_render_report_generic`, `_run_report_csv`, and the
      `_make_report_routes` / `_make_superadmin_report_routes`
      registrars) into a new `reports.py`. This is the single biggest
      coherent chunk and would make the rest of `app.py` materially
      easier to read.
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
- [ ] **Resend delivery webhooks** — Resend posts events (delivered /
      bounced / complained / opened / clicked) to a URL we register.
      Wire a new `/webhooks/resend` handler that verifies the Resend
      signature header and stamps a new `email_send_event` table.
      Unblocks: bounce-suppression (don't keep emailing addresses that
      hard-bounce), complaint auto-unsubscribe (mark notify_* False on
      spam report), and per-message status surfacing on the superadmin
      health card beyond "last attempt succeeded/failed."
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
