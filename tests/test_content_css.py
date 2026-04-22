"""Guard that the new content.css (dark+neon overrides for legacy
content-area classes) is linked on authenticated app pages so every
card/table/stat/badge picks up the new styling without per-template
edits."""


def test_admin_dashboard_loads_content_css(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    assert b"content.css" in resp.data


def test_admin_dashboard_loads_design_tokens(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert b"design-tokens.css" in resp.data


def test_transfers_page_loads_content_css(logged_in_client):
    resp = logged_in_client.get("/transfers")
    assert resp.status_code == 200
    assert b"content.css" in resp.data


def test_shell_still_loaded_after_content(logged_in_client):
    """shell.css must load AFTER content.css so sidebar/topbar wins."""
    resp = logged_in_client.get("/dashboard")
    body = resp.data.decode()
    # Find the <link href="...content.css..."> and <link href="...shell.css...">
    # tags (not mere textual mentions in comments).
    i_content = body.find("filename='content.css'")
    i_shell = body.find("filename='shell.css'")
    # Fall back to generic match since Jinja rendering swaps to double quotes
    # depending on Flask version.
    if i_content < 0:
        i_content = body.find("static/content.css")
    if i_shell < 0:
        i_shell = body.find("static/shell.css")
    assert i_content > 0 and i_shell > 0, "one of the stylesheets is missing"
    assert i_content < i_shell, (
        "content.css must be linked before shell.css so shell overrides win "
        f"(content at {i_content}, shell at {i_shell})"
    )
