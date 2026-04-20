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
