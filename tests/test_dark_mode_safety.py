"""Regression guard against dark-mode invisibility bugs.

The design system declares two buckets of color tokens:

  Fixed tokens    — --navy, --blue, --mid, --gold, --gold2, --white,
                    --gray1, --gray2, --gray3, --gray4, --dark, --cream,
                    --paper. These stay the SAME value in both light and
                    dark mode. Useful for brand-colored heroes, gold
                    accents, permanently-dark buttons, etc.

  Semantic tokens — --surface, --surface-2, --text, --text-muted,
                    --border, --border-strong. These FLIP between light
                    and dark mode. Everything that belongs to the app
                    chrome (card bodies, field labels, section text,
                    borders inside cards, etc.) must use semantic tokens
                    — otherwise the element becomes invisible in dark
                    mode (dark text on a dark card, white background on
                    a dark page, etc.).

This test scans every template that extends the app chrome
(base.html / base_owner.html) and fails if an inline style attribute
uses a fixed token for `color`, `background`, or `border*` — which is
the exact mistake we keep regressing on. CSS classes defined in
app.css are not scanned; they're the correct place to put brand-
intentional fixed colors (.plan-hero, .ref-hero, .btn-on-dark, etc.)
which can attach explicit [data-theme="dark"] overrides.

If you really do want a fixed token inline (rare), move the styling
into a named CSS class in static/app.css so this test doesn't see it.
"""
import re
from pathlib import Path
import pytest


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# The "invisible text" tokens — any inline `color: var(--dark)` /
# `color: var(--navy)` puts very-dark text on a very-dark card in dark
# mode, which is the exact bug the user keeps catching. These two are
# always the wrong choice inline; use var(--text) instead.
#
# Other fixed tokens (--gray4 for muted labels, --sky/--blue/--gold for
# accents, --white / --gray1 backgrounds on brand heroes) are dimmer
# contrast in dark mode but not invisible, and some of them are
# intentional brand surfaces. We do NOT flag those here; if they turn
# out to be a problem we widen the blocklist or move those surfaces
# into named CSS classes with dark-mode overrides.
_BANNED_COLOR_TOKENS = ("--dark", "--navy")

# style="…" attribute matcher. Non-greedy to avoid eating across tags.
_STYLE_RE = re.compile(r'''style=["'](.*?)["']''', re.DOTALL)
# Rough `prop: value` splitter inside a style string.
_DECL_RE = re.compile(r"\s*([a-z-]+)\s*:\s*([^;]+)")


def _extends_app_chrome(html: str) -> bool:
    """True when the template extends base.html or base_owner.html — those
    are the only templates that inherit the sidebar + topbar + theme
    toggle and therefore must be dark-mode-safe. Logged-out auth pages,
    the public landing, and the error page are exempt.

    Also matches the conditional-extends pattern that account_* and
    error.html now use to pick the right shell per role
    (`{% extends "base_owner.html" if user.role == "owner" else "base.html" %}`).
    """
    if "{% extends" not in html:
        return False
    return (
        '"base.html"' in html
        or "'base.html'" in html
        or '"base_owner.html"' in html
        or "'base_owner.html'" in html
    )


def _violations(html: str):
    """Yield (property, value, token) tuples for every inline `color: …`
    declaration using one of the invisible-on-dark tokens."""
    for style in _STYLE_RE.findall(html):
        for prop, value in _DECL_RE.findall(style):
            if prop != "color":
                continue
            for tok in _BANNED_COLOR_TOKENS:
                if tok in value:
                    yield prop, value.strip(), tok


@pytest.mark.parametrize("template",
    sorted(p for p in TEMPLATES_DIR.glob("*.html")),
    ids=lambda p: p.name,
)
def test_no_invisible_color_tokens_inline(template):
    """Templates extending the app chrome must not use `color: var(--dark)`
    or `color: var(--navy)` in inline styles — both render as very dark
    text on the dark-mode card surface and effectively disappear.

    If this test fails on a template you just edited:
        - Replace `color: var(--dark)` with `color: var(--text)`.
        - Replace `color: var(--navy)` with `color: var(--text)`.
        - If the element genuinely must stay dark-blue in both modes
          (e.g. a navy brand hero with gold content), move the style
          into a named class in app.css so it's documented intentional
          brand, not accidental drift.
    """
    html = template.read_text(encoding="utf-8")
    if not _extends_app_chrome(html):
        pytest.skip("template does not extend base.html / base_owner.html")
    violations = list(_violations(html))
    assert not violations, (
        f"{template.name} has inline `color:` declarations using "
        f"dark-mode-invisible tokens. Use var(--text) instead. "
        f"Violations: "
        + ", ".join(f"{prop}: {val} ({tok})" for prop, val, tok in violations)
    )
