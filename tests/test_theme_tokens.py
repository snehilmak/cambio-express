"""Regression guard for the semantic theme tokens.

The SPA's kit primitives (``frontend/src/components/ui/tokens.ts``)
read CSS variables called ``--db-surface``, ``--db-text``,
``--db-border``, etc. — the "semantic" layer that flips between
dark and light. If those tokens aren't defined in
``static/design-tokens.css``, every component falls through to
its hardcoded fallback hex (all dark), and the theme toggle
becomes a no-op.

This test pins the contract: the tokens the SPA expects to read
must actually be declared in the design-tokens stylesheet.
"""
from pathlib import Path


TOKENS_CSS = Path(__file__).parent.parent / "static" / "design-tokens.css"

# Tokens consumed by frontend/src/components/ui/tokens.ts. If you
# add a new ``var(--db-...)`` lookup in tokens.ts (or anywhere
# else that should respect the dark / light toggle) add it here.
SEMANTIC_TOKENS = [
    "--db-surface",
    "--db-surface-2",
    "--db-surface-3",
    "--db-text",
    "--db-text-muted",
    "--db-border",
    "--db-border-subtle",
    "--db-accent",
    "--db-on-accent",
]


def test_design_tokens_defines_every_semantic_alias():
    """All tokens the SPA kit reads must be declared in
    design-tokens.css. A missing declaration silently falls through
    to the hardcoded hex fallback, which locks the chrome into
    dark mode regardless of ``data-theme``."""
    css = TOKENS_CSS.read_text(encoding="utf-8")
    missing = [t for t in SEMANTIC_TOKENS if f"{t}:" not in css]
    assert not missing, (
        f"design-tokens.css is missing semantic aliases: {missing}. "
        f"Add ``{missing[0]}: var(--db-bg);`` (or the right backing "
        "token) inside the :root block."
    )
