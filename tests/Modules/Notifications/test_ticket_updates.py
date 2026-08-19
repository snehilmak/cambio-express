"""Ticket-update notifications — worker Services + controller hooks.

Worker level (``Notifications.Services.ticket_updates``):
  - staff acted → email + push to the ticket's creator, each channel
    gated on its own preference toggle
  - store side acted → email to active superadmins (platform side)

Controller level (``Support.Controllers``): every ticket mutation
enqueues the right worker with primitive args (invariant #16) —
asserted by recording ``api.Core.Jobs.enqueue`` calls.

Plus the notifications-prefs roundtrip for the two new toggles.
"""
import pytest

from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


@pytest.fixture
def sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


@pytest.fixture
def admin_headers(client):
    with db_session():
        from api.Modules.Tenancy.Models import Store
        store_id = db.session.query(Store).first().id
    return {"Authorization": f"Bearer {login_admin(client, store_id)}"}


def _make_ticket(client, headers, subject="Notify test"):
    resp = client.post("/api/v2/tickets", headers=headers, json={
        "category": "question", "subject": subject, "body": "Help please.",
    })
    assert resp.status_code == 201
    return resp.json()["ticket"]["id"]


def _set_creator_prefs(ticket_id, **fields):
    """Give the ticket's creator a deliverable email + any pref
    overrides. Returns the creator's email address."""
    with db_session():
        from api.Modules.Support.Models import SupportTicket
        from api.Modules.Tenancy.Models import User
        t = db.session.get(SupportTicket, ticket_id)
        u = db.session.get(User, t.user_id)
        if not u.email:
            u.email = f"creator{u.id}@example.com"
        for k, v in fields.items():
            setattr(u, k, v)
        db.session.commit()
        return u.email


@pytest.fixture
def outbox(monkeypatch):
    """Capture send_email + send_push calls from the workers."""
    emails: list[tuple[str, str]] = []
    pushes: list[tuple[int, str]] = []
    from api.Modules.Notifications.Services import push as push_mod
    from api.Modules.Notifications.Services import smtp as smtp_mod
    monkeypatch.setattr(
        smtp_mod, "send_email",
        lambda db_, to, subject, body, html=None: emails.append(
            (to, subject),
        ) or True,
    )
    monkeypatch.setattr(
        push_mod, "send_push",
        lambda db_, user_id, title, body="", url="/", tag=None: pushes.append(
            (user_id, title),
        ) or 1,
    )
    return {"emails": emails, "pushes": pushes}


class TestUserWorker:
    def test_staff_reply_sends_email_and_push(
        self, client, admin_headers, outbox,
    ):
        tid = _make_ticket(client, admin_headers)
        email = _set_creator_prefs(tid)
        from api.Modules.Notifications.Services.ticket_updates import (
            send_ticket_update_to_user,
        )
        sent = send_ticket_update_to_user(tid, "staff_reply", "We are on it.")
        assert sent == 1
        assert outbox["emails"] == [
            (email, "Update on your support ticket: Notify test"),
        ]
        assert len(outbox["pushes"]) == 1

    def test_email_optout_still_pushes(self, client, admin_headers, outbox):
        tid = _make_ticket(client, admin_headers)
        _set_creator_prefs(tid, notify_ticket_updates=False)
        from api.Modules.Notifications.Services.ticket_updates import (
            send_ticket_update_to_user,
        )
        sent = send_ticket_update_to_user(tid, "staff_reply", "hi")
        assert sent == 0
        assert outbox["emails"] == []
        assert len(outbox["pushes"]) == 1

    def test_push_optout_still_emails(self, client, admin_headers, outbox):
        tid = _make_ticket(client, admin_headers)
        _set_creator_prefs(tid, notify_ticket_updates_push=False)
        from api.Modules.Notifications.Services.ticket_updates import (
            send_ticket_update_to_user,
        )
        sent = send_ticket_update_to_user(tid, "status_change", "In progress")
        assert sent == 1
        assert outbox["pushes"] == []

    def test_inactive_creator_gets_nothing(
        self, client, admin_headers, outbox,
    ):
        tid = _make_ticket(client, admin_headers)
        _set_creator_prefs(tid, is_active=False)
        from api.Modules.Notifications.Services.ticket_updates import (
            send_ticket_update_to_user,
        )
        assert send_ticket_update_to_user(tid, "staff_reply", "x") == 0
        assert outbox["emails"] == []
        assert outbox["pushes"] == []


