"""Jinja helpers used by the public HTML templates.

Lifted out of ``api/Flask/Templating.py`` when Flask was retired
in PR #550. The ``country_flag_html`` helper is the only thing the
public templates (``offline.html``, ``tv_display_public.html``)
need; the rest of the legacy Jinja-globals registration died with
``app.jinja_env``.
"""
from __future__ import annotations

from markupsafe import Markup


def country_flag_html(code, size="1em"):
    """ISO-2 → flag-icons SVG ``<span>``. MIT-licensed CSS sprite;
    renders uniformly across browsers (unlike emoji flags on
    Windows)."""
    code = (code or "").strip().lower()
    if len(code) != 2 or not code.isalpha():
        return ""
    style = f"width:{size};height:{size};"
    return Markup(
        f'<span class="fi fi-{code}" style="{style}"></span>'
    )
