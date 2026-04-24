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

## SimpleFIN removal (after Stripe FC is proven)
- [ ] Once all active stores have migrated off SimpleFIN (verify via a
      superadmin query on `SimpleFINConfig` rows with `access_url != ''`),
      delete:
      - The `SimpleFINConfig` model (keep it in `_STORE_OWNED_MODELS` right
        up to the moment you drop the table so the retention purge still
        cleans legacy rows).
      - `simplefin_fetch`, `simplefin_claim_token`, `get_sfin_cfg`.
      - Routes: `/bank/setup`, `/bank/disconnect`, `/api/bank/refresh`.
      - The `<details>` legacy section on `/bank`.
      - The `bank_data` / `bank_error` / `cfg` context on the dashboard.
      - The SimpleFIN references in `CLAUDE.md` section map.
- [ ] Drop the `simplefin_config` table in a follow-up deploy, not together
      with the code removal.

## Code quality
- [ ] Graduate inline chat smoke tests to committed regression tests in
      `tests/`. Current gap: subscription, superadmin controls, customer
      directory, forgot-password flow.
- [ ] `pytest-cov` report + target ≥ 80% line coverage.
- [ ] Split `app.py` (~2500 lines) into Flask blueprints once feature
      cadence slows down. Likely slices: `auth`, `billing`,
      `superadmin`, `transfers`, `reports`.
- [ ] Replace the PR description smoke-test lists with committed tests
      so the "Test plan" checklist can stay short.

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