class TestPlatformWorker:
    def _superadmin_email(self, **fields):
        with db_session():
            from api.Modules.Tenancy.Models import User
            sa = db.session.query(User).filter_by(role="superadmin").first()
            if not sa.email:
                sa.email = "platform@example.com"
            for k, v in fields.items():
                setattr(sa, k, v)
            db.session.commit()
            return sa.email

    def test_created_event_emails_superadmin(
        self, client, admin_headers, outbox,
    ):
        tid = _make_ticket(client, admin_headers)
        email = self._superadmin_email(notify_ticket_updates=True)
        from api.Modules.Notifications.Services.ticket_updates import (
            send_ticket_event_to_platform,
        )
        sent = send_ticket_event_to_platform(
            tid, "created", "Help please.", "Store Admin",
        )
        assert sent == 1
        to, subject = outbox["emails"][0]
        assert to == email
        assert f"Ticket #{tid}" in subject
        assert "New ticket" in subject
        assert outbox["pushes"] == []  # platform side is email-only

    def test_opted_out_superadmin_skipped(
        self, client, admin_headers, outbox,
    ):
        tid = _make_ticket(client, admin_headers)
        self._superadmin_email(notify_ticket_updates=False)
        from api.Modules.Notifications.Services.ticket_updates import (
            send_ticket_event_to_platform,
        )
        assert send_ticket_event_to_platform(tid, "user_reply", "x") == 0
        assert outbox["emails"] == []


@pytest.fixture
def enqueued(monkeypatch):
    """Record every notification the Support controllers enqueue,
    without running the workers."""
    calls: list[tuple[str, tuple]] = []
    import api.Core.Jobs as jobs
    monkeypatch.setattr(
        jobs, "enqueue",
        lambda fn, *args, **kwargs: calls.append((fn.__name__, args)),
    )
    return calls


class TestControllerHooks:
    def test_create_ticket_notifies_platform(
        self, client, admin_headers, enqueued,
    ):
        tid = _make_ticket(client, admin_headers)
        assert len(enqueued) == 1
        name, args = enqueued[0]
        assert name == "send_ticket_event_to_platform"
        assert (args[0], args[1], args[2]) == (tid, "created", "Help please.")

    def test_staff_reply_notifies_user(
        self, client, admin_headers, sa_headers, enqueued,
    ):
        tid = _make_ticket(client, admin_headers)
        enqueued.clear()
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=sa_headers,
            json={"body": "We are on it."},
        )
        assert enqueued == [
            ("send_ticket_update_to_user", (tid, "staff_reply", "We are on it.")),
        ]

    def test_user_reply_notifies_platform(
        self, client, admin_headers, enqueued,
    ):
        tid = _make_ticket(client, admin_headers)
        enqueued.clear()
        client.post(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
            json={"body": "More detail."},
        )
        assert len(enqueued) == 1
        name, args = enqueued[0]
        assert name == "send_ticket_event_to_platform"
        assert (args[0], args[1], args[2]) == (tid, "user_reply", "More detail.")

    def test_reopen_by_user_notifies_platform(
        self, client, admin_headers, sa_headers, enqueued,
    ):
        tid = _make_ticket(client, admin_headers)
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "closed"},
        )
        enqueued.clear()
        client.post(f"/api/v2/tickets/{tid}/reopen", headers=admin_headers)
        assert len(enqueued) == 1
        name, args = enqueued[0]
        assert name == "send_ticket_event_to_platform"
        assert (args[0], args[1]) == (tid, "reopened")

    def test_status_change_by_staff_notifies_user(
        self, client, admin_headers, sa_headers, enqueued,
    ):
        tid = _make_ticket(client, admin_headers)
        enqueued.clear()
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "in_progress"},
        )
        assert enqueued == [
            ("send_ticket_update_to_user", (tid, "status_change", "In progress")),
        ]

    def test_legacy_put_reply_notifies_user_once(
        self, client, admin_headers, sa_headers, enqueued,
    ):
        """A PUT carrying both a reply and a status change sends ONE
        notification — the reply (which shows current status anyway)."""
        tid = _make_ticket(client, admin_headers)
        enqueued.clear()
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"status": "resolved", "admin_reply": "Fixed it."},
        )
        assert enqueued == [
            ("send_ticket_update_to_user", (tid, "staff_reply", "Fixed it.")),
        ]

    def test_noop_put_sends_nothing(
        self, client, admin_headers, sa_headers, enqueued,
    ):
        tid = _make_ticket(client, admin_headers)
        enqueued.clear()
        client.put(
            f"/api/v2/tickets/{tid}", headers=sa_headers,
            json={"priority": "high"},
        )
        assert enqueued == []


class TestPrefsRoundtrip:
    def test_toggle_roundtrip(self, client, admin_headers):
        r = client.get("/api/v2/auth/notifications", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["notify_ticket_updates"] is True
        assert r.json()["notify_ticket_updates_push"] is True
        assert r.json()["ticket_updates_applies"] is True
        r = client.put(
            "/api/v2/auth/notifications", headers=admin_headers,
            json={
                "notify_ticket_updates": False,
                "notify_ticket_updates_push": False,
            },
        )
        assert r.status_code == 200
        assert r.json()["notify_ticket_updates"] is False
        assert r.json()["notify_ticket_updates_push"] is False
        r = client.get("/api/v2/auth/notifications", headers=admin_headers)
        assert r.json()["notify_ticket_updates"] is False
        assert r.json()["notify_ticket_updates_push"] is False
