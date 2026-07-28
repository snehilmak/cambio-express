# Project Handoff — DineroBook

> **New to this repo, or a fresh Claude Code account picking up the work?**
> Read this file first, then `CLAUDE.md`. This captures the *in-flight
> state* that does NOT live anywhere else in git — the roadmap, the
> known-but-unfixed bugs, and the pre-launch operational gates. Keep it
> current: when a "Next up" item ships, move it to "Shipped" with its PR
> number.

_Last updated: 2026-07-28 (pre-beta, targeting end-of-month beta launch)._

---

## 0. How Claude "knows" this codebase (read this if you're a new account)

Claude Code's knowledge of this project is stored in **the repository**,
not in any Claude subscription or account. A brand-new account, pointed
at this repo, inherits all of it automatically on its first session:

- **`CLAUDE.md`** — auto-loaded every session. The invariants, stack,
  design system, and "what NOT to do" list. This is the single most
  important file; follow it exactly.
- **Per-module `INVARIANTS.md`** — `api/Modules/{Auth,DailyBook,Monthly,Transfers}/INVARIANTS.md`.
  Read the local one before editing a money-flow module.
- **`.claude/`** — custom agents (`dedup-hunter`, `refactor-scout`,
  `simplifier`, `test-writer`), skills (`sweep`, `dedupe`, `scout`,
  `simplify-pass`, `add-tests`), and `settings.json`. All git-tracked,
  so a new account gets the same tooling.
- **`docs/design-system/`** — the dark-first / neon-green design source
  of truth. Any UI change starts here.
- **`BACKLOG.md`** — deferred work; the "Before going live" items are
  launch gates.

**What does NOT transfer between accounts:** the *chat history* of the
old account, and any decision/plan that only ever lived in a
conversation. That is exactly what the rest of this file is for. When in
doubt, write it here rather than leaving it in chat.

---

## 1. Shipped (on `main`)

