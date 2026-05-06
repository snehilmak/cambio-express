"""Regression test: subscribe.html has no inline `style="..."` attrs.

The page used to be a wall of duplicated inline styles (34 occurrences
across the two pricing cards). The May 2026 cleanup moved everything
into a page-scoped `<style>` block with a `.pricing-*` class set so
the design tokens flow correctly in light + dark mode. This test
prevents the inline pattern from creeping back in.

Same contract proposed for the other 67 templates that still carry
inline styles — see BACKLOG entry "Inline-CSS audit". Each one ships
its own narrowly-scoped no-inline test as it gets cleaned up.
"""
import re


def test_subscribe_html_has_no_inline_style_attributes():
    with open("templates/subscribe.html", encoding="utf-8") as f:
        src = f.read()
    # Match `style="..."` on element attributes (not inside the <style>
    # block — those are intentional). The negative lookbehind guards
    # against false positives if a CSS selector ever matches the
    # pattern in a comment.
    inline = re.findall(r'<[^>]+\sstyle="[^"]*"', src)
    assert not inline, (
        f"subscribe.html must not use inline style attributes. Found "
        f"{len(inline)} occurrence(s):\n" + "\n".join(inline[:5])
    )


def test_subscribe_html_uses_design_tokens_not_legacy_colors():
    """The cleanup also dropped legacy `--gray4 / --navy / --gold /
    --blue` references in favor of `--db-*` tokens. If those legacy
    names sneak back in, they'll bypass dark/light flipping and we'll
    get the same kind of bug PR #203 fixed for the brand mark."""
    with open("templates/subscribe.html", encoding="utf-8") as f:
        src = f.read()
    for legacy in ("var(--gray4)", "var(--navy)", "var(--gold)", "var(--gold2)"):
        assert legacy not in src, (
            f"subscribe.html still uses legacy token {legacy!r} — "
            f"replace with the equivalent --db-* token"
        )


def test_subscribe_page_renders_for_authenticated_user(logged_in_client):
    """End-to-end: the refactored page still serves a 200 with the
    pricing cards and CTAs intact."""
    resp = logged_in_client.get("/subscribe")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Class names from the new pricing component.
    assert 'class="pricing-grid"' in body
    assert 'class="pricing-card"' in body
    assert "pricing-card--accent" in body  # Pro tier
    # Both monthly buttons present.
    assert "$35 / mo" in body
    assert "$45 / mo" in body
