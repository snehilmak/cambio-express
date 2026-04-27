# TV-Display catalog logo seed directory

Drop logo files into `companies/` or `banks/` and they auto-import
into the catalog on the next deploy / app restart.

## How it works

1. App boots → `_seed_tv_logos_from_disk()` runs as part of `init_db()`.
2. For each file `<slug>.<ext>` in `companies/` or `banks/`:
   - If `<slug>` matches an existing row in the corresponding catalog
     table (`TVCompanyCatalog` for `companies/`, `TVBankCatalog` for
     `banks/`),
   - **AND** there's no logo already in `TVCatalogLogo` for that
     `(catalog_type, slug)`,
   - The file's bytes are imported and the parent row's `logo_url`
     is updated.
3. Re-running is a no-op for any slug that already has a logo. UI
   uploads via `/superadmin/controls?tab=tv-catalog` always take
   precedence — drop-in seeds never override an operator's manual
   upload.

## File naming

Files must be named exactly `<slug>.<ext>` where `<slug>` matches a
catalog row's slug (the immutable key, not the display name).

- Company slug examples: `intermex`, `maxi`, `barri`, `vigo`,
  `western_union`, `boss_revolution`. See `_DEFAULT_TV_COMPANIES` in
  `app.py` for the full list.
- Bank slug examples: `mx_bbva_bancomer`, `gt_banrural`,
  `hn_atlantida`. Country-prefixed; see `_DEFAULT_TV_BANKS` in
  `app.py`.

## Supported formats

- `.svg` — strongly preferred. Scales perfectly on TV, no aspect
  drama, smaller files than equivalent PNGs.
- `.png` — fine. Use a transparent background.
- `.jpg` / `.jpeg` — fine. Will look bad on dark theme if the source
  has a white background; prefer PNG/SVG when possible.
- `.webp` — fine.

Files larger than **200 KiB** are silently skipped (matches the
upload-endpoint hard cap). Most brand logos in vector form are well
under 50 KiB.

## Where to source logos

- **Brand press kits / media downloads.** Most companies have a
  "Brand Resources" or "Press" page that links downloadable assets
  in PNG + SVG. This is the cleanest source.
- **Wikimedia Commons.** Has SVG versions of most major bank logos.
  Check the licensing on each — many are public domain or
  permissive.
- **Brandfetch / SimpleIcons / Logo APIs.** Fast for prototyping.
  Verify license before shipping.

### Nominative-use reminder

We display these logos under nominative-use doctrine (using a brand's
mark to identify a relationship — "we accept Maxi transfers"). To
stay safely within that boundary:

- Display at small sizes (≤ 200 px wide).
- No implication of partnership / endorsement in surrounding UI copy.
- Take down on request — flip the catalog row's Active checkbox to
  No (or delete the seed file + redeploy) if a brand objects.

## Examples

```
static/seed-logos/
├── README.md            ← this file
├── companies/
│   ├── intermex.svg
│   ├── maxi.svg
│   ├── barri.png
│   ├── vigo.svg
│   ├── ria.svg
│   ├── moneygram.png
│   ├── western_union.svg
│   ├── cibao.png
│   └── boss_revolution.png
└── banks/
    ├── mx_bbva_bancomer.svg
    ├── mx_banorte.svg
    ├── mx_santander.svg
    ├── gt_industrial.svg
    ├── gt_banrural.svg
    ├── hn_atlantida.svg
    └── …
```

## Adding a new company / bank that's not in the seed

The seed directory only imports logos for catalog rows that already
exist. To add a brand-new entry:

1. Sign in as superadmin → `/superadmin/controls?tab=tv-catalog`.
2. Use the "Add company" or "Add bank" form at the bottom of the
   matching section. Provide a slug (e.g. `remitly`) and display
   name. Save.
3. Drop `remitly.svg` (or `.png`) into `companies/`.
4. Redeploy / restart. The seed loader picks it up.

Or use the upload button next to the catalog row in the UI; works
the same.
