# DineroBook — Deployment Runbook

> Last updated: 2026-05-12
> Audience: anyone deploying to Render, rotating secrets, doing a
> trial restore, or debugging a prod incident.

DineroBook deploys to **Render** as a single web service (`dinerobook`)
backed by a managed Postgres (`dinerobook-db`). Every push to `main`
auto-deploys via `render.yaml`. The legacy `cashnet` service and
`cambio-db` are decommissioned — never reference them.

## 0. Repos, services, domains

| What | Where |
|---|---|
| Repo | `snehilmak/cambio-express` (GitHub) |
| Render service | `dinerobook` (web, Python) |
| Render DB | `dinerobook-db` (Postgres, free tier today — upgrade to Starter $7/mo before paid launch) |
| Production URL | `https://dinerobook.com` (custom domain → Render edge) |
| Render-internal URL | `https://dinerobook.onrender.com` (no longer canonical; keep for emergencies) |
| Deploy trigger | `git push origin main` → Render reads `render.yaml` → builds + restarts |
| Build script | `scripts/build.sh` — installs Python deps, installs Node via `nodeenv`, builds SPA bundle |
| Boot command | `gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker --workers 2 --timeout 120` |

## 1. First-time setup checklist

You **only do this once** when standing up a fresh environment. For
every-deploy work, jump to §2.

### a) Render dashboard

1. **Create the database first.** Render → New → Postgres. Region
   matching the web service. Default plan = free; upgrade to
   Starter ($7/mo) before paid launch.
   - Database name: `dinerobook`
   - User: `dinerobook`
   - Region: same as web service
2. **Blueprint deploy the web service.** Render → New → Blueprint
   → select this repo. `render.yaml` declares the `dinerobook`
   service and binds `DATABASE_URL` to `dinerobook-db`.
   - **Don't** create the service manually; let Render's
     blueprint render fill in env vars from `render.yaml`.
3. **Wire the custom domain.** Settings → Custom Domains →
   `dinerobook.com`. Add the `A` / `CNAME` records Render gives
   you to your DNS provider (Cloudflare in our case). Issue +
   verify the Let's Encrypt cert.
4. **Set the secrets that `render.yaml` marks `sync: false`.**
   These are intentionally NOT in the repo. Render → service →
   Environment → add each by hand:

   | Key | Where to find it |
   |---|---|
   | `STRIPE_SECRET_KEY` | Stripe → Developers → API keys → Secret key. Starts `sk_test_` in test mode, `sk_live_` in live. |
   | `STRIPE_PUBLISHABLE_KEY` | Same Stripe page, Publishable key. Must pair with the matching secret (`pk_test_` ↔ `sk_test_`). |
   | `STRIPE_WEBHOOK_SECRET` | Stripe → Webhooks → your endpoint → Signing secret. Starts `whsec_`. |
   | `STRIPE_BASIC_PRICE_ID` / `STRIPE_PRO_PRICE_ID` | Stripe → Products → Basic or Pro → Pricing → copy the price ID. Starts `price_`. |
   | `STRIPE_BASIC_YEARLY_PRICE_ID` / `STRIPE_PRO_YEARLY_PRICE_ID` | Same flow, "add additional price → yearly". Optional — leave blank to hide the yearly toggle on `/subscribe`. |
   | `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | Gmail SMTP is the quickest option: `smtp.gmail.com`, your address, a 16-char App Password (NOT your login), and the same address as From. |
   | `SENTRY_DSN` (optional) | Sentry → Settings → Projects → DSN. Leave blank to disable (no-op import). |
   | `RESEND_API_KEY` / `RESEND_WEBHOOK_SECRET` (optional) | Alternative transactional-email vendor. Either Resend OR SMTP — having both wired is fine but only one path fires per email. |

5. **First deploy.** Push `main` (or click "Manual Deploy" in
   Render). Watch the build log; failures here are usually:
   - **`scripts/build.sh` fails** → check the Node version. The
     script pins via `nodeenv`; if upstream Node changed a major
     line, bump the version in `scripts/build.sh`.
   - **`alembic_version` table mismatch** → DB was previously
     used by a different fork. Drop the DB or `flask
     alembic-stamp <revision>`.
6. **Verify the seed user.** First boot creates
   `superadmin / super2025!` and `admin / cambio2025!`. **Change
   both passwords immediately** via /superadmin and /admin
   logins. The seed values are also override-able via
   `SUPERADMIN_PASSWORD` / `ADMIN_PASSWORD` env vars in
   `render.yaml` — set those instead and re-deploy.
7. **Stripe webhook endpoint.** Stripe → Webhooks → Add endpoint
   → `https://dinerobook.com/webhooks/stripe`. Subscribe to:
     - `checkout.session.completed`
     - `customer.subscription.deleted`
     - `customer.subscription.updated`
     - `invoice.payment_failed`
   Copy the signing secret into `STRIPE_WEBHOOK_SECRET` (step 4)
   and re-deploy if it changed.
