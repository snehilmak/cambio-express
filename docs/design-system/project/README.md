# DineroBook Design System

> A bookkeeping SaaS for Money Service Businesses (MSBs) — small shops that send remittances via Intermex, Maxi, and Barri and keep daily cash-ledger + monthly P&L.

## About the product

**DineroBook** is a multi-tenant web app. Each **Store** has admins + employees; multi-store **Owners** connect via invite codes; the platform runs under one **Superadmin**.

The product solves a real-world pain: MSB owners historically manage their shops on paper or Excel. DineroBook replaces that with:

- **Daily Books** — cash in/out, sales, money orders, check cashing, recorded every day
- **Money Transfers** — log Intermex / Maxi / Barri transfers with sender + recipient detail
- **ACH Batches** — reconcile ACH deposits against transfer totals and spot variances
- **Monthly P&L** — auto-populated profit/loss from daily reports
- **Bank Sync (Pro)** — Stripe Financial Connections for live bank balances
- **Multi-store (Owner portal)** — roll up reporting across a chain of stores

### Plans
- **Free Trial** — 7 days, full Pro access, no card
- **Basic** — $20 / store / month
- **Pro** — $30 / month (or $300 / year = 2 mo free)

## Sources

This design system was assembled from:

- **Codebase**: `snehilmak/cambio-express` on GitHub (commit `d22fa1d`). Flask 3.0 monolith (`app.py`, Jinja2 templates, a single shared `static/app.css`). Key files imported into this project root:
  - `CLAUDE.md` — engineering invariants (sidebar groupings, semantic tokens, trial state machine, etc.)
  - `BACKLOG.md` — deferred work
  - `static/app.css` — **the source of truth for all tokens & components**
  - `templates/*.html` — reference implementations
- No Figma file was provided. All visual decisions come from the codebase.

> The app's production URL is `https://dinerobook.onrender.com`. The GitHub repo itself still carries the old project name "cambio-express" — DineroBook is the product.

## Surfaces covered

| Surface | Role | Kit |
|---|---|---|
| Marketing landing page | prospects | `ui_kits/marketing/` |
| Admin dashboard + app shell | store admin, employee | `ui_kits/admin_app/` |
| Auth pages (login, signup) | everyone | `ui_kits/auth/` |

## Index

```
README.md                    ← you are here
SKILL.md                     ← agent skill manifest (for Claude Code use)
colors_and_type.css          ← all CSS variables + semantic classes
fonts/                       ← webfont references (see note below)
assets/                      ← logos, brand marks
preview/                     ← small cards rendered in the Design System tab
ui_kits/
  marketing/                 ← landing page UI kit (index.html + JSX components)
  admin_app/                 ← in-app UI kit (index.html + JSX components)
  auth/                      ← sign-in / sign-up kit
```

---

## CONTENT FUNDAMENTALS

DineroBook's writing voice is **operational and reassuring** — it addresses a small-business owner who is anxious about their books. It is **never salesy or playful**.

### Voice rules

- **Second person ("you", "your")** — *"Your Business. Crystal Clear."*, *"Stop managing your store on paper or spreadsheets."*
- **Short, declarative sentences.** The landing hero uses a two-line statement (*"Your Business. / Crystal Clear."*) followed by one explanatory sentence. No flowery prose.
- **Concrete nouns over marketing abstractions.** Says "transfers", "ACH batches", "daily books" — not "solutions", "workflows", "journeys".
- **Numbers and symbols are real.** Prices show as `$20`, `$30`. Money always uses two decimals with thousands separators: `$1,234.56`. Dates are `MM/DD` in tables, `Mar 14, 2026` in copy.
- **Status words are active and unambiguous.** `Sent`, `Pending`, `Canceled`, `Rejected`, `Refunded`, `Re-Transferred`, `Cleared`, `Disputed`, `Returned`, `Partial`.

### Casing

- **Section headings and nav labels**: Title Case — *"Daily Reports"*, *"ACH Batches"*, *"Bank & Subscription"*.
- **Eyebrow / section labels above headings**: UPPERCASE, letter-spaced 1–2px, gold accent — *"WHAT'S INCLUDED"*, *"SIMPLE PRICING"*.
- **Button labels**: Title Case, with optional arrow — *"Start Free Trial"*, *"View All"*, *"Connect Bank via Stripe →"*.
- **Form labels**: UPPERCASE, 12px, letter-spaced — *"USERNAME"*, *"FROM DATE"*.
- **Badges**: Title Case, colored per state.

