"""Email-template renderer (standalone Jinja2).

Renders the HTML email templates in ``templates/emails/`` via a
Jinja2 ``Environment`` that has zero dependency on Flask. Used by
the trial-reminder cron, the locked-day digest, the
announcement-broadcast CLI, and any future caller that needs to
mail a templated HTML body.

Why not Flask's ``render_template``: it requires a request context,
which forced cron + webhook callers to fabricate one with
``app.test_request_context("/")``. The standalone env is pure
str-in, str-out — works from any caller, with no Flask boot cost
and no fake request context.
"""
from __future__ import annotations

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "templates"),
)

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_email_template(template_name: str, /, **ctx: object) -> str:
    """Render an email template by path (e.g.
    ``"emails/trial_reminder.html"``). The Jinja2 env is rooted at
    the repo's ``templates/`` directory so the relative
    ``{% extends "emails/_base.html" %}`` declarations in the email
    templates keep working.

    ``template_name`` is positional-only so callers can pass
    ``name=u.full_name`` in ``**ctx`` without a parameter-collision
    TypeError. (Legacy callers do exactly that — the previous
    signature ``(name: str, **ctx)`` was a latent bug.)
    """
    from api.Core.Brand import get_brand_name
    tmpl = _env.get_template(template_name)
    # brand_name is available in EVERY email template (the _base
    # chrome uses it); explicit ctx wins if a caller passes one.
    return tmpl.render(**{"brand_name": get_brand_name(), **ctx})


__all__ = ["render_email_template"]
