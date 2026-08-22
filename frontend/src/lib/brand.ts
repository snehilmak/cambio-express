// Product brand name — the SPA's single config point for a rebrand
// (backend twin: api/Core/Brand.py, which documents the remaining
// static checklist: index.html meta, PWA manifest, Privacy legal
// text, plain-text email bodies).
//
// Override at build time with VITE_BRAND_NAME.
export const BRAND_NAME =
  (import.meta.env.VITE_BRAND_NAME as string | undefined) ?? "DineroBook";
