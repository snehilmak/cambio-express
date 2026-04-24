"""Personal `/account/notifications` page + the trial-reminder sender
it toggles.

The page is shipped as the third per-user surface (Profile, Security,
Notifications). v1 controls a single real sender — trial-ending
reminder emails — because that's the only sender beyond password
reset we've built. The rest of the page is an informational catalog.

We cover:
  - Cross-role GET (admin, owner, employee, superadmin).
  - Toggle persists in both directions (checkbox-off means False).
  - `send_trial_reminders()` stamps dedup, is idempotent on re-run,
    respects the user's opt-out, and only targets stores actually
    in expiring_soon.
  - Resubscribe (simulated via direct column clear, same thing the
    Stripe webhook does) re-enables the next reminder.
  - CLI `flask send-trial-reminders` exists and invokes the sender.
  - Topbar dropdown ships the Notifications link in both chromes.
"""
from datetime import datetime, timedelta

from app import db, User, Store, send_trial_reminders


def _client_for(app, user_id, role, store_id):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user_id
        s["role"] = role
        s["store_id"] = store_id
    return c


def _make_user(app, role, store_id, *, username, email="", password="x",
               full_name="X", notify=True):
    with app.app_context():
        u = User(store_id=store_id, username=username, full_name=full_name,
                 role=role, email=email, notify_trial_reminders=notify)
        u.set_password(password)
        db.session.add(u); db.session.commit()
        return u.id


# ── Access + render ────────────────────────────────────────────

def test_anonymous_redirected(client):
    resp = client.get("/account/notifications")
    assert resp.status_code in (302, 401)


def test_admin_page_renders(logged_in_client):
    resp = logged_in_client.get("/account/notifications")
    assert resp.status_code == 200
    body = resp.data.decode()
    for token in ("Your preferences", "Trial-ending reminder",
                  "What DineroBook sends you", "Password reset",
                  "Save preferences"):
        assert token in body, f"missing: {token}"


def test_employee_page_renders_with_toggle_disabled(client, test_store_id):
    """Employees see the same catalog, but the trial toggle is
    non-applicable (they don't own a trial) so it renders `disabled`."""
    emp = _client_for(client.application,
                      _make_user(client.application, "employee", test_store_id,
                                 username="emp-notif@test.com"),
                      "employee", test_store_id)
    resp = emp.get("/account/notifications")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'id="ntr"' in body
    assert "disabled" in body  # toggle is disabled for employees


def test_superadmin_page_renders(client):
    with client.application.app_context():
        sa_id = User.query.filter_by(username="superadmin").first().id
    sa = _client_for(client.application, sa_id, "superadmin", None)
    assert sa.get("/account/notifications").status_code == 200


