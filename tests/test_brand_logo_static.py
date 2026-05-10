"""Regression test: brand mark is image-based, not CSS-painted text.

Previously the brand mark was a `<span>$</span>` styled with
`background: var(--db-neon)`. In light mode `--db-neon` flips to
a muted green for accessibility on white surfaces, so the LOGO
flipped along with the rest of the chrome — wrong. The brand
identity should be static.

Fix shipped in May 2026: replace the text-span pattern with an
`<img src="static/brand-mark.svg">`. The SVG file is the single
source of truth for the brand identity and doesn't care about
CSS variables, so the logo can't accidentally re-flip.

These tests pin the contract: the SVG file exists and contains
the brand colors, and every shell + login + signup page references
it via <img> rather than re-painting the brand in CSS.
"""
import os


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_brand_mark_svg_file_exists_and_uses_brand_colors():
    """The single source of truth for the brand mark."""
    path = "static/brand-mark.svg"
    assert os.path.exists(path), f"missing canonical brand asset: {path}"
    src = _read(path)
    # Neon-green tile + near-black "$" — pinned literal hex so a
    # designer can't accidentally drift the brand color via a token.
    assert "#3fff00" in src, "brand mark tile must be the neon green #3fff00"
    assert "#001a0f" in src, "brand mark glyph must be the near-black ink"
    # The "$" glyph is visible.
    assert ">$<" in src or "$" in src


def test_admin_shell_uses_image_brand_mark(logged_in_client):
    """The sidebar in base.html pulls the logo from the SVG file —
    not from a CSS-painted text span. The latter flips under light
    mode because var(--db-neon) is muted there."""
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'class="brand-mark"' in body
    assert "brand-mark.svg" in body, \
        "sidebar must <img> the brand-mark.svg — see PR for context"
    # The text-span pattern must be gone.
    assert '<span class="brand-mark"' not in body, \
        "brand mark must be an <img>, not a CSS-painted <span>$</span>"


def test_owner_shell_uses_image_brand_mark():
    """Same contract on base_owner.html."""
    from app import app as flask_app, db, User, StoreOwnerLink, Store
    with flask_app.app_context():
        s = Store(name="Brand Logo Test", slug="brand-logo-test", plan="trial")
        db.session.add(s); db.session.commit()
        o = User(username="owner-brand-logo@x.com", role="owner",
                 store_id=None, full_name="Brand Logo Owner")
        o.set_password("p"); db.session.add(o); db.session.commit()
        db.session.add(StoreOwnerLink(owner_id=o.id, store_id=s.id))
        db.session.commit()
        oid = o.id
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = c.get("/owner/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "brand-mark.svg" in body
    assert '<span class="brand-mark"' not in body


def test_login_chrome_uses_image_brand_mark():
    """The 2FA login chrome (the big-logo screen on /app/login/2fa*)
    shouldn't paint the mark in CSS either — same SVG file. The
    legacy templates/_login_chrome.html partial moved to
    frontend/src/routes/TwoFactor.tsx (inline `TWO_FACTOR_CSS`)
    when /login/2fa* migrated to React. Same brand-mark contract:
    .brand-mark must be a sized <img> with no background fill."""
    src = _read("frontend/src/routes/TwoFactor.tsx")
    assert "brand-mark.svg" in src
    idx = src.find(".brand-mark {")
    assert idx != -1, ".brand-mark rule missing in TwoFactor.tsx"
    end = src.find("}", idx)
    rule = src[idx:end]
    decl_lines = [
        ln.strip() for ln in rule.splitlines()
        if ln.strip() and not ln.strip().startswith(("/*", "*"))
    ]
    has_bg = any("background:" in ln and "/*" not in ln for ln in decl_lines)
    assert not has_bg, (
        f"login-chrome .brand-mark must not paint a background — "
        f"the brand identity comes from brand-mark.svg. Rule body:\n{rule}"
    )


def test_sidebar_brand_mark_css_is_image_only():
    """Sidebar `.brand-mark` rule should size the image — no
    background / color / font properties (those would be irrelevant
    for an <img> and a sign of a regression to the text pattern)."""
    src = _read("static/shell.css")
    idx = src.find(".sidebar-logo .brand-mark")
    assert idx != -1
    block = src[idx:idx + 500]
    # Background-color shouldn't be on an image-based brand mark.
    # We accept the rule mentioning width/height/border-radius/box-shadow,
    # but `background:` (any non-comment occurrence) is the smell.
    # Simple heuristic: `background:` outside a comment.
    # Lines starting with `*` or beginning a `/*` block are comments;
    # we strip those out before checking.
    decl_lines = [
        ln.strip() for ln in block.splitlines()
        if ln.strip() and not ln.strip().startswith("*")
        and "/*" not in ln and "*/" not in ln
    ]
    background_decls = [ln for ln in decl_lines
                        if ln.startswith("background:")]
    assert not background_decls, (
        f"sidebar .brand-mark must not paint a background — found: "
        f"{background_decls}. Use <img> + the brand-mark.svg file."
    )
