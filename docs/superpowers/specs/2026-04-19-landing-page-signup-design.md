# Landing Page + Self-Service Signup — Design Spec
**Date:** 2026-04-19  
**Project:** Cambio Express (cambio-express on Render / GitHub: snehilmak/cambio-express)  
**Stack:** Flask, SQLAlchemy, Jinja2, Stripe, PostgreSQL on Render

---

## Overview

Add a public-facing marketing landing page at `/` and a self-service signup flow so prospective customers can discover the product, start a 1-week free trial (no credit card required), and later subscribe to a paid plan via Stripe Checkout.

---

## Goals

- Any visitor can sign up and immediately start a 7-day free trial with full Pro-level access
- No credit card required at signup
- After trial ends, a 4-day grace period gives users time to subscribe
- Stripe Checkout handles all billing when they upgrade
- Existing superadmin and store admin flows are unaffected

---

## Route Changes

| Route | Methods | Before | After |
|---|---|---|---|
| `/` | GET | Login page | Public landing page |
| `/login` | GET, POST | (moved from `/`) | Login page |
| `/signup` | GET, POST | (new) | Self-service signup form |
| `/subscribe` | GET | (new) | Plan selection page |
| `/subscribe/checkout` | POST | (new) | Creates Stripe Checkout Session, redirects to Stripe |
| `/subscribe/success` | GET | (new) | Post-payment confirmation page |
| `/webhooks/stripe` | POST | Stub | Full Stripe event handler |

All internal `redirect(url_for("login"))` calls throughout `app.py` must be updated to point to the new `/login` route name.

---

## Landing Page (`/`)

**Layout:** Classic SaaS — Navbar → Hero → Features → Pricing → Footer

### Navbar
- Left: Cambio Express logo + "MSB Manager" tagline
- Right: Features (anchor) | Pricing (anchor) | Login (link to `/login`)
- Sticky on scroll

### Hero
- Headline: **"Your Business. Crystal Clear."**
- Subtext: "Stop managing your store on paper or spreadsheets. DineroSync gives you real-time visibility into transfers, daily cash, and monthly profits."
- Primary CTA: **"Try Free for 7 Days"** → `/signup` (gold button)
- Secondary CTA: **"Learn More ↓"** → anchor to features section (outline button)
- Below CTAs: "No credit card required · Cancel anytime"
- Background: navy-to-blue gradient matching existing brand (`--navy` → `--blue`)

### Features Section
Six feature cards in a 3-column grid:

| Feature | Description |
|---|---|
| Daily Books | Track cash in/out, sales, money orders, check cashing every day |
| Money Transfers | Log Intermex, Maxi, Barri transfers with full sender/recipient detail |
| ACH Batches | Reconcile ACH deposits against transfer totals |
| Monthly P&L | Auto-populated profit & loss from daily reports |
| Bank Sync *(Pro)* | Connect via SimpleFIN to see live bank balances |
| Reports | Filter transfers by date, company, and status |

### Pricing Section
Three cards, Pro highlighted as "Most Popular":

| Plan | Price | Key Features |
|---|---|---|
| Free Trial | $0 / 7 days | Full Pro access, no card needed |
| Basic | $20 / month | All features except bank sync |
| **Pro** *(highlighted)* | **$30 / month** | Everything + SimpleFIN bank sync + multi-store (coming soon) |

Each card has a CTA button. Trial CTA → `/signup`. Basic/Pro CTAs → `/signup` (plan pre-selected in query param, used on subscribe page after trial).

### Footer
- © 2026 Cambio Express
- Login link

---

## Signup Flow (`/signup`)

### Form Fields
| Field | Required | Notes |
|---|---|---|
| Store Name | Yes | Stored as `Store.name`; slug auto-generated via `slugify()` |
| Email | Yes | Stored as `Store.email`; used as admin `User.username` |
| Password | Yes | Min 8 chars |
| Phone | No | Stored as `Store.phone` |

### On Submit (POST)
1. Validate required fields; re-render form with inline errors on failure
2. Check email uniqueness: query `User.query.filter_by(username=email).filter(User.store_id != None).first()` — if found, show "An account with this email already exists"
3. Create `Store(name=..., slug=slugify(name), email=..., phone=..., plan="trial")`
4. `db.session.flush()` to get `store.id`
5. Set `store.trial_ends_at = datetime.utcnow() + timedelta(days=7)`
6. Set `store.grace_ends_at = store.trial_ends_at + timedelta(days=4)`
7. Create `User(store_id=store.id, username=email, role="admin", full_name=store_name)`
8. `user.set_password(password)`
9. `db.session.commit()`
10. Set session: `session["user_id"]`, `session["role"]`, `session["store_id"]`
11. Redirect to `/dashboard`
12. No Stripe API call at this step

---

## Store Model Changes

Add two new columns to the `Store` model:

```python
trial_ends_at = db.Column(db.DateTime, nullable=True)
grace_ends_at = db.Column(db.DateTime, nullable=True)  # trial_ends_at + 4 days
```

Both are `nullable=True` to support:
- Stores created by superadmin (no trial — treated as permanently active)
- Existing stores in the database before this feature was added

