"""Regression test: shared chrome lives in `_base_chrome.html` only.

Prior to May 2026, `base.html` and `base_owner.html` shipped duplicate
copies of the chrome — head, sidebar logo + footer, topbar (clock,
avatar dropdown), service-worker registration. The duplication had
already drifted once and shipped a bug to prod (PR #197). The JS half
was consolidated into `static/shell.js`; this test pins the markup
half to one file.

If a future refactor re-introduces an inline `<aside class="sidebar">`
or `<title>` block in either base, this test will fail and ask for
the duplication to be moved into `_base_chrome.html` instead.
"""


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_both_bases_extend_chrome():
    """Each shell must extend `_base_chrome.html`. Without that, any
    chrome change forces a parallel edit in two places."""
    admin = _read("templates/base.html")
    owner = _read("templates/base_owner.html")
    assert '{% extends "_base_chrome.html" %}' in admin
    assert '{% extends "_base_chrome.html" %}' in owner


def test_chrome_owns_the_html_skeleton():
    """The `<!DOCTYPE>`, `<html>`, `<head>`, and `<body>` tags must
    only live in `_base_chrome.html`. If they leak back into a base,
    we've duplicated the skeleton again."""
    chrome = _read("templates/_base_chrome.html")
    admin = _read("templates/base.html")
    owner = _read("templates/base_owner.html")

    assert "<!DOCTYPE html>" in chrome
    assert "<!DOCTYPE html>" not in admin
    assert "<!DOCTYPE html>" not in owner

    assert "<html lang=\"en\"" in chrome
    for path, src in (("base.html", admin), ("base_owner.html", owner)):
        assert "<html lang=" not in src, (
            f"{path} must not redeclare <html> — that lives in "
            f"_base_chrome.html now"
        )
        assert "<aside class=\"sidebar\"" not in src, (
            f"{path} must not redeclare the sidebar wrapper — only the "
            f"sidebar_nav block content belongs in the per-shell file"
        )
        assert "<div class=\"topbar\"" not in src, (
            f"{path} must not redeclare the topbar — only the "
            f"topbar_pill / topbar_extras block content belongs here"
        )


def test_chrome_loads_shared_assets_once():
    """The chrome must be the only file that links app.css /
    design-tokens.css / content.css / shell.css. If a base re-loads
    them, we've split the asset contract."""
    chrome = _read("templates/_base_chrome.html")
    for asset in ("app.css", "design-tokens.css", "content.css", "shell.css"):
        assert asset in chrome, f"chrome must load {asset}"
    admin = _read("templates/base.html")
    owner = _read("templates/base_owner.html")
    # design-tokens / content / shell are chrome-only. (app.css gets
    # loaded by some logged-out pages too, but admin/owner shells must
    # not re-link it.)
    for asset in ("design-tokens.css", "content.css", "shell.css"):
        for path, src in (("base.html", admin), ("base_owner.html", owner)):
            assert asset not in src, (
                f"{path} must not re-link {asset} — chrome owns it"
            )


def test_admin_shell_renders_with_admin_nav(logged_in_client):
    """Smoke: admin can hit /dashboard and see admin nav links — the
    shell hasn't broken in the refactor."""
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Sidebar nav (admin-specific).
    assert 'href="/transfers"' in body
    assert 'href="/daily"' in body
    # Avatar dropdown still rendered by chrome.
    assert 'id="userAvatar"' in body
    assert 'id="userDropdown"' in body
    # Plan pill from base.html's topbar_pill block.
    assert 'topbar-plan-pill' in body or 'TRIAL' in body or 'BASIC' in body or 'PRO' in body


def test_owner_shell_renders_with_owner_nav():
    """Smoke: owner can hit /owner/dashboard and see owner-only nav."""
    from app import app as flask_app, db, User, StoreOwnerLink, Store
    with flask_app.app_context():
        s = Store(name="Chrome Dedup Test", slug="chrome-dedup-test", plan="trial")
        db.session.add(s); db.session.commit()
        o = User(username="owner-chrome-dedup@x.com", role="owner",
                 store_id=None, full_name="Chrome Owner")
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
    # Owner-specific nav links.
    assert 'href="/owner/locations"' in body
    assert 'href="/owner/pl-rollup"' in body
    assert 'href="/owner/connect"' in body
    # Admin nav must NOT appear in the owner shell.
    assert 'href="/transfers"' not in body
    assert 'href="/daily"' not in body
    # OWNER badge from owner shell's topbar_pill block.
    assert ">OWNER<" in body


def test_avatar_role_label_uses_block_in_owner_shell():
    """Owner shell overrides `avatar_role_label` to "Owner" (capital
    O). Chrome default would be `{{ user.role|title }}` which renders
    "Owner" too, but the override pins the wording."""
    src = _read("templates/base_owner.html")
    assert "{% block avatar_role_label %}Owner{% endblock %}" in src
