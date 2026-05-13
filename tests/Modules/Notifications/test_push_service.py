"""Unit tests for Notifications.Services.push (PR 67).

The Service reads VAPID env vars at import time. To test the
configured / not-configured paths we monkeypatch the module-level
constants directly (env-var monkeypatching alone wouldn't take
effect — the read already happened).
"""
from unittest.mock import MagicMock, patch

import pytest


# ── is_enabled ─────────────────────────────────────────────


def test_is_enabled_false_when_keys_missing(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "")
    assert push_svc.is_enabled() is False


def test_is_enabled_false_when_only_public_key_set(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj...")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "")
    assert push_svc.is_enabled() is False


def test_is_enabled_true_when_both_keys_set(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj...")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd...")
    assert push_svc.is_enabled() is True


# ── vapid_public_key ───────────────────────────────────────


def test_vapid_public_key_returns_module_constant(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj_test_pubkey")
    assert push_svc.vapid_public_key() == "BHj_test_pubkey"


def test_vapid_public_key_empty_when_unset(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "")
    assert push_svc.vapid_public_key() == ""


# ── send_push ──────────────────────────────────────────────


def test_send_push_returns_zero_when_disabled(monkeypatch):
    """No keys configured → no-op + return 0."""
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "")
    db = MagicMock()
    assert push_svc.send_push(db, 42, "title") == 0
    # No DB query attempts.
    assert db.query.call_count == 0


def test_send_push_zero_when_no_subscriptions(monkeypatch):
    """User has no subscriptions → no webpush calls + return 0."""
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd")
    from api.Modules.Announcements.Models import PushSubscription
    from app import app as flask_app, db
    with flask_app.app_context():
        PushSubscription.query.delete()
        db.session.commit()
        # Stub pywebpush so the test doesn't need it installed.
        with patch("pywebpush.webpush") as wp:
            assert push_svc.send_push(db.session, 99999, "hi") == 0
            wp.assert_not_called()


def test_send_push_delivers_to_each_subscription(monkeypatch):
    """Two subscriptions → webpush called twice + sent=2."""
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd")
    from api.Modules.Announcements.Models import PushSubscription
    from api.Modules.Tenancy.Models import User
    from app import app as flask_app, db
    with flask_app.app_context():
        PushSubscription.query.delete()
        db.session.commit()
        u = User(
            username="push-target@test.com", password_hash="x",
            role="admin", full_name="x",
            email="push-target@test.com", store_id=1,
        )
        db.session.add(u); db.session.flush()
        for i in (1, 2):
            db.session.add(PushSubscription(
                user_id=u.id,
                endpoint=f"https://push.example.com/{i}",
                p256dh=f"p256-{i}", auth=f"auth-{i}",
            ))
        db.session.commit()
        with patch("pywebpush.webpush") as wp:
            wp.return_value = None
            sent = push_svc.send_push(db.session, u.id, "hi", body="hello")
            assert sent == 2
            assert wp.call_count == 2


def test_send_push_drops_dead_subscriptions(monkeypatch):
    """webpush raising 404 / 410 → subscription deleted from DB."""
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd")
    from api.Modules.Announcements.Models import PushSubscription
    from api.Modules.Tenancy.Models import User
    from app import app as flask_app, db
    from pywebpush import WebPushException
    with flask_app.app_context():
        PushSubscription.query.delete()
        db.session.commit()
        u = User(
            username="dead-sub@test.com", password_hash="x",
            role="admin", full_name="x",
            email="dead-sub@test.com", store_id=1,
        )
        db.session.add(u); db.session.flush()
        sub = PushSubscription(
            user_id=u.id,
            endpoint="https://push.example.com/dead",
            p256dh="p", auth="a",
        )
        db.session.add(sub); db.session.commit()

        # Build a 410-Gone exception object.
        response = MagicMock()
        response.status_code = 410
        exc = WebPushException("subscription gone")
        exc.response = response

        with patch("pywebpush.webpush", side_effect=exc):
            sent = push_svc.send_push(db.session, u.id, "hi")
            assert sent == 0
        # Subscription deleted.
        remaining = PushSubscription.query.filter_by(
            user_id=u.id,
        ).count()
        assert remaining == 0


def test_send_push_keeps_subscriptions_on_other_errors(monkeypatch):
    """Non-(404/410) WebPushException → subscription kept, logged."""
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd")
    from api.Modules.Announcements.Models import PushSubscription
    from api.Modules.Tenancy.Models import User
    from app import app as flask_app, db
    from pywebpush import WebPushException
    with flask_app.app_context():
        PushSubscription.query.delete()
        db.session.commit()
        u = User(
            username="alive-sub@test.com", password_hash="x",
            role="admin", full_name="x",
            email="alive-sub@test.com", store_id=1,
        )
        db.session.add(u); db.session.flush()
        db.session.add(PushSubscription(
            user_id=u.id,
            endpoint="https://push.example.com/alive",
            p256dh="p", auth="a",
        ))
        db.session.commit()

        response = MagicMock()
        response.status_code = 500
        exc = WebPushException("upstream error")
        exc.response = response

        with patch("pywebpush.webpush", side_effect=exc):
            sent = push_svc.send_push(db.session, u.id, "hi")
            assert sent == 0
        # Subscription kept (not deleted).
        remaining = PushSubscription.query.filter_by(
            user_id=u.id,
        ).count()
        assert remaining == 1


def test_send_push_payload_drops_none_values(monkeypatch):
    """tag=None should NOT appear in the payload JSON — service-
    workers branch on its presence."""
    import api.Modules.Notifications.Services.push as push_svc
    import json as _json
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd")
    from api.Modules.Announcements.Models import PushSubscription
    from api.Modules.Tenancy.Models import User
    from app import app as flask_app, db
    with flask_app.app_context():
        PushSubscription.query.delete()
        db.session.commit()
        u = User(
            username="payload-test@test.com", password_hash="x",
            role="admin", full_name="x",
            email="payload-test@test.com", store_id=1,
        )
        db.session.add(u); db.session.flush()
        db.session.add(PushSubscription(
            user_id=u.id,
            endpoint="https://push.example.com/x",
            p256dh="p", auth="a",
        ))
        db.session.commit()
        with patch("pywebpush.webpush") as wp:
            wp.return_value = None
            push_svc.send_push(
                db.session, u.id, "hi",
                body="b", url="/x", tag=None,
            )
            payload = wp.call_args.kwargs["data"]
            decoded = _json.loads(payload)
            # tag=None was dropped.
            assert "tag" not in decoded
            assert decoded == {"title": "hi", "body": "b", "url": "/x"}


# ── legacy Flask wrappers ──────────────────────────────────


def test_legacy_push_enabled_delegates(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "BHj")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "wHd")
    from app import push_enabled as legacy
    assert legacy() is True


def test_legacy_push_enabled_false_when_unconfigured(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "")
    from app import push_enabled as legacy
    assert legacy() is False


def test_legacy_send_push_delegates(monkeypatch):
    import api.Modules.Notifications.Services.push as push_svc
    monkeypatch.setattr(push_svc, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(push_svc, "VAPID_PRIVATE_KEY", "")
    from app import app as flask_app
    from app import send_push as legacy
    with flask_app.app_context():
        # Disabled → 0
        assert legacy(1, "hi") == 0
