# Cambio Express — Cloud Deployment Guide

---

## THE PROBLEM YOU SAW
Render couldn't find `render.yaml` because the files were inside
a subfolder in the zip. This version is fixed — all files sit at
the root level. Follow the steps below exactly.

---

## Step 1 — Create a GitHub Account & Repo

1. Go to **github.com** → Sign Up (free)
2. Click the **+** icon (top right) → **New repository**
3. Name: `cambio-express`
4. Set to **Private**
5. Click **Create repository**
6. Leave the browser tab open — you'll need it in Step 2

---

## Step 2 — Upload Your Files to GitHub

**Do NOT upload the zip file itself. Extract it first.**

### Easy method (no coding needed):
1. Extract this zip to a folder on your computer
2. On your new GitHub repo page, click **"uploading an existing file"**
   (it's a small link in the middle of the page)
3. **Drag ALL the extracted files and folders** into the upload box
   - You should see: `app.py`, `requirements.txt`, `render.yaml`,
     `Procfile`, `templates/` folder, etc. all at the top level
4. Scroll down → click **"Commit changes"**

### Verify it worked:
Your GitHub repo should look like this — files directly visible,
NOT inside another folder:
```
cambio-express/
├── app.py           ✅ visible at root
├── render.yaml      ✅ visible at root
├── requirements.txt ✅ visible at root
├── Procfile         ✅ visible at root
└── templates/       ✅ visible at root
```

---

## Step 3 — Deploy on Render.com

1. Go to **render.com** → Sign Up with your GitHub account
2. Click **"New +"** → **"Blueprint"**
3. Click **"Connect account"** → authorize GitHub
4. Find your `cambio-express` repo → click **"Connect"**
5. Render finds `render.yaml` automatically → click **"Apply"**
6. Wait 3–5 minutes for the first deploy

Your app will be live at:
`https://cambio-express.onrender.com`

---

## Step 4 — First Login & Setup

| Account | Username | Password |
|---|---|---|
| Platform Owner (you) | `superadmin` | `super2025!` |
| Demo Store Admin | `admin` | `cambio2025!` |

**Change both passwords immediately** → Users section.

---

## Step 5 — Set Environment Variables on Render

Go to your Render service → **Environment** tab → Add:

| Key | Value |
|---|---|
| `SECRET_KEY` | Any 32+ random characters (e.g. `xK9mP2...`) |
| `SUPERADMIN_PASSWORD` | Your new superadmin password |
| `ADMIN_PASSWORD` | Default password for new stores |

To generate a good SECRET_KEY, use: https://randomkeygen.com
(use the "256-bit WEP Keys" row)

After adding variables → click **"Save Changes"** → Render redeploys automatically.

---

## Step 6 — Connect SimpleFIN (Fixed)

The crash you had before is fully fixed. To reconnect:

1. Log in as store admin → **Bank / SimpleFIN**
2. Go to **beta-bridge.simplefin.org**
3. **Recommended:** If you already have a connection, click it →
   copy the **Access URL** (starts with `https://`) → paste that directly
4. If you need a fresh token: click "Add Data Connection" →
   copy the Setup Token → paste it in the app

---

## Adding New Customer Stores

1. Log in as `superadmin`
2. Dashboard → **All Stores** → **Add Store**
3. Fill in business name, create their admin login
4. Give them the URL and their credentials
5. They log in and set up their own SimpleFIN + employees

---

## Setting Up Stripe (When Ready to Charge Customers)

1. Create account at **stripe.com**
2. Go to **Developers → API Keys** → copy Secret Key
3. In Render → Environment → add `STRIPE_SECRET_KEY = sk_live_...`
4. In Stripe → **Webhooks** → Add endpoint:
   URL: `https://your-app.onrender.com/webhooks/stripe`
   Events: `customer.subscription.created`, `customer.subscription.deleted`
5. Copy the Webhook Signing Secret → add as `STRIPE_WEBHOOK_SECRET`
6. In `app.py`, find the `stripe_webhook` function and uncomment
   the handler code (it's clearly marked)

---

## Custom Domain

1. Buy a domain (Namecheap ~$10/yr)
2. Render → Your Service → **Settings → Custom Domains → Add**
3. Enter your domain (e.g. `app.cambioexpress.com`)
4. In Namecheap DNS settings, add:
   `CNAME  app  →  cambio-express.onrender.com`
5. SSL/HTTPS is automatic — takes ~10 minutes

---

## Suggested Pricing

| Plan | Price | Features |
|---|---|---|
| Trial | Free 14 days | 1 admin, 2 employees |
| Basic | $49/mo | 1 location, 5 employees |
| Pro | $99/mo | Unlimited employees, SimpleFIN, full P&L |

---

## Logins Summary

| Role | What They See |
|---|---|
| `superadmin` | All stores, can enter any store, platform overview |
| `admin` (store) | Full daily book, P&L, bank data, ACH batches, all employee transfers |
| `employee` | Only their own transfers, today's view |

