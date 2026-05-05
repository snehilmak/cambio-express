# Backlog

Tracked work we're deferring. Anything in **Before going live** must be
closed out before public / paid launch; the other sections can happen on
any cadence.

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
