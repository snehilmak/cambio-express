# DineroBook Architecture Migration ADR

> **Status:** ACCEPTED — software lead has answered all open questions.
>            Migration kicks off with PR 1 (Reports module).
> **Last updated:** 2026-05-06
> **Authors:** Snehil Mak (product), Software Lead (architecture), Claude (drafting)

This document is the **target architecture** for DineroBook and the
**migration plan** to get there from the current Flask monolith. It's
the single source of truth that every migration PR refers back to.

---

## 1. Why we're doing this

The current backend (`app.py` ~14,000 lines) is a Flask monolith with
routes, business logic, DB queries, email sending, and Stripe webhooks
all in one file. This was correct for the first 18 months of feature
velocity but is now a structural drag:

- **Onboarding is hard** — a new contributor has to learn the entire
  app to make any change.
- **Testing is bound to HTTP** — most tests go through `test_client`
  because the business logic isn't directly callable; we can't unit-
  test workflows in isolation.
- **No reuse path** — we can't extract the daily-book or transfer
  workflows into another product without bringing the whole monolith.
- **Web framework is dated for this product** — Flask + Jinja2 made
  the SaaS launch easy, but a customer-deployable backend wants
  API-first ergonomics, automatic OpenAPI docs, and Pydantic
  validation. FastAPI gives all three.

The target is a **modular, multi-layer FastAPI backend** that customers
can deploy as a Docker image, paired with a **separate frontend repo**
that talks to the API. Single-tenant per deployment.

---

## 2. Target architecture

### Stack

| Layer | Old | New |
|---|---|---|
| Backend framework | Flask 3.0 | **FastAPI** |
| Schema validation | Werkzeug `request.form` | **Pydantic** |
| Database | Postgres (prod) / SQLite (dev) | **Postgres** (unchanged) |
| ORM | SQLAlchemy 3.1 | SQLAlchemy 3.1 (unchanged) |
| Templates | Jinja2 (server-rendered HTML) | **Frontend in separate repo** (React/Vue/HTMX — TBD) |
| Auth | Flask sessions + WebAuthn | OAuth2 + JWT (FastAPI standard) — see §6 |
| Tenancy | Multi-tenant (`store_id` everywhere) | **Single-tenant** per deployment |
| Deployment | One Render service | **Dockerized FastAPI image** customers run |

### Directory layout

```
app/
  Modules/
    Transfers/
      Controllers/    # FastAPI APIRouter — request/response, no logic
      Services/       # business logic, workflows, transactions
      Repositories/   # DB queries (one method = one query intent)
      Models/         # SQLAlchemy table definitions
      Requests/       # Pydantic request/response schemas
    Customers/
      Controllers/ Services/ Repositories/ Models/ Requests/
    Reports/
      Controllers/ Services/ Repositories/ Models/ Requests/
    Billing/
      Controllers/ Services/ Repositories/ Models/ Requests/
    Auth/
      Controllers/ Services/ Repositories/ Models/ Requests/
    BankSync/
      Controllers/ Services/ Repositories/ Models/ Requests/
    DailyBook/
      Controllers/ Services/ Repositories/ Models/ Requests/
    # …one folder per bounded context
  Core/
    Config/           # settings via Pydantic BaseSettings (env vars)
    Database/         # SQLAlchemy engine, session lifecycle, migrations
    Providers/        # external integrations (Stripe, Resend, etc.)
    # everything that's used by ≥2 modules
  main.py             # FastAPI app factory; mounts module routers
tests/
  Modules/
    Transfers/        # mirrors app/Modules layout
    Customers/
    …
  Integration/        # cross-module HTTP-level tests
docs/
  architecture/
    MIGRATION_ADR.md  # ← this file
```

### Layer rules (enforced via PR review and lint where possible)

| Layer | Allowed to call | NOT allowed to call |
|---|---|---|
| **Controller** | Service | Repository, Model directly |
| **Service** | Repository, other Services, Provider | Controller, framework code |
| **Repository** | Model, raw DB session | Service, Controller, Provider |
| **Model** | nothing else | everything else |
| **Provider** | external SDKs (Stripe, etc.) | Service / Repository |
| **Request schema** | nothing else | everything else |

