---
name: dinerobook-design
description: Use this skill to generate well-branded interfaces and assets for DineroBook, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick reference

- DineroBook is a bookkeeping SaaS for Money Service Businesses (MSBs).
- Palette: **navy `#0f1f3d`** + **gold `#c9973a`/`#f0c060`** on **cream `#faf7f2`**.
- Type: **DM Serif Display** (headlines), **DM Sans** (UI), **JetBrains Mono** (money/dates/IDs).
- Voice: second-person, declarative, utilitarian. No marketing fluff.
- Emoji OK in nav + status, never as body decoration.
- Radii: cards 12px, buttons 8px, pills 999px. Flat — shadows only on hover/overlay.
- Sidebar nav groupings: **Workspace · Books · Finance · Account** (+ **Platform** for superadmin).

Always link `colors_and_type.css` (tokens) + `preview/_shared.css` (components) for quick prototypes; for production accuracy, reference the original `app.css` in the cambio-express repo.
