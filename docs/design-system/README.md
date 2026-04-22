# DineroBook Design System — source of truth

**If you are touching any UI or UX in DineroBook, read this file first.** It is the canonical reference for how the product looks and feels. Do not reach for Bootstrap, Tailwind, Material, or any other library — this system is the house style.

This bundle was exported from [`claude.ai/design`](https://claude.ai/design) and committed here on 2026-04-22. It captures the **dark-first, Robinhood-inspired** direction the product landed on after two iterations with the user.

## TL;DR — the rules

1. **Dark only.** `data-theme="dark"` is unconditional across the app. No light-mode fallback exists or should be re-introduced.
2. **One saturated color.** Neon green `#3fff00` is the ONLY primary accent. Use it for: CTAs, positive values, active nav indicators, the primary chart stroke. Everything else is cool gray so the neon actually reads.
3. **Typography.**
   - **Space Grotesk** — display / headlines / brand wordmark / stat values (`--db-font-display`)
   - **Inter** — body + UI labels (`--db-font-body`)
   - **JetBrains Mono** — every number, timestamp, ID, ticker, section eyebrow (`--db-font-mono`)
4. **Surfaces.** Five near-black layers (`--db-bg`, `--db-bg-elevated`, `--db-bg-raised`, `--db-bg-input`, `--db-bg-popover`). Pure `#000` is reserved for full-bleed hero/video only.
5. **Elevation.** Dark = subtle border + inner glow. **Never** drop shadows on cards. Neon glow is reserved for the active/hover states of neon elements.
6. **Radii.** Cards `14-16px`, buttons `10px`, pills `999px`, inputs `10px`.
7. **Emoji is retired for nav.** Nav icons are inline stroke SVGs (`stroke-width:2; stroke-linecap:round; fill:none; currentColor`). Emoji only survives in status/eyebrow prefixes (`⏳ trial ends`, `🔴`, `📣`) and the hero `$` brand mark (which is set as Space Grotesk text, not an emoji).

## How this maps to live production code

| Design-system asset | Lives in code at |
|---|---|
| `project/colors_and_type.css` (tokens) | `static/design-tokens.css` — renamed `--db-*` + legacy-token aliases |
| `project/ui_kits/admin_app/Sidebar.jsx` | `templates/base.html` sidebar + `static/shell.css` |
| `project/ui_kits/admin_app/Topbar.jsx` | `templates/base.html` topbar + `static/shell.css` |
| `project/ui_kits/admin_app/StatCards.jsx` | `static/content.css` `.stat-card` (richer sparklines are phase C.2) |
| `project/ui_kits/admin_app/TransfersTable.jsx` | `templates/transfers.html` + `static/content.css` table rules |
| `project/ui_kits/admin_app/Dashboard.jsx` | `templates/dashboard_admin.html` + `static/content.css` |
| `project/ui_kits/auth/LoginLeft.jsx`, `LoginRight.jsx` | `templates/login.html` (and `_login_chrome.html` for 2FA) |
| `project/ui_kits/marketing/Hero.jsx` + `HeroIsometric.jsx` | `templates/landing.html` hero section (isometric inlined as SVG) |
| `project/ui_kits/marketing/Features.jsx` + `Mocks.jsx` | `templates/landing.html` features section |
| `project/ui_kits/marketing/Pricing.jsx` | `templates/landing.html` pricing section |
| `project/ui_kits/marketing/FAQ.jsx` | `templates/landing.html` FAQ (native `<details>`) |
| `project/ui_kits/marketing/HowItWorks.jsx` + `CTABand.jsx` + `Footer.jsx` | `templates/landing.html` |
| `project/assets/logo*.{svg,png}` | `static/logo.svg`, `static/logo-192.png`, `static/logo-512.png` |

`colors_and_type.css` (in the bundle) uses names like `--neon` and `--bg`. The live tokens use `--db-*` prefixed names to avoid colliding with legacy `app.css` vars during the migration — same values, namespaced.

## When you make UI changes

1. **Read this file and `project/README.md`.** The README in `project/` has the detailed content, voice, and layout rules (8px spacing base, 240px sidebar, how gradients are used, etc.) — don't re-invent them.
2. **Look in `project/ui_kits/`** for the closest existing component. If you're building a new page, find the kit file that matches the surface (marketing/auth/admin) and pixel-reference it.
3. **Add tokens to `static/design-tokens.css`**, not to individual templates. If you need a new semantic color, add it as a `--db-*` token with a comment explaining its role.
4. **Use `static/content.css` class overrides** if your change affects a legacy class like `.card` or `.badge`. Template-specific styles go in `{% block head %}`.
5. **Preserve the neon discipline.** If you feel the urge to add a second saturated color (blue, purple, gold, whatever) — don't. The single-neon rule is load-bearing for how the brand reads. Use `--db-co-intermex/maxi/barri` for the three company tints when you need the jewel tones; use `--db-info/warning/negative` for state colors; otherwise stay in cool gray.

## Layout of this directory

```
docs/design-system/
├── README.md               ← you are here
├── AGENTS_HANDOFF.md       ← original handoff instructions from claude.ai/design
├── chats/chat1.md          ← the user's full iteration transcript — READ THIS
│                             to understand why we landed on dark+neon
└── project/
    ├── README.md           ← detailed tone, voice, palette, layout rules
    ├── CLAUDE.md           ← engineering invariants from the design side
    ├── SKILL.md            ← skill manifest (note: describes the PRE-pivot
    │                         navy/gold system — ignore the colors in SKILL;
    │                         colors_and_type.css is the source of truth)
    ├── BACKLOG.md          ← deferred design work
    ├── colors_and_type.css ← CSS tokens + semantic type classes
    ├── assets/             ← brand logo files
    ├── preview/            ← small example cards for each token/component
    └── ui_kits/
        ├── marketing/      ← full landing-page UI kit (React components)
        ├── admin_app/      ← in-app shell + dashboard + transfers + daily book
        └── auth/           ← split-pane login/signup layout
```

## Out-of-date notes in the bundle

A few things in the bundle describe an earlier iteration the user rejected. The chat transcript explains the pivot. Skim it if you see a disagreement between files.

- `project/SKILL.md` describes the pre-pivot **navy + gold + cream** palette. That palette is **dead**. Use `colors_and_type.css` + the live `static/design-tokens.css`.
- `project/README.md` has both the pre-pivot visual-foundations section (navy/gold) and the new voice rules. Palette-wise trust `colors_and_type.css`; voice-wise trust the README.
- `project/CLAUDE.md` (inside the bundle) references the legacy invariants. The **repo-root** `CLAUDE.md` is the actual source of truth for engineering rules.

## Phase roadmap

- **Phase A/B** (shipped) — design tokens, app shell (sidebar + topbar).
- **Phase C** (shipped, PR #75) — every template on the dark+neon system: landing, auth, dashboards, transfers, reports, batches, bank, admin, subscribe, superadmin, owner portal, 2FA, static pages.
- **Phase C.2** (open) — port the richer kit components from `ui_kits/admin_app/`: sparklines on stat cards, 14-day volume area chart, stacked company breakdown bar, ACH variance cards.
- **Phase D** (open) — retire the legacy `--navy / --gold / --cream` tokens from `app.css` once a week of main has confirmed nothing still references them.