- **PR #777 — Superadmin controls Phase 2 ("PR B")** (merged 2026-07-28).
  Additive; one schema migration (`announcement_store`):
  - `POST /api/v2/superadmin/stores/{id}/credit` — issue a Stripe
    customer-balance credit (goodwill / make-good) from the panel. Same
    primitive as the referral path (invariant #12), but interactive, so
    Stripe failures surface instead of being swallowed (422/409/503/502).
    A single credit is capped at $5,000 (`credits.MAX_CREDIT_CENTS`).
  - **Announcement targeting** — new `announcement_store` join table
    scopes a banner to a subset of stores. **Absence of any row = global**
    (back-compat default). Targeting gates BOTH the on-screen banner
    (`active_announcements(db, store_id)`) and the email fan-out
    (`eligible_recipients(db, store_ids=…)`). Registered in the retention
    purge registry (invariant #4).
  - SPA: Store-Drill "Credit account" modal + announcement All/Specific
    store-picker + Audience column.
- **PR #778 — Superadmin audit-commit fix ("PR D")** (merged 2026-07-28).
  Closes the §3 bug. Every superadmin mutation now records its audit row
  through a new `_audit_and_commit()` helper (audit + commit together),
  so the ordering can't drift back to the buggy form. 11 routes were
  fixed (the 10 in §3 plus `email_store`, which audited with no commit).
  Regression tests assert each audit row survives the request lifecycle
  (invariant #7).
- **PR #774 — Pre-beta hardening** (merged 2026-07-13). Four fixes:
  1. Retention purge FK-ordering crash on Postgres — `purge_expired_stores()`
     now sweeps `RecoveryCode`, `PasswordResetToken`, `RefreshToken`,
     `Passkey`, `LoginEvent`, `PushSubscription` (and `TimeClockShift`)
     before deleting `User`/`StoreEmployee`. SQLite hid this in dev.
  2. Stripe `customer.subscription.deleted` idempotency — the 180-day
     retention clock is now stamped only on the *first* cancellation, so
     Stripe retries can't reset it and strand a store un-purged.
  3. Rate limits added to `/auth/login-cross-store`, `/auth/login/totp`,
     `/auth/login/recovery` (`10/min;50/hour`) and `/webhooks/{stripe,resend}`
     (`120/min`).
  4. Doc drift fixes (`reset_superadmin` CLI, passkey-login forward
     invariant, `migrate_db.sh` deprecation).
- **PR #775 — Superadmin controls (Phase 1 / "PR A")** (merged 2026-07-13,
  same commit as #774). Additive, no migrations, no money paths:
  - `POST /api/v2/superadmin/users/{id}/revoke-sessions` — revoke all of
    a user's refresh tokens (rejects superadmin targets).
  - `GET /api/v2/superadmin/retention-dry-run` — read-only preview of
    what the purge cron would delete, per store.
  - `POST /api/v2/superadmin/stores/{id}/clear-retention` — pause the
    retention clock (does NOT reactivate Stripe).
  - Two anomaly rules: `cancellation_spike`, `password_reset_spike`.

> Note: #774 and #775 were the *same commit* (`1908ef0`) reachable from
> two branches, so merging #774 brought in everything and #775
> auto-resolved as merged. `main` has one clean copy — nothing duplicated.

---

## 2. Roadmap — "Next up" (NOT yet started)

> ⚠️ **Numbering caveat.** In earlier planning chats these were referred
> to as "#2 / #3 / #5 / #6", but those are **survey/checklist item
> numbers, not GitHub issue numbers.** GitHub issues #2/#3/#5/#6 are
> unrelated old closed PRs (init_db fix, dark-mode toggle, mobile layout,
> dinerobook rebrand). Do NOT map these features to those issue numbers.
> If you want durable references, open fresh GitHub issues (see the
> checklist at the bottom).

> ✅ **PR B (#777) and PR D (#778) have shipped** — see §1. PR C is the
> only remaining roadmap item.

**PR C — Superadmin controls Phase 3** (next up):
- **Store freeze** — a superadmin write-gate that suspends a store's
  activity (distinct from trial-expired and from retention-pause; decide
  interaction with `get_trial_status` and `_TRIAL_EXEMPT`).
- **Webhook replay** — re-deliver / replay a stored Stripe (or Resend)
  webhook event from the superadmin panel for recovery/debugging
  (touches `api/Modules/Webhooks`).

_These descriptions are from planning conversation, not a written spec.
Confirm scope before implementing — the first step of PR C should be to
re-derive the exact requirements._

---

## 3. ~~Known bug~~ — ✅ FIXED in PR #778 ("PR D")

**Resolved 2026-07-28.** ~10 superadmin mutation routes wrote an audit
row but never committed it (`db.add()`-ed after the route's own
`db.commit()`, or with no commit at all), so `get_db()`'s
`finally: db.close()` rolled it back — the mutation landed but the
audit trail didn't, silently violating **invariant #7**.

The fix (PR #778) extracted an `_audit_and_commit()` helper in
`api/Modules/Superadmin/Controllers/__init__.py` (records the audit row
**and** commits in one call) and routed every superadmin mutation
through it. 11 routes were affected — the 10 originally flagged
(`change_user_role`, `toggle_user_active`, `reset_2fa`,
`force_password_reset`, `extend_trial`, `toggle_store_active`,
`bulk_action`, `set_maintenance`, `impersonate_user`,
`update_permissions`) plus `email_store`, which audited with no commit
at all. Regression coverage:
`tests/Modules/Superadmin/test_superadmin_audit_commit.py` asserts the
audit row is durably persisted (read in a fresh session after the
request lifecycle closes) for every previously-buggy route.

**Guard against regression:** any new superadmin mutation MUST end with
`_audit_and_commit(...)` — never a bare `db.commit()` followed by a
separate `_audit_store(...)`.

---

## 4. Launch gates — OPS / CONFIG, not code (from PR #774)

These are **Render / Stripe configuration**, not code changes. None block
a PR, but all block a real beta with paying customers. Verify each on the
`dinerobook` Render service before launch:

- [ ] **SMTP not configured** → password-reset & notification emails
      silently never send. Set the SMTP env vars (or Resend key).
- [ ] **Cron services deleted from Render** → `purge_expired_stores`,
      `send_daily_summaries`, `send_trial_reminders`,
      `send_missed_shift_digest` don't run. (The #774 purge fix only
      matters once the purge cron is back.) Re-declare them.
- [ ] **Stripe still in test mode** → any "paid" beta subscription is
      fake. Switch to live keys + verify the webhook signing secret.
- [ ] **DB backups not verified** → free-tier Postgres has no PITR.
      Confirm backups/retention before real tenant data lands.
- [ ] **Playwright E2E runs with `continue-on-error`** → never blocks a
      PR. Decide whether to make it blocking before beta.
      _Reviewed 2026-07-28: this is a deliberate, documented choice — the
      `continue-on-error: true` on the two Playwright steps in
      `.github/workflows/ci.yml` has an inline plan to drop it "when smoke
      is reliably passing for a week." The unit suite is the ground-truth
      gate. **Decision only — no code change recommended yet**; flipping
      it now risks gating every PR on flaky Chromium installs. Owner to
      decide when to make it blocking._
- [ ] **Hidden receipt endpoint still live** → review/remove before beta.
      _Reviewed 2026-07-28: the only receipt route is
      `GET /api/v2/transfers/{id}/receipt`, which is **authed**
      (`require_permission(claims, "transfers", "read")`) and
      **tenant-scoped** (cross-tenant lookups 404) — not an unauthenticated
      leak. The receipt **UI** is intentionally hidden (`App.tsx` +
      `Settings.tsx` comments: "ledger-only product… backend stays so
      re-enabling is a one-line revert"). **Decision only** — removing the
      backend would undo that documented intent and make re-enabling
      multi-file. Recommend **keep as-is**; owner to confirm._

---

## 5. Pre-beta UI / workflow polish (fill this in)

> The owner mentioned "small issues in UI and workflows to fix before
> beta." Enumerate them here so the new account can pick them up. Suggested
> format per item: page/route, what's wrong, expected behavior. Remember
> every UI change starts from `docs/design-system/` and uses the kit
> primitives in `frontend/src/components/ui/index.tsx`.

- [ ] _(add items)_

---

## 6. New-account setup checklist

When you switch to the new Claude subscription:

1. **Point the new account at this same repo** — clone it, or for Claude
   Code on the web, connect the `snehilmak/cambio-express` GitHub repo to
   the new account. `CLAUDE.md` + this file load automatically; no import
   step needed.
2. **Re-create the web environment config** (this is per-account /
   per-environment and is NOT stored in the repo): environment variables,
   the network-access policy, and any setup script. See
   https://code.claude.com/docs/en/claude-code-on-the-web.
3. **Re-connect integrations** the old account had: the GitHub connector
   and any MCP servers (each needs its own auth on the new account).
4. **Confirm tooling loaded** — ask the new session to list available
   skills/agents; you should see `sweep`, `dedupe`, `scout`, etc. from
   `.claude/`. If not, `.claude/` didn't come across — check it's not
   gitignored (it is currently tracked).
5. **Prime the first session** — point it at this file: *"Read HANDOFF.md
   and CLAUDE.md, then let's start on PR B."*

---

## 7. Suggested first actions for the new account

- [x] ~~Confirm the exact scope of PR B with the owner, then implement.~~
      **Done — shipped as PR #777.**
- [x] ~~Knock out PR D (audit-commit fix).~~ **Done — shipped as PR #778.**
- [x] ~~Review the code-only §4 items.~~ **Done — the receipt endpoint and
      Playwright `continue-on-error` are both deliberate, documented
      decisions (see §4 annotations); no unilateral code change made.**
- [ ] **Next: PR C** (store freeze + webhook replay) — re-derive scope,
      confirm design, implement.
- [ ] Walk the remaining §4 ops checklist with the owner (SMTP, cron
      services, Stripe live keys, DB backups — Render/Stripe dashboard
      access, not code).
- [ ] Fill in §5 from the owner's UI/workflow punch list.
- [ ] _(Optional)_ Open a durable GitHub issue for PR C. PR B/D no longer
      need issues — the merged PRs (#777/#778) are the durable references.

---

_Workflow reminders (also in `CLAUDE.md`): `pytest tests/` and
`python -m mypy` must both be clean before any commit; regenerate
`frontend/src/api/openapi.*` via `cd frontend && npm run generate-types`
after any Pydantic-schema change; never push to `main` — always PR._
