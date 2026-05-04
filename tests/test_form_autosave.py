"""Smoke tests for the form-draft autosave wiring on /transfers/new.

The actual save/restore behavior lives in `static/draft-autosave.js` and
runs in the browser's localStorage — out of reach from pytest's request
client. These tests pin the server-side wiring: the form gets a
`data-draft-key` attribute on the create route (so the script latches
on), and edit routes do NOT (so a stale local draft can't overwrite
real edits).
"""


def test_new_transfer_form_has_draft_key(logged_in_client):
    resp = logged_in_client.get("/transfers/new")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-draft-key="new-transfer"' in body
    # Script tag is loaded with the cache-buster query string.
    assert "draft-autosave.js" in body


def test_edit_transfer_form_does_not_have_draft_key(logged_in_client):
    """Editing an existing transfer must NOT carry the draft-key
    attribute — restoring a local draft on top of a real edit form
    would silently overwrite legitimate field values."""
    from datetime import date
    from app import app as flask_app, db, Store, User, Transfer
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        user = User.query.filter_by(username="admin@test.com").first()
        t = Transfer(
            store_id=store.id, created_by=user.id,
            send_date=date.today(), company="Intermex",
            sender_name="Edit Test", send_amount=100.0, fee=2.0,
            federal_tax=1.0, commission=0.0, status="Sent",
        )
        db.session.add(t)
        db.session.commit()
        tid = t.id

    resp = logged_in_client.get(f"/transfers/{tid}/edit")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "data-draft-key" not in body
    # Script tag should NOT be loaded on the edit route either, since
    # there's nothing to autosave.
    assert "draft-autosave.js" not in body
