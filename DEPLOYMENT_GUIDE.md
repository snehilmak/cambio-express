# Cambio Express — Cloud Deployment & SaaS Setup Guide

---

## What's in This Package

| File | Purpose |
|---|---|
| `app.py` | Main application (all bugs fixed) |
| `requirements.txt` | Python dependencies |
| `Procfile` | Tells cloud how to start the app |
| `render.yaml` | One-click deploy to Render.com |
| `railway.json` | One-click deploy to Railway.app |
| `runtime.txt` | Pins Python version |
| `START_SERVER.bat` | Run locally on Windows |
| `templates/` | All HTML pages |

---

## OPTION A — Deploy to Render.com (Recommended)
**Cost: Free to start, ~$14/mo for production**

### Step 1 — Put your code on GitHub
1. Go to **github.com** → Sign up free → New repository
2. Name it `cambio-express` → Create repository
3. Download **GitHub Desktop** from desktop.github.com
4. Clone your new repo, copy all files from this folder into it
5. Commit and Push

### Step 2 — Deploy on Render
1. Go to **render.com** → Sign up with your GitHub account
2. Click **"New +"** → **"Blueprint"**
3. Connect your `cambio-express` GitHub repo
4. Render reads your `render.yaml` automatically
5. Click **"Apply"** — it creates the web app AND the database together
6. Wait ~3 minutes for first deploy

### Step 3 — Your app is live
Render gives you a URL like: `https://cambio-express.onrender.com`

**First login:**
- Superadmin: `superadmin` / `super2025!`
- Store admin: `admin` / `cambio2025!`

**⚠️ Change both passwords immediately** in the Users section.

---

## OPTION B — Deploy to Railway.app
**Cost: ~$5/mo, faster cold starts than Render free tier**

1. Go to **railway.app** → Sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select `cambio-express`
4. Railway auto-detects Python and deploys
5. Go to **Variables** tab, add:
   ```
   SECRET_KEY        = (any random 32+ character string)
   SUPERADMIN_PASSWORD = (your chosen password)
   ADMIN_PASSWORD    = (your chosen password)
   ```
6. Add a **PostgreSQL** plugin from the Railway dashboard
7. Railway auto-sets `DATABASE_URL` — no extra config needed

---

## Environment Variables (Required in Production)

Set these in your hosting platform's dashboard:

| Variable | What It Is | Example |
|---|---|---|
| `SECRET_KEY` | Random secret for session security | `x9k2m...` (32+ chars) |
| `DATABASE_URL` | Auto-set by Render/Railway | `postgresql://...` |
| `SUPERADMIN_PASSWORD` | Your platform owner password | Strong password |
| `ADMIN_PASSWORD` | Default password for new stores | Strong password |
| `STRIPE_SECRET_KEY` | From Stripe dashboard | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | From Stripe webhook settings | `whsec_...` |

**Generate a secure SECRET_KEY** — run this in Python:
```python
import secrets
print(secrets.token_hex(32))
```

---

## Setting Up Stripe (Billing for Customers)

### Step 1 — Create Stripe account
1. Go to **stripe.com** → Create account
2. Go to **Developers → API Keys**
3. Copy your **Secret Key** (`sk_live_...`)
4. Add it as `STRIPE_SECRET_KEY` environment variable

### Step 2 — Create a Product in Stripe
1. In Stripe → **Products** → Add Product
2. Name: "Cambio Express Pro"
3. Price: $X/month (recurring)
4. Copy the **Price ID** (`price_...`)

### Step 3 — Create a Payment Link
1. In Stripe → **Payment Links** → Create
2. Select your product/price
3. Add a **success URL**: `https://your-app.com/dashboard`
4. Share this link with businesses that want to subscribe

### Step 4 — Enable Webhooks (so app knows when someone pays)
1. Stripe → **Developers → Webhooks** → Add endpoint
2. URL: `https://your-app.onrender.com/webhooks/stripe`
3. Events to listen for:
   - `customer.subscription.created`
   - `customer.subscription.deleted`
   - `customer.subscription.updated`
4. Copy the **Signing Secret** → add as `STRIPE_WEBHOOK_SECRET`
5. In `app.py`, uncomment the Stripe webhook handler code (see comments in file)

---

## Your Business Model — How to Sell to Other Stores

### How it works
- Each MSB business gets their own isolated account
- You (superadmin) create the account for them → they pay you
- Their employees only see their store's data
- You can log in as any store to help them troubleshoot

### Onboarding a new customer
1. Log in as `superadmin`
2. Go to **Platform → Stores → Add Store**
3. Enter their business name, create their admin login
4. Give them their login URL and credentials
5. They log in, set up SimpleFIN, add their employees

### Pricing ideas
| Plan | Features | Price |
|---|---|---|
| Trial | 14 days, 1 user | Free |
| Basic | 3 users, daily book, transfers | $49/mo |
| Pro | Unlimited users, SimpleFIN, full P&L | $99/mo |

---

## Custom Domain (Make it look professional)

### On Render:
1. Dashboard → Your service → **Settings → Custom Domains**
2. Add `app.cambioexpress.com` (or whatever you want)
3. Go to your domain registrar (GoDaddy, Namecheap, etc.)
4. Add a **CNAME record**: `app` → `cambio-express.onrender.com`
5. Render auto-provisions SSL (HTTPS) — takes ~10 minutes

---

## Database Backups

### Render (automatic):
- Free tier: no automatic backups — export manually monthly
- Paid tier ($7/mo): daily automatic backups

### Manual backup anytime:
In your hosting dashboard → PostgreSQL → Export → Download SQL file
Keep a copy on Google Drive monthly.

---

## SimpleFIN — Fix for Your Error

The error you saw was caused by the setup token having incorrect base64 padding.
The new `app.py` fixes this completely.

**How to reconnect:**
1. Go to **beta-bridge.simplefin.org**
2. If your old token was already claimed: click your connection → **"Rotate Access Token"**
3. Copy the new access URL (starts with `https://`) — paste the full URL directly
4. OR generate a fresh setup token and paste that

**Paste the full access URL if you have it** — this is the most reliable method
and skips the base64 step entirely.

---

## Security Checklist Before Going Live

- [ ] Change `superadmin` password from default
- [ ] Change `admin` password from default
- [ ] Set a real `SECRET_KEY` (32+ random chars)
- [ ] Enable HTTPS (automatic on Render/Railway)
- [ ] Set up Stripe in live mode (not test mode)
- [ ] Test SimpleFIN connection with a real token
- [ ] Do a test transfer and verify it saves correctly

---

## Support & Next Steps

Future features you can add:
- **Email notifications** when ACH hits (use SendGrid — free tier)
- **PDF daily reports** (exportable version of daily book)
- **Multi-location** per store (one admin, multiple branches)
- **Stripe ACH** for collecting subscription fees automatically
- **SMS alerts** for employees when transfer status changes (Twilio)