def test_owner_page_renders(client):
    with client.application.app_context():
        s = Store(name="ON", slug="on-notif", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own = _client_for(client.application,
                      _make_user(client.application, "owner", sid,
                                 username="own-notif@test.com"),
                      "owner", sid)
    assert own.get("/account/notifications").status_code == 200


# ── Preference persistence ─────────────────────────────────────

def test_toggle_off_persists(logged_in_client, test_admin_id):
    # Checkbox absent → field missing from POST body → stored as False.
    resp = logged_in_client.post("/account/notifications", data={},
                                 follow_redirects=True)
    assert resp.status_code == 200
    with logged_in_client.application.app_context():
        assert db.session.get(User, test_admin_id).notify_trial_reminders is False


def test_toggle_on_persists(logged_in_client, test_admin_id):
    # First turn off, then on, to exercise the True path explicitly.
    logged_in_client.post("/account/notifications", data={})
    logged_in_client.post("/account/notifications",
                          data={"notify_trial_reminders": "1"})
    with logged_in_client.application.app_context():
        assert db.session.get(User, test_admin_id).notify_trial_reminders is True


# ── send_trial_reminders sender ────────────────────────────────

def _put_store_in_expiring_soon(app, store_id):
    """Force the fixture store into the expiring_soon window."""
    with app.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "trial"
        s.trial_ends_at = datetime.utcnow() + timedelta(days=2)
        s.trial_reminder_sent_at = None
        db.session.commit()


def test_sender_stamps_dedup_on_success(logged_in_client, test_admin_id, test_store_id):
    app = logged_in_client.application
    _put_store_in_expiring_soon(app, test_store_id)
    # Ensure the admin has an email + the toggle on.
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        u.notify_trial_reminders = True
        db.session.commit()
    with app.app_context():
        n = send_trial_reminders()
    assert n == 1, f"expected 1 send, got {n}"
    with app.app_context():
        assert db.session.get(Store, test_store_id).trial_reminder_sent_at is not None


def test_sender_is_idempotent_on_rerun(logged_in_client, test_admin_id, test_store_id):
    app = logged_in_client.application
    _put_store_in_expiring_soon(app, test_store_id)
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        u.notify_trial_reminders = True
        db.session.commit()
    with app.app_context():
        send_trial_reminders()
        first = db.session.get(Store, test_store_id).trial_reminder_sent_at
        assert first is not None
        # Run again the same day — must be a no-op, stamp unchanged.
        n2 = send_trial_reminders()
        assert n2 == 0
        assert db.session.get(Store, test_store_id).trial_reminder_sent_at == first


def test_sender_respects_user_opt_out(logged_in_client, test_admin_id, test_store_id):
    """User with notify_trial_reminders=False isn't included in the
    recipient list. If they're the only admin, sender sends 0 and
    leaves the dedup stamp NULL so a later opt-in still gets served."""
    app = logged_in_client.application
    _put_store_in_expiring_soon(app, test_store_id)
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        u.notify_trial_reminders = False  # OPTED OUT
        db.session.commit()
    with app.app_context():
        n = send_trial_reminders()
    assert n == 0
    with app.app_context():
        # Still NULL — otherwise the user would never get a reminder
        # if they later flip the toggle back on.
        assert db.session.get(Store, test_store_id).trial_reminder_sent_at is None


def test_sender_skips_non_expiring_soon_stores(logged_in_client, test_admin_id, test_store_id):
    """Store with 10 days left on trial → "active" → skipped."""
    app = logged_in_client.application
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"
        s.trial_ends_at = datetime.utcnow() + timedelta(days=10)  # "active"
        s.trial_reminder_sent_at = None
        db.session.commit()
        n = send_trial_reminders()
    assert n == 0


def test_sender_skips_paid_stores(logged_in_client, test_admin_id, test_store_id):
    app = logged_in_client.application
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        s = db.session.get(Store, test_store_id)
        s.plan = "basic"  # paid — exempt
        db.session.commit()
        n = send_trial_reminders()
    assert n == 0


def test_sender_skips_users_with_no_email(logged_in_client, test_admin_id, test_store_id):
    """notify_trial_reminders=True but email="" — can't send."""
    app = logged_in_client.application
    _put_store_in_expiring_soon(app, test_store_id)
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = ""  # blank
        u.notify_trial_reminders = True
        db.session.commit()
        n = send_trial_reminders()
    assert n == 0


def test_resubscribe_clears_dedup(logged_in_client, test_admin_id, test_store_id):
    """After the Stripe checkout webhook fires (clearing the dedup
    stamp on re-subscribe), a subsequent trial re-entry gets a fresh
    reminder. We simulate the webhook's side effect directly."""
    app = logged_in_client.application
    _put_store_in_expiring_soon(app, test_store_id)
    with app.app_context():
        u = db.session.get(User, test_admin_id)
        u.email = "admin@test.com"
        u.notify_trial_reminders = True
        db.session.commit()
        send_trial_reminders()
        s = db.session.get(Store, test_store_id)
        assert s.trial_reminder_sent_at is not None
        # Webhook clears it on resubscribe:
        s.trial_reminder_sent_at = None
        db.session.commit()
        # New trial later — sender fires again.
        n = send_trial_reminders()
    assert n == 1


# ── CLI wiring ─────────────────────────────────────────────────

def test_cli_send_trial_reminders_runs(logged_in_client):
    """The Click command exists and invokes the sender. We don't care
    about its stdout beyond "it ran without raising." """
    runner = logged_in_client.application.test_cli_runner()
    result = runner.invoke(args=["send-trial-reminders"])
    assert result.exit_code == 0, result.output
    assert "trial reminder" in result.output.lower()


# ── Topbar dropdown wiring ─────────────────────────────────────

def test_topbar_dropdown_links_notifications_admin_chrome(logged_in_client):
    body = logged_in_client.get("/admin/settings?tab=store").data.decode()
    assert "/account/notifications" in body


def test_topbar_dropdown_links_notifications_owner_chrome(client):
    with client.application.app_context():
        s = Store(name="ON2", slug="on-notif-2", plan="basic")
        db.session.add(s); db.session.flush()
        sid = s.id
    own = _client_for(client.application,
                      _make_user(client.application, "owner", sid,
                                 username="own-notif-2@test.com"),
                      "owner", sid)
    body = own.get("/owner/dashboard").data.decode()
    assert "/account/notifications" in body
