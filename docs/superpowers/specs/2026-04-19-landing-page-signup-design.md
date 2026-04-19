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

| Route | Before | After |
|---|---|---|
| `/` | Login page | Public landing page |
| `/login` | (new) | Login page (moved from `/`) |
| `/signup` | (new) | Self-service signup form |
| `/subscribe` | (new) | Plan selection → Stripe Checkout |

All internal redirects using `url_for("login")` must be updated to `url_for("login")` pointing to the new `/login` route.

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
- Secondary CTA: **"Learn More ↓"** → anchor to features (outline button)
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

Each card has a CTA button. Trial CTA → `/signup`. Basic/Pro CTAs → `/signup` (plan pre-selected in query param, used post-trial on subscribe page).

### Footer
- © 2026 Cambio Express
- Login link

---

## Signup Flow (`/signup`)

### Form Fields
| Field | Required | Notes |
|---|---|---|
| Store Name | Yes | Stored as `Store.name`; slug auto-generated |
| Email | Yes | Stored as `Store.email`; used as admin username |
| Password | Yes | Min 8 chars |
| Phone | No | Stored as `Store.phone` |

### On Submit
1. Validate required fields; show inline errors on failure
2. Check email not already registered (unique on `User.username`)
3. Create `Store(name=..., slug=slugify(name), email=..., phone=..., plan="trial")`
4. Create `User(store_id=store.id, username=email, role="admin", full_name=store_name)`
5. Set `store.trial_ends_at = datetime.utcnow() + timedelta(days=7)`
6. Log user in (set session) → redirect to `/dashboard`
7. No Stripe API call at this step

---

## Store Model Changes

Add two new columns to the `Store` model:

```python
trial_ends_at = db.Column(db.DateTime, nullable=True)
grace_ends_at = db.Column(db.DateTime, nullable=True)  # = trial_ends_at + 4 days
```

`grace_ends_at` is set at signup alongside `trial_ends_at`.

---

## Trial & Grace Period Enforcement

A helper function `get_trial_status(store)` returns one of:
- `"active"` — trial in progress, no banner
- `"expiring_soon"` — within 3 days of trial_ends_at, show yellow banner
- `"grace"` — past trial_ends_at but within grace_ends_at, show red banner
- `"expired"` — past grace_ends_at, soft lock

A `check_trial` decorator (or logic inside `login_required`) runs on every protected route:
- `"expiring_soon"` → inject yellow banner via flash or template variable
- `"grace"` → inject red banner
- `"expired"` → redirect to `/subscribe`

Stores on `"basic"` or `"pro"` plan (i.e., active Stripe subscription) skip all trial checks.
Superadmin skips all trial checks.

---

## Subscribe Page (`/subscribe`)

Shown when trial is expired (hard redirect) or accessible any time via banner CTA.

- Displays Basic ($20/mo) vs Pro ($30/mo) side-by-side
- User clicks a plan → POST to `/subscribe/checkout` with `plan=basic|pro`
- Server creates a Stripe Checkout Session:
  - Mode: `subscription`
  - Line item: the corresponding Stripe Price ID (configured via env vars `STRIPE_BASIC_PRICE_ID`, `STRIPE_PRO_PRICE_ID`)
  - `success_url`: `/subscribe/success`
  - `cancel_url`: `/subscribe`
- Redirect user to Stripe-hosted checkout URL

---

## Stripe Webhook (`/webhooks/stripe`)

Currently a stub. Implement handler for:

**`checkout.session.completed`**
- Retrieve the subscription from Stripe
- Match to store via `stripe_customer_id` or metadata
- Update `store.plan = "basic"` or `"pro"`
- Save `store.stripe_customer_id`, `store.stripe_subscription_id`

**`customer.subscription.deleted`**
- Revert `store.plan = "trial"` (or a new `"inactive"` status)
- Show upgrade prompt

Webhook signature verification via `STRIPE_WEBHOOK_SECRET` env var.

---

## Environment Variables Required

| Variable | Purpose |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe API key |
| `STRIPE_BASIC_PRICE_ID` | Stripe Price ID for Basic plan |
| `STRIPE_PRO_PRICE_ID` | Stripe Price ID for Pro plan |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification |

---

## Out of Scope (This Spec)

- Multi-store owner role and aggregate dashboard (separate spec)
- Email notifications (trial expiry reminders)
- Admin ability to manually override trial/plan from superadmin panel
- Coupon/discount codes