8. **Resend webhook endpoint (optional).** Resend → Webhooks →
   `https://dinerobook.com/webhooks/resend`. Subscribe to
   `email.delivered`, `email.bounced`, `email.complained`.
   Copy the signing secret to `RESEND_WEBHOOK_SECRET`.

## 2. Routine deploy

A normal feature deploy:

```bash
git checkout main
git pull --ff-only
# (Branch + PR work happens off-platform; merge the green PR.)
# Render auto-deploys on push to main.
```

Watch the Render → Events tab. A green deploy shows the build log
ending with `==> Your service is live 🎉`. If it shows yellow
(degraded), grep the runtime logs for the error.

### Roll back

Render → service → Manual Deploy → pick the previous successful
deploy (deploys are tagged by commit SHA). One click; no Git
revert needed on the repo.

For DB-schema rollbacks see §5.

## 3. Secrets rotation

* **Stripe live mode swap** (test → live):
  1. Verify the `dinerobook` Stripe account is in **Live mode**
     in the dashboard (top-right toggle).
  2. Pull live values for the five `STRIPE_*` env vars (step 4 in
     §1) and update them in Render → Environment.
  3. Add a webhook in **Live mode** Stripe → Developers →
     Webhooks → `https://dinerobook.com/webhooks/stripe`. Copy
     its signing secret into `STRIPE_WEBHOOK_SECRET`.
  4. Restart the service (env-var change → auto-restart).
  5. Verify via `/superadmin/controls` → Overview → "Stripe
     connection" card. The card shows `live` mode and the
     account's `id` once verified.
  6. Test the round-trip: take a fresh test Store off-trial,
     pick a plan at `/subscribe`, run a real card through, watch
     `/superadmin/controls` → Stores show the new `plan` =
     `basic` or `pro`.

* **SECRET_KEY**: don't rotate unless compromised. Rotating
  invalidates every active session (logs everyone out) AND every
  password-reset token in flight. If you must:
  1. Generate a new value (`python -c "import secrets;
     print(secrets.token_urlsafe(48))"`).
  2. Render → Environment → replace `SECRET_KEY`.
  3. Restart. Announce the forced re-login to all stores.

