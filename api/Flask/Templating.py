"""Jinja template globals + the country-flag helpers.

Registered onto the Flask app via ``install(app)``. The helpers
are also importable directly (PublicRoutes uses
``country_flag_html`` from this module too).
"""
from __future__ import annotations

import os
import time

from flask import Flask
from markupsafe import Markup


_APP_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "static", "app.css",
)


def _country_flag_emoji(code):
    """ISO-2 → flag emoji. Use country_flag_html() for visual
    rendering — emoji flags show as tofu on Windows."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in code)


def country_flag_html(code, size="1em"):
    """ISO-2 → flag-icons SVG <span>. MIT-licensed; renders
    uniformly across browsers (unlike emoji flags on Windows)."""
    code = (code or "").strip().lower()
    if len(code) != 2 or not code.isalpha():
        return ""
    style = f"width:{size};height:{size};"
    return Markup(
        f'<span class="fi fi-{code}" style="{style}"></span>'
    )


def install(app: Flask) -> str:
    """Register Jinja globals (STATIC_VERSION + flag helpers) on
    `app`. Returns the STATIC_VERSION cache-bust string."""
    try:
        static_version = str(int(os.path.getmtime(_APP_CSS_PATH)))
    except OSError:
        static_version = str(int(time.time()))
    app.jinja_env.globals["STATIC_VERSION"] = static_version
    app.jinja_env.globals["_country_flag_emoji"] = _country_flag_emoji
    app.jinja_env.globals["country_flag_html"] = country_flag_html
    return static_version
