# Recovery — Rebuilding the Render Stack

Use this when the `dinerobook` web service or `dinerobook-db` database on
Render has been deleted or is otherwise unreachable. The repo is the
source of truth; `render.yaml` declares the full stack and Render can
recreate it from scratch via Blueprint.

---

## Scenario A — Only the web service is gone, DB is intact

This is the easy case. Data is safe; recreate the service and it will
relink to the existing DB.

### Steps

1. Render Dashboard → **New +** → **Blueprint**.
2. Connect to `snehilmak/cambio-express`, branch `main`.
3. Render reads `render.yaml` and proposes:
   - web service `dinerobook`
   - database `dinerobook-db` (should say *"already exists, will link"*)
4. Click **Apply**.
5. Enter the `sync: false` secrets when Render prompts (see list below).
6. Wait 3–5 min for the first deploy. `_ensure_added_columns()` runs on
   boot and is idempotent — safe against an already-migrated DB.
7. App is back at `https://dinerobook.onrender.com`.

### Post-deploy verification

- Log in as `superadmin` and confirm stores/users are present (proves
  the DB relink worked).
- Stripe webhook endpoint: URL is unchanged
  (`https://dinerobook.onrender.com/webhooks/stripe`), but if the signing
  secret rotated, update `STRIPE_WEBHOOK_SECRET` in Render env.
- Custom domain: if one was attached to the old service, re-add it under
  **Settings → Custom Domains** and confirm DNS still points at
  `dinerobook.onrender.com`.

---

## Scenario B — Database is also gone

**Do not create a fresh empty `dinerobook-db` first.** Recover or restore
before running the Blueprint, otherwise the app boots against an empty
schema and seeds fresh superadmin/demo-store rows on top of nothing.

### Recovery path, in order of preference

1. **Render "recently deleted"** — free-plan Postgres is typically
   recoverable for ~7 days from the Render dashboard. Check there first.
2. **Render daily backup** — on paid plans Render snapshots daily; restore
   the most recent snapshot into a new DB named `dinerobook-db`.
3. **Local `pg_dump`** — if neither of the above works, restore from the
   newest `cambio-backup-*.sql` or equivalent dump you've kept offline:
   ```bash
   psql "$DINERO_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
   psql "$DINERO_URL" < cambio-backup-YYYY-MM-DD-HHMM.sql
   ```

Only after the DB is restored, run Scenario A's Blueprint steps.

---

## Secrets that must be re-entered

`render.yaml` marks these `sync: false` — Render prompts for them on
Blueprint apply and does not read them from the repo. Have them ready:

| Key | Where to find it |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe → Developers → API keys |
| `STRIPE_WEBHOOK_SECRET` | Stripe → Developers → Webhooks → endpoint → Signing secret |
| `STRIPE_BASIC_PRICE_ID` | Stripe → Products → Basic → Pricing |
| `STRIPE_PRO_PRICE_ID` | Stripe → Products → Pro → Pricing |
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_USER` | mailbox login |
| `SMTP_PASS` | app password (Gmail: 16-char app password, not the login password) |
| `SMTP_FROM` | from-address shown on password-reset emails |

`SUPERADMIN_PASSWORD` and `ADMIN_PASSWORD` have placeholder values in
`render.yaml` — override in the dashboard on first deploy.

---

## What NOT to do

- ❌ Do not hand-create a web service outside the Blueprint flow. It
  will drift from `render.yaml` and future deploys won't be reproducible.
- ❌ Do not rename the service or database. `render.yaml`'s
  `fromDatabase: name: dinerobook-db` assumes those exact names.
- ❌ Do not point the new service at the decommissioned `cambio-db` (see
  CLAUDE.md — decommissioned, do not reference).
- ❌ Do not skip restoring the DB before first boot; empty-schema boots
  seed a fresh superadmin/demo store on top of nothing.