* **SMTP creds**: swap any time. No data dependency. New mail
  sends use the new creds on next request; in-flight resets
  remain valid (token lifetime is 1 hour and the token itself
  isn't tied to SMTP).

* **WEBAUTHN_RP_ID**: **don't rotate**. Passkeys are
  cryptographically bound to the rpId active at registration
  time. Changing this invalidates every existing passkey. If
  it's truly necessary (domain change), warn users in advance
  and provision a TOTP fallback before flipping.

## 4. Database

### Schema migrations

DineroBook uses a hybrid approach. Read
[`migrations.md`](migrations.md) for the full story, but in
short:

* **Adding a column** → append to `_ADDED_COLUMNS` at the bottom
  of `app.py`. `_ensure_added_columns()` runs on boot, idempotent.
* **New table** → just define the `db.Model` class; `db.create_all()`
  picks it up.
* **Dropping a column** → not allowed without coordination.
  See `migrations.md` for the deprecate-then-drop sequence.
* **Alembic** → baseline migration `99691740424c_baseline_2026_05`
  pins the current schema. Cutover (stamp + retire
  `_ADDED_COLUMNS`) is the open item in BACKLOG D4 phase 2.

### Backups

Render's managed Postgres takes daily snapshots automatically
(retention varies by plan). Verify via Render → Database →
Backups. **Before paid launch:**

1. Confirm snapshots are enabled on the current plan.
2. **Do a trial restore at least once.** Render → Database →
   Backups → restore to a new staging DB. Bring up a staging
   service pointed at it, log in, confirm the seeded data + a
   real transfer round-trip.
3. If restoring fails, escalate to Render support BEFORE going
   live. A backup you've never restored from is not a backup.

### Data-retention purge

Stores on the 180-day retention deadline are reaped by:

```bash
flask purge-expired-stores
```

Run on the Render Shell. Cascades through `_STORE_OWNED_MODELS`
before deleting the `Store` row. **Schedule this as a cron in
Render** (Render → service → Cron Jobs) so it doesn't depend on
human attention.

## 5. Incident playbook

| Symptom | First check | Likely fix |
|---|---|---|
| `502 Bad Gateway` from Render | Render → Logs → look for `WORKER TIMEOUT` | Restart the service. If it recurs, increase `--timeout 120` in the start command (already set). |
| `500` on every page | Sentry → most recent issue | Almost always a missed env var or a DB-schema drift after a release. |
| `503` from `/bank/stripe/connect` | `/superadmin/controls` → Stripe card | Either `STRIPE_SECRET_KEY` or `STRIPE_PUBLISHABLE_KEY` is missing/wrong. |
| Stripe webhook → no plan change | Stripe → Webhooks → Recent deliveries → 4xx/5xx? | Often `STRIPE_WEBHOOK_SECRET` is stale after a webhook rotation. Copy the current signing secret from Stripe and re-deploy. |
| Login screen → "Network error" | Render → Logs → `WORKER TIMEOUT` near `/api/v2/auth/*` | Was a real prod incident in early 2026 — `a2wsgi` bridge leaked asyncio tasks. Fix shipped: `asgi.py` routes `/api/v2/*` natively. If symptom recurs, check Logs for "ASGIMiddleware" tracebacks — escalation to maintainer. |
| 429 from `/login` after deploy | Logs show `ratelimit ... exceeded` | Honest — someone IS hammering /login from one IP. Confirm via IP in the log line. If false-positive (e.g. someone behind a NAT), bump the limit in `app.py` `_apply_rate_limits()`. |
| `flask reset-superadmin` won't accept | Stale 2FA recovery codes | Add `--reset-2fa` to wipe TOTP too. |

### When you don't know what changed

1. Render → Events → see the most recent deploy + its commit
   SHA.
2. `git log <prev-sha>..<deploy-sha>` shows what just shipped.
3. Sentry → filter by `release` if release tracking is set, OR
   filter by "first seen" within the deploy window.
4. If the change is small and clearly the trigger → roll back
   via Render dashboard (see §2 "Roll back"). DON'T edit prod
   files directly.

## 6. Pre-launch checklist (canonical copy)

The `BACKLOG.md` "Before going live" section is the authoritative
gate. Re-read it the morning of launch. As of 2026-05 the open
items are:

* SMTP env vars set + a real password-reset round-trip verified
  end-to-end
* Stripe LIVE mode swap (§3 secrets rotation) + a real card test
* DB backups verified via trial restore (§4)
* Data-retention purge cron scheduled (§4)
* Secrets audit: confirm no hardcoded keys; review `git log -p
  -- render.yaml` for any accidentally-committed values

Closed items don't need re-checking unless you've touched the
relevant code — track-via-PR; the BACKLOG marker tells you
exactly when it landed.

## 7. Local prod-parity dev

For a development loop that exactly matches production routing:

```bash
python -m uvicorn asgi:asgi_app --host 0.0.0.0 --port 5000
```

This boots the same `asgi.py` entrypoint Render uses, including
the native `/api/v2/*` routing that bypasses the leaky bridge.
Run it when you're debugging anything that touches the FastAPI
mount.

For day-to-day dev, `python app.py` (Flask dev server) is fine —
the bridge bug doesn't manifest in single-user sessions.

## 8. Doc maintenance contract

Update this doc when you:

* Change `render.yaml` env-var layout
* Rotate any service (Sentry, Resend, Stripe) at the
  infrastructure level
* Change the boot command in `render.yaml`
* Add a new "Before going live" item in BACKLOG.md (mirror it
  here under §6)
* Hit a new incident class — add a row to §5

An out-of-date runbook is worse than no runbook. Keep this
honest.