### Tone

- **Tactical / utilitarian** when describing features: *"Log Intermex, Maxi, and Barri transfers with full sender and recipient detail. Find any transfer instantly."*
- **Direct / warning** for state changes: *"Your free trial ends in 3 days."* — *"👁 Impersonating Store Name — actions you take now are recorded as this store's admin."*
- **Friendly but brief** for success and empty states: *"✅ Entered"*, *"All clear"*, *"No transfers yet."*

### Emoji usage

DineroBook **does use emoji**, but sparingly and always functionally:
- **Sidebar nav icons** (`⬛ Dashboard`, `💸 Transfers`, `📅 Daily Reports`, `📦 ACH Batches`, `🏦 Bank Sync`, `💳 Billing`, `👥 Team`, `⚙️ Settings`, `🟢 System Status`, `📜 Audit Log`, `🎟️ Discount Codes`, `🚩 Feature Flags`, `📣 Announcements`)
- **Status/state prefixes in banners**: `⏳`, `🔴`, `👁`, `📣`, `✅`, `⚠️`
- **The landing page hero icon**: `💱`

They are **never decorative on buttons or body text**. They are never used for marketing bullet points instead of real icons.

### Examples (lifted from the codebase)

Landing hero:
> **Your Business. Crystal Clear.**
> Stop managing your store on paper or spreadsheets. DineroBook gives you real-time visibility into transfers, daily cash, and monthly profits.

Empty state:
> **No transfers yet.**

Trial warning:
> ⏳ Your free trial ends in **3 days**.   →   *Choose a Plan →*

Subscribe success:
> Start Free. Upgrade When Ready.

Referral hover:
> Earn $100 — share your referral code

---

## VISUAL FOUNDATIONS

### Palette

