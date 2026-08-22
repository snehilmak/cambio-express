"""Product brand name — the single config point for a rebrand.

"DineroBook" reads MSB-flavored; the pivot (HANDOFF.md §2) makes a
rename plausible. Everything runtime-variable reads the name from
here (backend) or ``frontend/src/lib/brand.ts`` (SPA), so a rebrand
is an env change plus the small static checklist below — not a
codebase-wide hunt.

Static spots a rebrand still touches by hand:
  * ``frontend/index.html`` — <title> + meta/OG tags
  * PWA manifest + icons
  * ``frontend/src/routes/Privacy.tsx`` — legal text (needs legal
    review at rebrand time anyway)
  * plain-text email body constants (grep for the old name)
  * the custom domain + ``APP_BASE_URL`` / ``WEBAUTHN_RP_ID`` env
"""
import os


def get_brand_name() -> str:
    return os.environ.get("BRAND_NAME", "DineroBook")
