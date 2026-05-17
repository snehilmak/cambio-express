"""Service-layer unit tests for
``api.Modules.Auth.Services.sessions``.

The HTTP integration tests in ``test_sessions_endpoint.py`` cover
auth gating + JWT-claim plumbing. This file pins the chain-walk
logic in isolation.
"""
from datetime import datetime, timedelta

from api.Modules.Auth.Models import RefreshToken
from api.Modules.Auth.Services.refresh import issue, rotate
from api.Modules.Auth.Services.sessions import (
    LEGACY_SESSION_ID,
    list_active_sessions,
    revoke_other_sessions,
    revoke_session,
)
from api.Modules.Tenancy.Models import User
from tests._app import db, db_session


def _seed_user(username: str = "sess-user@test.com") -> int:
    u = User(
        username=username,
        password_hash="x",
        role="admin",
        full_name="Sess Test",
        email=username,
        notify_locked_day_digest=False,
    )
    db.session.add(u); db.session.commit()
    return u.id


# ── list_active_sessions ────────────────────────────────────


def test_list_returns_one_row_per_distinct_session():
    """Two distinct logins (two different ``session_id``s) for the
    same user → two rows on the panel."""
    with db_session():
        uid = _seed_user("sess-list-distinct@test.com")
        a = issue(db.session, user_id=uid,
                  user_agent="UA-A", ip_address="1.1.1.1")
        b = issue(db.session, user_id=uid,
                  user_agent="UA-B", ip_address="2.2.2.2")
        db.session.commit()
        sessions = list_active_sessions(db.session, user_id=uid)
    assert {s.session_id for s in sessions} == {a.session_id, b.session_id}


def test_list_collapses_rotation_chain_to_one_session():
    """``rotate()`` inherits ``session_id`` from the predecessor so
    a refresh chain looks like a single session on the panel."""
    with db_session():
        uid = _seed_user("sess-list-chain@test.com")
        first = issue(db.session, user_id=uid, user_agent="UA")
        db.session.commit()
        # Rotate twice — three rows in DB sharing one session_id.
        _, second = rotate(db.session, jti=first.jti)
        _, third = rotate(db.session, jti=second.jti)
        db.session.commit()
        sessions = list_active_sessions(db.session, user_id=uid)
    assert len(sessions) == 1
    assert sessions[0].session_id == first.session_id
    # Head row's metadata is the most-recently-rotated one. We
    # didn't pass user_agent on rotate(), so the head row's
    # user_agent is empty.
    assert sessions[0].user_agent == ""


def test_list_uses_head_row_metadata_after_rotation():
    """When ``rotate()`` is given a fresh user_agent / ip_address,
    the head row's metadata wins on the panel — useful for "you
    just refreshed from a new IP" forensics."""
    with db_session():
        uid = _seed_user("sess-list-head@test.com")
        first = issue(
            db.session, user_id=uid,
            user_agent="Chrome", ip_address="1.1.1.1",
        )
        db.session.commit()
        _, second = rotate(
            db.session, jti=first.jti,
            user_agent="Firefox", ip_address="2.2.2.2",
        )
        db.session.commit()
        sessions = list_active_sessions(db.session, user_id=uid)
    assert len(sessions) == 1
    assert sessions[0].user_agent == "Firefox"
    assert sessions[0].ip_address == "2.2.2.2"


def test_list_marks_current_session_via_sid_claim():
    """``current_session_id`` flags the matching row.
    Non-matching rows render with ``is_current=False``."""
    with db_session():
        uid = _seed_user("sess-list-current@test.com")
        here = issue(db.session, user_id=uid)
        away = issue(db.session, user_id=uid)
        db.session.commit()
        sessions = list_active_sessions(
            db.session, user_id=uid,
            current_session_id=here.session_id,
        )
    current_flags = {s.session_id: s.is_current for s in sessions}
    assert current_flags[here.session_id] is True
    assert current_flags[away.session_id] is False


def test_list_skips_revoked_sessions():
    """A revoked chain doesn't appear on the panel — that's the
    whole point of revoke."""
    with db_session():
        uid = _seed_user("sess-list-revoked@test.com")
        a = issue(db.session, user_id=uid)
        b = issue(db.session, user_id=uid)
        db.session.commit()
        revoke_session(db.session, user_id=uid, session_id=a.session_id)
        db.session.commit()
        sessions = list_active_sessions(db.session, user_id=uid)
    assert {s.session_id for s in sessions} == {b.session_id}


def test_list_skips_expired_sessions():
    """Past-expiry tokens are also filtered out so a stale chain
    that never got rotated falls off the panel by itself."""
    with db_session():
        uid = _seed_user("sess-list-expired@test.com")
        a = issue(db.session, user_id=uid)
        db.session.commit()
        # Manually rewind the row's expiry into the past — the
        # path that would normally do this (a 14-day-old refresh
        # cookie) is impractical in a unit test.
        row = (
            db.session.query(RefreshToken)
              .filter_by(jti=a.jti).one()
        )
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        sessions = list_active_sessions(db.session, user_id=uid)
    assert sessions == []


