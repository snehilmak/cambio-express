"""Smoke-test that the bilingual "Use your browser to translate" hint
renders on every user-facing page (public + logged-in + owner chrome).

We don't test dismissal behavior (that's localStorage-backed JS); we just
confirm the include is wired into each template family so we don't
silently lose it on future template edits.
"""


def _assert_hint(resp):
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", errors="ignore")
    assert 'id="translate-hint"' in html, "Translate hint missing from page"
    assert "Traducir al español" in html


def test_hint_on_landing(client):
    _assert_hint(client.get("/"))


def test_hint_on_login(client):
    _assert_hint(client.get("/login"))


def test_hint_on_signup(client):
    _assert_hint(client.get("/signup"))


def test_hint_on_privacy(client):
    _assert_hint(client.get("/privacy"))


def test_hint_on_logged_in_dashboard(logged_in_client):
    # Logged-in visits to "/" bounce to the dashboard — follow the redirect
    # so we land on the page that should include the hint.
    _assert_hint(logged_in_client.get("/", follow_redirects=True))
