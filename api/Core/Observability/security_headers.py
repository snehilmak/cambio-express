"""Security headers middleware.

Adds defense-in-depth HTTP headers to every response:

- Content-Security-Policy: restricts what the browser will execute
  (scripts, styles, images, fonts, iframes, connections). Stops
  XSS at the browser level even if a vulnerability slips through.
- X-Content-Type-Options: blocks MIME-sniffing attacks
- X-Frame-Options: blocks clickjacking via iframe embed
- Referrer-Policy: don't leak referrer URLs to third parties
- Permissions-Policy: opt out of browser APIs we don't use

CSP allowlist accommodates:
- Self-hosted SPA bundle + CSS
- Google Fonts (fonts.googleapis.com + fonts.gstatic.com)
- Stripe Checkout iframe (js.stripe.com + checkout.stripe.com)
- Inline styles (Vite injects some) and inline scripts (theme
  restore in index.html) — both with 'unsafe-inline' until we
  switch to nonce-based CSP
"""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://js.stripe.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: blob: https:",
    "connect-src 'self' https://api.stripe.com https://*.sentry.io",
    "frame-src 'self' https://js.stripe.com https://checkout.stripe.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", _CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(self), payment=(self)",
        )
        return response