def test_list_legacy_rows_collapse_to_one_session():
    """Rows pre-dating the ``session_id`` column (NULL value) are
    grouped as a single legacy session per user. They show up on
    the panel so the user can revoke them like any other."""
    with db_session():
        uid = _seed_user("sess-list-legacy@test.com")
        legacy_a = RefreshToken(
            jti="leg-a", user_id=uid,
            created_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
        legacy_b = RefreshToken(
            jti="leg-b", user_id=uid,
            created_at=datetime.utcnow() - timedelta(hours=1),
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
        db.session.add_all([legacy_a, legacy_b])
        db.session.commit()
        sessions = list_active_sessions(db.session, user_id=uid)
    legacy_rows = [s for s in sessions if s.session_id == LEGACY_SESSION_ID]
    assert len(legacy_rows) == 1


def test_list_isolates_users():
    """User A's sessions never leak into User B's panel — the
    user_id filter is the entire security boundary."""
    with db_session():
        a_id = _seed_user("sess-iso-a@test.com")
        b_id = _seed_user("sess-iso-b@test.com")
        a = issue(db.session, user_id=a_id)
        issue(db.session, user_id=b_id)
        db.session.commit()
        b_sessions = list_active_sessions(db.session, user_id=b_id)
    assert all(s.session_id != a.session_id for s in b_sessions)


# ── revoke_session ──────────────────────────────────────────


def test_revoke_session_revokes_every_row_in_chain():
    """A chain that's been rotated three times has three rows in
    the DB; revoking the session revokes all three."""
    with db_session():
        uid = _seed_user("sess-rev-chain@test.com")
        first = issue(db.session, user_id=uid)
        db.session.commit()
        _, second = rotate(db.session, jti=first.jti)
        _, third = rotate(db.session, jti=second.jti)
        db.session.commit()
        # Pre-revoke: first + second are revoked-by-rotation,
        # third (the head) is live. revoke_session should flip
        # the third's revoked_at too.
        n = revoke_session(
            db.session, user_id=uid, session_id=first.session_id,
        )
        db.session.commit()
    # Only the head row was alive pre-revoke; the rotated
    # predecessors were already revoked-by-rotation so they don't
    # count.
    assert n == 1
    with db_session():
        # All three rows are now revoked.
        rows = (
            db.session.query(RefreshToken)
              .filter_by(user_id=uid).all()
        )
        assert len(rows) == 3
        assert all(r.revoked_at is not None for r in rows)


def test_revoke_session_returns_zero_for_other_users():
    """Revoking another user's session_id is a 0-affected no-op —
    the user_id filter is the security boundary."""
    with db_session():
        a_id = _seed_user("sess-rev-cross-a@test.com")
        b_id = _seed_user("sess-rev-cross-b@test.com")
        a = issue(db.session, user_id=a_id)
        db.session.commit()
        n = revoke_session(
            db.session, user_id=b_id, session_id=a.session_id,
        )
        db.session.commit()
        # A's session must still be alive.
        sessions = list_active_sessions(db.session, user_id=a_id)
    assert n == 0
    assert any(s.session_id == a.session_id for s in sessions)


def test_revoke_session_handles_legacy_bucket():
    """Passing ``LEGACY_SESSION_ID`` revokes every NULL-session row
    for the user."""
    with db_session():
        uid = _seed_user("sess-rev-legacy@test.com")
        a = RefreshToken(
            jti="rev-leg-a", user_id=uid,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
        b = RefreshToken(
            jti="rev-leg-b", user_id=uid,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
        db.session.add_all([a, b])
        db.session.commit()
        n = revoke_session(
            db.session, user_id=uid, session_id=LEGACY_SESSION_ID,
        )
        db.session.commit()
    assert n == 2


# ── revoke_other_sessions ──────────────────────────────────


def test_revoke_other_sessions_keeps_the_current_one():
    with db_session():
        uid = _seed_user("sess-rev-others@test.com")
        keep = issue(db.session, user_id=uid)
        drop_a = issue(db.session, user_id=uid)
        drop_b = issue(db.session, user_id=uid)
        db.session.commit()
        n = revoke_other_sessions(
            db.session, user_id=uid, keep_session_id=keep.session_id,
        )
        db.session.commit()
        live = list_active_sessions(db.session, user_id=uid)
    assert {s.session_id for s in live} == {keep.session_id}
    # Two chains revoked, one row apiece.
    assert n == 2
    _ = (drop_a, drop_b)  # used to keep the test readable


def test_revoke_other_sessions_isolates_users():
    """User B running ``revoke_other_sessions`` does NOT touch
    User A's sessions."""
    with db_session():
        a_id = _seed_user("sess-rev-others-iso-a@test.com")
        b_id = _seed_user("sess-rev-others-iso-b@test.com")
        a = issue(db.session, user_id=a_id)
        b_keep = issue(db.session, user_id=b_id)
        b_drop = issue(db.session, user_id=b_id)
        db.session.commit()
        revoke_other_sessions(
            db.session, user_id=b_id,
            keep_session_id=b_keep.session_id,
        )
        db.session.commit()
        a_sessions = list_active_sessions(db.session, user_id=a_id)
    # A's session is untouched.
    assert any(s.session_id == a.session_id for s in a_sessions)
    _ = b_drop