The brand palette is **dark navy + warm gold on warm cream**. This is a "trust + money" pairing — navy for authority/fintech, gold for the commodity (and an MSB's cash), cream/paper for a bookkeeping, ledger feel.

- **Navy `#0f1f3d`** — primary brand. Sidebar background, section headings, topbar titles, nav on the landing page. Always a solid deep navy; never gradients at small sizes.
- **Blue `#1a4080`** → **Mid `#2a5caa`** → **Sky `#3b82f6`** — action color ramp. Primary buttons, link accents, focus rings.
- **Gold `#c9973a`** → **Gold2 `#f0c060`** — accent. Active nav border, referral crown, brand logotype, "Pro" badges, hero CTAs on dark. Never the primary button — gold is for celebration + brand moments.
- **Cream `#faf7f2`** — default page background. **Paper `#f3ede3`** — a slightly dustier variant used rarely.
- **White `#ffffff`** — card surfaces in light mode.
- **Neutrals `#f5f5f7 / #e8e8ec / #b0b4c0 / #6b7280 / #1a1a2e`** — gray1 → gray4 → dark.

Semantic colors: green `#16a34a`, red `#dc2626`, orange `#ea580c`, yellow `#ca8a04`, with `-bg` and `-border` tints for banners/badges.

**Mode-aware semantic tokens** (`--surface`, `--surface-2`, `--surface-sticky`, `--text`, `--text-muted`, `--border`, `--border-strong`) flip on `[data-theme="dark"]`. Rule: *"Never use `--white` / `--gray1` / `--dark` for a surface or text that should adapt to dark mode"* — this is an explicit invariant in `CLAUDE.md`.

### Typography

Three families, all from Google Fonts:

- **DM Serif Display** — display serif. Used for the wordmark "DineroBook", hero headlines (`54px`), section headings (`36px`), stat card values (`30px`), empty-state titles (`20px`), modal titles. Never weights — DM Serif Display only ships in one weight.
- **DM Sans** — body UI face. Weights 300, 400, 500, 600. Everything that isn't a display headline or mono readout.
- **JetBrains Mono** — monospace for money, dates, IDs, ledger columns. Weights 400, 600. Amounts in tables, timestamps, referral codes.

The combination of a classical display serif + modern grotesque + typewriter mono creates the **"ledger book"** feel that differentiates DineroBook from generic SaaS.

### Spacing & rhythm

No explicit token scale is defined — the codebase uses direct pixel values. In practice the system uses an **8px base**:
- Card padding: `24px` (desktop) / `16px` (mobile)
- Section vertical rhythm: `20px` between section boxes, `28px` above a section divider
- Form field gaps: `18px` (two-column), `14px` (mobile)
- Content gutter: `32px` (desktop) / `16px` (mobile tablet) / `12px` (phone)

The utility classes `.mt-1/2/3` and `.mb-1/2/3` equal `8 / 16 / 24px`. A full scale is proposed in `colors_and_type.css` as `--space-1` … `--space-8`.

### Corners, borders, shadows

- **Corner radii**: cards `12px`, buttons `8px`, badges `999px` (full pill), inputs `8px`, modals `14px`, quick-link cards `10px`, small pills `6px`.
- **Borders**: `1px solid var(--gray2)` on cards by default; `1.5px` on inputs and outline buttons; `3px` gold accent on `.stat-card::before` and active nav `border-left`.
- **Shadows are minimal.** Cards are flat. Elevation is added only on:
  - Hover on quick-link cards (`0 4px 12px rgba(15,31,61,0.08)` + `translateY(-1px)`)
  - Dropdowns (`0 8px 28px rgba(15,31,61,0.15)`)
  - Modal backdrop (`0 20px 60px rgba(15,31,61,0.25)`)
  - Tooltips (`0 6px 18px rgba(15,31,61,0.25)`)

There is **no neumorphism**, **no inset shadow system**, **no color-tinted shadow beyond navy**.

### Backgrounds

- No hand-drawn illustrations.
- No repeating textures or patterns.
- Full-bleed imagery is **not** used — DineroBook's identity is text + numeric-first.
- The **only gradients** in the system are:
  1. Hero section on the landing page: `linear-gradient(135deg, var(--navy) 0%, var(--mid) 100%)` — navy to mid-blue.
  2. Login page left panel: `linear-gradient(145deg, #0f1f3d 0%, #1a3a6e 100%)`.
  3. Gold buttons/avatars: `linear-gradient(135deg, var(--gold) 0%, var(--gold2) 100%)`.
  4. Soft radial halos on the login left panel: gold @ 12% opacity and sky @ 8% opacity.

Dark mode uses flat backgrounds — `#0f1220` body, `#1a1f2e` surfaces, `#232838` surface-2.

### Animation & interaction

- **Transitions are fast and subtle.** `transition: all 0.15s` is the house default. Longer (`0.25s`) is reserved for the mobile sidebar slide.
- **No bounces, springs, or parallax.** Easing is linear / browser-default — utility over delight.
- **Hover states**:
  - Primary buttons: shift to a lighter blue (`blue → mid`).
  - Gold buttons: `gold → gold2` + text darkens to navy.
  - Outline buttons: fill with the border color.
  - Nav links: `color: white` + background `rgba(255,255,255,0.06)`.
  - Cards: `border-color: blue` + `translateY(-1px)` + soft shadow (quick-link only).
  - Table rows: background shifts to `gray1`.
- **Press states**: `transform: scale(0.96–0.97)` on avatar / crown. Buttons don't shrink.
- **Focus states**: `border-color: sky` + `0 0 0 3px rgba(59,130,246,0.1)` focus ring on inputs. Same on textareas/selects.

### Transparency & blur

Used sparingly. Two places only:
- Sticky save bar: `var(--surface-sticky)` which is `rgba(250,247,242,0.96)` + `backdrop-filter: blur(4px)`.
- Halo effects on the login-left radial gradients at 8–12% opacity.

### Layout rules

- **Fixed sidebar**: `240px` desktop, `260px` tablet (collapsed drawer on ≤900px). Position `fixed` with `z-index: 100`.
- **Sticky topbar**: `58px` tall, `z-index: 50`, sits inside `.main`. Inflates by `env(safe-area-inset-top)` on iOS PWA.
- **Grid rule**: `.grid-2` and `.grid-3` use `minmax(0, 1fr)` tracks — an invariant in `CLAUDE.md` to prevent wide children (the Money Transfer table) from overflowing their track.
- **Sticky save bar** at the bottom of long forms: pinned to `bottom: 0` with a backdrop blur and safe-area-inset-bottom on iOS.
- Mobile breakpoints: `900px` (sidebar collapses to drawer) and `480px` (single-column everything, stacked save bar).

### Cards

Flat white rectangle, 12px radius, 1px neutral border, no shadow.
`card-header` has 18×24 padding and a bottom border; `card-body` has 24 padding.
Specialized variants: `.stat-card` (with 3px gradient accent top stripe), `.quick-link-card` (icon-left mini-card), `.section-box` (report form section with a colored header band driven by `--sb-accent`).

### Iconography

See the ICONOGRAPHY section below.

---

## ICONOGRAPHY

DineroBook's iconography is **pragmatic, not curated**:

### What's in the codebase

- **Emoji as nav + section icons.** This is the primary icon system (see Content Fundamentals → Emoji). Every sidebar link carries a single emoji (`💸 Transfers`, `📅 Daily Reports`, etc). This is unusual for a fintech but appropriate for a small-business product that prioritizes clarity and rapid team onboarding over polish.
- **Unicode geometric glyphs** for abstract concepts: `⬛` (Dashboard), `＋` (Add / New), `×` (Close), `✕` (Dismiss), `✓` (Check / Success), `→` / `↓` (directional arrows inside CTAs), `•` (separator).
- **Hand-rolled inline SVGs** in `base.html` for:
  - Hamburger menu (`<svg>` with three `<line>`s)
  - Sun / Moon theme toggle (stroke-only, 2px round caps)
  - Clipboard copy icon
  - Check icon (swapped in after copy success)
  - Crown glyph (filled, on the gold referral badge)
- **The wordmark logo**: `static/logo.svg` — a small SVG. PNGs at 192/512 for PWA icons.

No icon library (Lucide, Heroicons, FontAwesome, Material Icons) is installed. Icons are inline SVG or emoji only.

### Rule for new designs

1. **Prefer the existing emoji set** when a sidebar-style nav icon is needed — consistency beats "cleaner" replacements.
2. **Inline-SVG with stroke-based geometry** (like the sun/moon/hamburger) is the house style for true UI chrome (toggles, close buttons, carets, copy). Match: `stroke-width: 2`, `stroke-linecap: round`, `stroke-linejoin: round`, `fill: none`, `currentColor`.
3. **Do not introduce an icon font or a CDN icon pack** without explicit approval — it would break the established voice.
4. **PNG icons are used only for PWA manifest / apple-touch-icon** (192px, 200px, 512px of the logo).

### Assets

| File | Use |
|---|---|
| `assets/logo.svg` | Primary wordmark (reconstructed — see caveat). Flagged: the original `static/logo.svg` was not importable in the initial batch. |
| `assets/logo-192.png` | PWA icon + apple-touch fallback |
| `assets/logo-512.png` | PWA splash / apple-touch-icon |

### Emoji inventory used by DineroBook

```
Nav/Section:   ⬛ 💸 ＋ 📅 📊 📦 🏦 👥 ⚙️ 💳 🏪 🎟️ 🚩 📣 🟢 📜 👑 📲 🔔 🚪
Status:        ⏳ 🔴 👁 ✅ ⚠️ 🟢 ✓ ✕ ✗
Brand hero:    💱
Company tags:  (none — companies are spelled out: Intermex / Maxi / Barri)
```

---

## Fonts — substitution note

All three families (DM Serif Display, DM Sans, JetBrains Mono) are loaded from Google Fonts via `https://fonts.googleapis.com/css2?...` in `base.html`, `landing.html`, and `login.html`. No self-hosted `.ttf` / `.woff2` files live in the repo — DineroBook is online-only and relies on the Google Fonts CDN.

**No substitution was needed.** This design system links the same Google Fonts URL. If you ever self-host these, grab:
- DM Serif Display — Regular 400
- DM Sans — 300, 400, 500, 600
- JetBrains Mono — 400, 600

---

## Caveats — please review

- **`static/logo.svg` failed to import** from GitHub in the first batch (likely flagged as oversized/invalid — it's only 891 bytes, so probably a transient fetch issue). I reconstructed a clean DineroBook wordmark+icon lockup in `assets/logo.svg` using the brand palette. **Please replace with the real logo** if you want pixel fidelity.
- **No Figma was provided.** All UI-kit recreations come from the Jinja2 templates. They should be pixel-accurate because the CSS is shared verbatim via `colors_and_type.css`.
- **No sample slide deck** was provided, so no `slides/` folder was created.
- **The `app.py` file (203KB)** wasn't imported — it's the backend source of truth for business logic, not visuals. I worked entirely from `static/app.css` + templates.
- **The repo name on GitHub is `cambio-express`** (a legacy pre-rename). The current product name is DineroBook.