---

## Trial & Grace Period Enforcement

### `get_trial_status(store)` helper

Returns one of four values:

| Status | Condition |
|---|---|
| `"exempt"` | `store.trial_ends_at is None` OR `store.plan in ("basic", "pro")` |
| `"active"` | `now < trial_ends_at - 3 days` |
| `"expiring_soon"` | `trial_ends_at - 3 days <= now < trial_ends_at` |
| `"grace"` | `trial_ends_at <= now < grace_ends_at` |
| `"expired"` | `now >= grace_ends_at` |

Superadmin (role = `"superadmin"`) always returns `"exempt"` without checking the store.

### Enforcement

Add `trial_status` to every `@login_required` route's template context (or use a `@app.context_processor`):

- `"expiring_soon"` → yellow banner in `base.html`: "Your trial ends in X days — [Choose a plan]"
- `"grace"` → red banner in `base.html`: "Your trial has ended — [Upgrade now] to keep access"
- `"expired"` → redirect to `/subscribe` before rendering any page
- `"exempt"` or `"active"` → no banner, normal access

---

## Subscribe Page (`/subscribe`) — GET

Shown on redirect when expired, or accessible any time via banner CTA. Requires login.

- Displays Basic ($20/mo) vs Pro ($30/mo) side-by-side (same pricing card style as landing page)
- Each card has a form with a hidden `plan` field (`basic` or `pro`) that POSTs to `/subscribe/checkout`

---

## Subscribe Checkout (`/subscribe/checkout`) — POST

Requires login. Reads `plan=basic|pro` from form data.

Creates a Stripe Checkout Session:
- `mode="subscription"`
- `line_items`: one item using `STRIPE_BASIC_PRICE_ID` or `STRIPE_PRO_PRICE_ID` env var
- `metadata={"store_id": str(store.id)}` — used by webhook to identify the store
- If `store.stripe_customer_id` exists, pass `customer=store.stripe_customer_id` to reuse the Stripe customer
- `success_url`: `url_for("subscribe_success", _external=True)`
- `cancel_url`: `url_for("subscribe", _external=True)`

Redirect user to `session.url` (Stripe-hosted checkout page).

---

## Subscribe Success (`/subscribe/success`) — GET

Requires login. Shown after Stripe redirects back.

- Display a "Payment received — activating your account" confirmation message
- **Do not** update `store.plan` here — wait for the webhook (Stripe guarantees webhook delivery even if the user closes the tab)
- If `store.plan` is already updated (webhook arrived first), show "You're all set — welcome to [Basic/Pro]!"
- Poll or show a simple "refresh in a moment" message if plan is still `"trial"`

---

## Stripe Webhook (`/webhooks/stripe`) — POST

Verify signature using `STRIPE_WEBHOOK_SECRET`. Return 400 on invalid signature.

**`checkout.session.completed`**
1. Read `store_id` from `event.data.object.metadata["store_id"]`
2. Look up `Store.query.get(store_id)`
3. Retrieve full subscription from Stripe: `stripe.Subscription.retrieve(session.subscription)`
4. Determine plan from the Price ID: match against `STRIPE_BASIC_PRICE_ID` / `STRIPE_PRO_PRICE_ID`
5. Update `store.plan`, `store.stripe_customer_id`, `store.stripe_subscription_id`
6. Commit

**`customer.subscription.deleted`**
1. Find store by `stripe_subscription_id`
2. Set `store.plan = "inactive"` (not `"trial"` — grace period is long past)
3. `store.stripe_subscription_id = ""`
4. Commit
5. On next login, `get_trial_status` returns `"expired"` for `"inactive"` plan → redirect to `/subscribe`

Note: update `get_trial_status` to treat `store.plan == "inactive"` as `"expired"` regardless of dates.

---

## Dependencies

Add to `requirements.txt`:
```
stripe==9.12.0
python-slugify==8.0.4
```

Add to `app.py` imports section:
```python
import stripe
from slugify import slugify
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
```

---

## Database Migration

`app.py` uses `db.create_all()` which does **not** add columns to existing tables. The two new `Store` columns (`trial_ends_at`, `grace_ends_at`) must be added manually for any existing Render PostgreSQL database:

```sql
ALTER TABLE store ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP;
ALTER TABLE store ADD COLUMN IF NOT EXISTS grace_ends_at TIMESTAMP;
```

Run these via the Render PostgreSQL console before deploying. New deployments on a fresh database will work automatically via `db.create_all()`.

---

## Environment Variables Required

| Variable | Purpose |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe API secret key |
| `STRIPE_BASIC_PRICE_ID` | Stripe Price ID for Basic plan ($20/mo) |
| `STRIPE_PRO_PRICE_ID` | Stripe Price ID for Pro plan ($30/mo) |
| `STRIPE_WEBHOOK_SECRET` | Webhook endpoint signing secret |

---

## Out of Scope (This Spec)

- Multi-store owner role and aggregate dashboard (separate spec)
- Email notifications (trial expiry reminders)
- Admin ability to manually override trial/plan from superadmin panel
- Coupon/discount codes