A controller calls **one service method** per request when possible.
The service orchestrates: validates business rules, opens a DB
transaction, calls one or more repositories, calls providers (e.g.
Stripe), commits.

### Why this shape

- **One folder per module = one bounded context.** A reader only needs
  the files in `Modules/Transfers/` to understand the transfer flow.
- **Layered = swappable.** If we ever switch ORMs or DB engines, only
  Repositories change. If we add gRPC or CLI on top of HTTP, only
  Controllers change.
- **Testable in isolation.** Services accept Repositories via
  dependency injection; tests pass mocks. No Flask test_client required
  for unit tests.
- **OpenAPI for free.** FastAPI generates it from Pydantic schemas;
  customers integrating against the API get a typed contract.

---

## 3. Tenancy model change: multi-tenant → single-tenant

The current code threads `store_id` through every query, has the
multi-store owner umbrella, and the superadmin can impersonate stores.
Going single-tenant means:

- **One `Store` per deployment.** The whole `Store` model can become a
  singleton (or just a config blob) — no more `store_id` joins.
- **Owner umbrella becomes a config thing**, not a runtime concept. If
  a customer wants multi-store oversight, they run multiple deployments
  and aggregate at the report layer (or we keep multi-store as a
  v2 feature post-cutover).
- **Superadmin disappears at the app layer.** Operations on a customer
  deployment are admin-only (the customer's own admin). DineroBook
  (us) wouldn't have a superadmin login into customer instances.
- **`StoreOwnerLink`, `OwnerConnectCode`, owner routes**: dropped from
  the customer-deployable image. Could survive in a separate hosted
  variant if we still operate dinerobook.com as SaaS — see §7.

This is the **biggest functional simplification** in the migration.
About 3,000 of the 14,000 lines in `app.py` are multi-tenant scaffolding
that goes away.

---

## 4. Migration approach: strangler fig

**Don't rewrite from scratch.** Run FastAPI alongside Flask in the same
repo until everything is ported, then cut Flask. Steps:

1. Add a FastAPI app that mounts at, say, `/api/v2/` while the existing
   Flask app keeps serving everything else.
2. Migrate one module per PR (in the order below). Each PR:
   - Creates `app/Modules/<Module>/` with all five layers.
   - Adds tests under `tests/Modules/<Module>/`.
   - Switches the Flask routes for that module into thin proxies that
     call the new FastAPI service layer (so the old UI keeps working
     during the migration).
3. Once **all** modules are ported, the new frontend repo (`dinerobook-web`)
   replaces the Jinja2 templates. At that point Flask + templates can
   be deleted in one final cleanup PR.
4. The FastAPI app gets Dockerized and the production deployment
   switches over.

Why strangler fig: every PR ships to production; we never have a
"big bang" branch sitting unmerged for weeks; rollback is one revert.

### Module migration order

Per discussion with the software lead:

| # | Module | Why this order | Risk | Status |
|---|---|---|---|---|
| 1 | **Reports** | Read-heavy, no writes, no external deps. Lowest risk reference impl. | Low | ✅ Done — all layers + Flask flip merged |
| 2 | **Customers** | Self-contained CRUD. Touches every transfer, but the surface is small. | Low | ✅ Done — search + upsert + get-by-id + Flask flip merged |
| 3 | **Transfers** | Big write surface (the core product). Most queries route through here. | Medium | 🟡 Read-side complete — list + get-by-id + Flask flip on `/transfers`. Write-side (create/edit/delete) still on Flask. |
| 4 | **Bank Sync** | External Stripe FC dependency; webhooks; reconciliation logic. | High | 🟡 Read-side complete — `/bank/transactions` + `/bank/rules` + `/bank/accounts`. Write-side (rule CRUD, manual categorize, daily-book post) still on Flask. |
| 5 | **Auth + Billing** | Cross-cutting (every request touches auth). Saved for last so we can refactor sessions → JWT once. | High | 🟡 Password login + JWT issuer + `/auth/me` complete. TOTP/passkey/refresh + Flask login flip pending. |
| 6 | **Daily Book + Monthly P&L + Return Checks + Batches** | Bookkeeping core. Heavy P&L math. Migrate in one batch since they share the daily-line-item plumbing. | Medium | 🟡 DailyBook read-side complete — `/daily/{store}/{date}` + period summary + `/daily` list flip. Monthly P&L / Return Checks / Batches still on Flask. Write-side (save report, lock/unlock, line items) still on Flask. |
| 7 | **Cleanup** | Drop Flask, drop multi-tenant code, drop superadmin, swap UI to new frontend repo. | Low (mechanical) | ⏳ Pending — depends on completing modules 3-6 write-side + Auth Flask flip. |

**As of 2026-05-06:** 27 PRs merged on `pre-prod`. The FastAPI router lineup (`/api/v2/{reports,customers,transfers,bank,auth,daily}/*`) is complete for the read-side; legacy Flask continues to own write-side endpoints and HTML chrome.

### Definition of done per module migration PR

- [ ] All five layers exist under `app/Modules/<Module>/`
- [ ] Pydantic schemas in `Requests/`
- [ ] At least one repository test, service test, and controller test (HTTP)
- [ ] Flask routes for this module proxy to the new service (so old UI works)
- [ ] No `app.py` query function remains for this module
- [ ] OpenAPI spec includes the new endpoints
- [ ] `pytest tests/` stays green

---

## 5. New repos

| Repo | Purpose | When created |
|---|---|---|
| `cambio-express` (this one) | Migration source. Shrinks per PR. Eventually retired. | exists |
| `dinerobook-api` | FastAPI backend extracted from this repo. | Created at start of Reports migration (PR 1). Initially populated by copying `app/` over. |
| `dinerobook-web` | Frontend (React/Vue/HTMX — TBD by software lead). | Created when the API has enough endpoints to render a page (~end of Reports migration). |

> **Q1 RESOLVED — Frontend stack: React.** Reasons given by the
> software lead: most-standard "customer integrates with our API"
> story, biggest hiring pool, mature tooling. Means the existing
> Jinja2 design system gets reimplemented in React components — the
> design tokens and visual language carry over (CSS-in-JS or CSS
> modules, TBD when the frontend repo is created).

---

## 6. Auth migration

Flask sessions → JWT. A few concrete steps:

1. Keep WebAuthn passkeys (they're independent of the session
   transport — they verify, then we issue a JWT instead of setting
   `session["user_id"]`).
2. TOTP 2FA stays — same flow, different finalizer (`/login/2fa/verify`
   returns a JWT instead of setting `session["user_id"]`).
3. Recovery codes stay.
4. The frontend stores the JWT in an HttpOnly cookie (still session-
   like, just with a token in the cookie instead of an opaque
   server-side session ID).

> **Q2 RESOLVED — JWT carries the full permission set as claims.**
> On successful login the auth service computes the user's effective
> permissions once (resolving role-default + any per-user overrides
> from the future permissions hierarchy feature) and embeds them
> in the JWT. Subsequent requests read from the token; no DB hit
> per request.
>
> **Concrete implications:**
> - Use a moderate TTL (default: 30 minutes) so a permission revoke
>   propagates within that window. Long-lived sessions get a refresh
>   token that re-issues with fresh claims.
> - On role change (admin promotes an employee, etc.), the auth
>   service issues a new token immediately so the user doesn't have
>   to wait for TTL expiry.
> - Server-side blacklist of token IDs (`jti` claim) for hard
>   revocations (account locked, password changed, etc.) — checked
>   on every request but the lookup is small (Redis or just a DB
>   table indexed on `jti`).

---

## 7. The fate of dinerobook.com (the SaaS)

**Option A:** Cut over the SaaS to the new FastAPI codebase deployed
multi-tenant. Requires keeping the multi-tenant code paths.

**Option B:** Keep Flask serving dinerobook.com indefinitely (no new
features), focus all engineering effort on the customer-deployable
backend. Eventually shut down the SaaS or migrate customers to
self-hosted instances.

**Option C:** Cut over the SaaS to the new FastAPI codebase but have
it host a **single multi-tenant deployment** (essentially: the SaaS
gets `store_id` back, but customer-deployable doesn't). One codebase,
two build flavors.

> **Q3 RESOLVED — Option A: cut over the SaaS to the new FastAPI
> codebase.** Rationale from the software lead: "we are not even at
> production level yet so nothing to affect much." Translation: the
> SaaS at dinerobook.com is early-stage with light load, so we don't
> need a careful drawn-out migration to protect existing customers.
> The new FastAPI app becomes the only codebase; Flask is removed in
> the cleanup PR.
>
> **Concrete implications:**
> - Strangler fig still applies (one module per PR, both serve traffic
>   in parallel) — but the migration window can be aggressive since
>   we're not protecting heavy production load.
> - At cutover, dinerobook.com points to the FastAPI deployment.
> - Multi-tenant code paths get **dropped entirely** in the cleanup
>   PR — no need to keep them for a residual SaaS variant.
> - Any existing SaaS customers get a one-time migration to a
>   self-hosted Docker deployment. (Coordinate with whoever owns
>   customer success.)

---

## 8. Risks register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migration takes longer than expected | High | Medium | Strangler fig — ship every PR. No long-lived branches. |
| Flask + FastAPI dual-routing introduces latency / bugs | Medium | Low | Keep the dual-route window short per module. Migrate one module at a time. |
| Test coverage drops during migration | Medium | High | DOD per module includes "tests pass". Smoke tests (PR #200) catch UI regressions. |
| Frontend rewrite outpaces / falls behind backend | Medium | Medium | Don't start frontend work until ≥3 modules are ported. Backend leads. |
| Auth migration breaks existing sessions | Medium | High | Phase auth migration last (after the modules are stable). Issue both session + JWT for one release; deprecate sessions in the next. |
| Postgres + SQLAlchemy version drift between repos | Low | Medium | Pin versions in `dinerobook-api` requirements. |
| Customers expect multi-tenant features (umbrella, superadmin) | Low | Medium | Document explicitly that the customer-deployable variant is single-tenant. SaaS continues for multi-tenant needs (per §7). |

---

## 9. Sign-off status

- [x] **Q1:** Frontend stack — **React** (resolved 2026-05-06).
- [x] **Q2:** JWT claims model — **Embed full permission set in JWT;
      30-min TTL; refresh token + jti blacklist for hard revocation**
      (resolved 2026-05-06).
- [x] **Q3:** SaaS at dinerobook.com — **Option A: cut over** (resolved
      2026-05-06). Aggressive migration window OK since light load.
- [x] Software lead reviews the directory layout in §2 and the layer rules.
- [x] Software lead reviews the module migration order in §4 and approves
      the Reports module as the starting reference implementation.
- [x] A `pre-prod` branch exists as a backup snapshot of `main` before
      migration begins. **`origin/pre-prod` created 2026-05-06.**

**All gates passed. PR 1 (Reports module migration) starts next.**
Estimated ~1–2 weeks per module based on Reports being the smallest;
transfers + bank sync will be larger.

---

## 10. Out of scope for this ADR

- **Permissions hierarchy** (the superadmin → owner → admin → employee
  toggle system the product team asked about) — gets folded into the
  Auth module migration in step 5. Will be specified in a follow-up ADR.
- **Dino AI helper bot** — sits on top of the API once it stabilizes;
  no architecture impact today.
- **Feature flag system** — the existing `store_feature_enabled` pattern
  carries over. Could become a `Core/FeatureFlags/` provider.

---

## Changelog

- **2026-05-06** — Initial draft (Claude). Pending software-lead review.
- **2026-05-06** — All three open questions resolved by software lead:
  React frontend, JWT-embedded permissions with 30-min TTL, hard cutover
  for the SaaS. Status moved from DRAFT to ACCEPTED. Migration begins.
- **2026-05-06** — Migration progress refresh: 27 PRs merged on
  `pre-prod`. Module-status column added to the migration-order table.
  Reports + Customers fully migrated; Transfers + BankSync + Auth +
  DailyBook read-side scaffolding complete; write-side + Auth Flask
  flip pending.
- **2026-05-06** — Codebase tree note: legacy `app/` package was
  renamed to `api/` early in PR 1 to avoid Python import collision
  with `app.py` (Python imports the package first, which broke every
  `from app import …`). All ADR references to `app/Modules/...`
  should be read as `api/Modules/...` until the cleanup PR removes
  the legacy module.
