"""Regression guard for design-system token references.

Every ``var(--db-...)`` lookup in the SPA frontend must resolve
to a token actually declared in ``static/design-tokens.css``. A
missing declaration silently falls through to the hardcoded hex
fallback — which is always dark — and the theme toggle becomes a
no-op (which is the exact bug we hit in PR #589).

This test scans the frontend bundle for every ``var(--db-…)``
reference and fails if any of them isn't declared in
``design-tokens.css``. Catches typos like ``--db-surface-1`` vs
``--db-surface`` before they ship.
"""
import re
from pathlib import Path


REPO_ROOT       = Path(__file__).parent.parent
TOKENS_CSS_PATH = REPO_ROOT / "static" / "design-tokens.css"
FRONTEND_SRC    = REPO_ROOT / "frontend" / "src"

# ``var(--db-foo)`` references in any frontend source file.
_USE_RE = re.compile(r"var\((--db-[a-z0-9-]+)")
# ``--db-foo:`` declarations on the left-hand side of a CSS line.
_DEF_RE = re.compile(r"(--db-[a-z0-9-]+)\s*:")

# File extensions the SPA can stash a CSS-var reference in.
_SCAN_EXTS = (".tsx", ".ts", ".css")


def _declared_tokens() -> set[str]:
    css = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    return set(_DEF_RE.findall(css))


def _referenced_tokens() -> dict[str, list[Path]]:
    """Return ``{token: [files that reference it]}`` so a failure
    message can point the reader at the offending call sites."""
    refs: dict[str, list[Path]] = {}
    for ext in _SCAN_EXTS:
        for path in FRONTEND_SRC.rglob(f"*{ext}"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for token in _USE_RE.findall(text):
                refs.setdefault(token, []).append(path)
    return refs


def test_every_frontend_token_reference_is_declared():
    declared = _declared_tokens()
    referenced = _referenced_tokens()
    missing = {
        tok: paths for tok, paths in referenced.items()
        if tok not in declared
    }
    if missing:
        lines = ["Frontend references undefined design tokens:"]
        for tok, paths in sorted(missing.items()):
            rel = sorted({p.relative_to(REPO_ROOT) for p in paths})
            lines.append(f"  {tok}  — used in: {', '.join(str(p) for p in rel)}")
        lines.append(
            "Either declare the token in static/design-tokens.css "
            "(inside :root) or change the call site to a token that "
            "exists. Undefined tokens fall through to their hardcoded "
            "hex fallback — that breaks the dark/light toggle."
        )
        raise AssertionError("\n".join(lines))
