"""Email / phone as the sign-in identifier (L-2).

New logins are created with an email and/or a phone number; there is
no username to type. Accounts that predate this keep their usernames
and keep working — including the seeded superadmin.
"""
import pytest

from api.Modules.Auth.Services.identity import (
    is_email, login_identifier, normalize_email, normalize_phone,
)
from tests._app import db, db_session


# ── Normalisation (pure) ────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("  Amber@Store.com ", "amber@store.com"),
    ("AMBER@STORE.COM", "amber@store.com"),
    ("", ""),
    (None, ""),
])
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


def test_normalize_email_keeps_dots_and_plus_tags():
    """Gmail treats a+tag@ and a.b@ as one mailbox; most providers do
    not. Collapsing them would let one person's address match
    another's account."""
    assert normalize_email("a.b+tag@store.com") == "a.b+tag@store.com"


@pytest.mark.parametrize("raw,expected", [
    # Every way an operator might type the same US number.
    ("(555) 123-4567", "5551234567"),
    ("555-123-4567", "5551234567"),
    ("555.123.4567", "5551234567"),
    ("+1 555 123 4567", "5551234567"),
    ("15551234567", "5551234567"),
    ("5551234567", "5551234567"),
    # Too short to be a phone number — don't invent a match.
    ("123", ""),
    ("", ""),
    (None, ""),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_normalize_phone_keeps_international_digits():
    """We can't tell a country code from a subscriber digit without a
    full phone library, so non-NANP numbers keep every digit rather
    than risk corrupting them."""
    assert normalize_phone("+44 20 7946 0958") == "442079460958"


@pytest.mark.parametrize("raw,expected", [
    ("amber@store.com", True),
    ("a@b.co", True),
    ("amber", False),
    ("amber@store", False),
    ("with space@store.com", False),
    ("", False),
])
def test_is_email(raw, expected):
    assert is_email(raw) is expected


def test_login_identifier_prefers_email():
    """Email wins when both are given — it's the channel password
    reset already runs on."""
    assert login_identifier("A@b.com", "555-123-4567") == "a@b.com"


def test_login_identifier_falls_back_to_phone():
    """Cashiers often have no email address."""
    assert login_identifier("", "(555) 123-4567") == "5551234567"
    assert login_identifier(None, "555-123-4567") == "5551234567"


def test_login_identifier_empty_when_neither_is_usable():
    assert login_identifier("", "") == ""
    assert login_identifier(None, None) == ""
    assert login_identifier("not-an-email", "12") == ""


# ── Creating a login ────────────────────────────────────────


def _admin_token(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _create(client, token, **body):
    return client.post(
        "/api/v2/admin/users",
        json={"password": "cashierpw1!", "role": "employee", **body},
        headers={"Authorization": f"Bearer {token}"},
    )


def _login(client, identifier, password="cashierpw1!"):
    return client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": identifier, "password": password},
    )


def test_create_requires_an_email_or_phone(client, test_store_id):
    """A login with neither is unusable — nothing to sign in with."""
    token = _admin_token(client, test_store_id)
    resp = _create(client, token, full_name="No Contact")
    assert resp.status_code == 422
    assert "email address or phone number" in str(resp.get_json())


def test_create_with_email_signs_in_with_it(client, test_store_id):
    token = _admin_token(client, test_store_id)
    created = _create(client, token, email="Amber@Store.com")
    assert created.status_code == 201
    # Stored normalised, not as typed.
    assert created.get_json()["username"] == "amber@store.com"
    # ...and case doesn't matter at sign-in either.
    assert _login(client, "AMBER@store.com").status_code == 200


def test_create_with_phone_only_signs_in_by_phone(client, test_store_id):
    """Cashiers without an email get a phone-only login, and the
    number works however it's punctuated."""
    token = _admin_token(client, test_store_id)
    created = _create(client, token, phone="(555) 987-6543")
    assert created.status_code == 201
    assert created.get_json()["username"] == "5559876543"

    for typed in ("5559876543", "(555) 987-6543", "555-987-6543",
                  "+1 555 987 6543"):
        resp = _login(client, typed)
        assert resp.status_code == 200, f"{typed} should sign in"


def test_create_with_both_prefers_email_but_phone_still_signs_in(
    client, test_store_id,
):
    """Email is the stored identifier; the phone is still a working
    way in, so the person can use whichever they remember."""
    token = _admin_token(client, test_store_id)
    created = _create(
        client, token, email="both@store.com", phone="555-222-3333",
    )
    assert created.status_code == 201
    assert created.get_json()["username"] == "both@store.com"
    assert _login(client, "both@store.com").status_code == 200
    assert _login(client, "(555) 222-3333").status_code == 200


def test_create_rejects_a_malformed_email(client, test_store_id):
    token = _admin_token(client, test_store_id)
    resp = _create(client, token, email="not-an-email")
    assert resp.status_code == 422
    assert "valid email" in str(resp.get_json())


def test_create_rejects_a_too_short_phone(client, test_store_id):
    token = _admin_token(client, test_store_id)
    resp = _create(client, token, phone="123")
    assert resp.status_code == 422
    assert "valid phone" in str(resp.get_json())


def test_create_rejects_a_duplicate_identifier_in_the_store(
    client, test_store_id,
):
    token = _admin_token(client, test_store_id)
    assert _create(client, token, email="dupe@store.com").status_code == 201
    again = _create(client, token, email="Dupe@Store.com")
    assert again.status_code == 422
    # Anchored on the field the operator filled in.
    assert "email" in again.get_json()["detail"]["field_errors"]


def test_phone_duplicate_is_caught_despite_formatting(
    client, test_store_id,
):
    """Two spellings of one number are one person — the second must
    not quietly become a separate account."""
    token = _admin_token(client, test_store_id)
    assert _create(client, token, phone="555-444-1111").status_code == 201
    again = _create(client, token, phone="(555) 444-1111")
    assert again.status_code == 422


# ── Grandfathered usernames ─────────────────────────────────


def test_legacy_username_still_signs_in(client):
    """Accounts created before L-2 keep working — nobody is locked
    out by the identifier change."""
    from api.Modules.Tenancy.Models import Store, User
    with db_session():
        s = Store(name="Legacy Store", slug="legacy-login",
                  email="legacy@x.com", plan="basic")
        db.session.add(s); db.session.commit()
        u = User(store_id=s.id, username="old.timer", role="employee",
                 full_name="Old Timer", is_active=True)
        u.set_password("legacypw123!")
        db.session.add(u); db.session.commit()

    resp = _login(client, "old.timer", password="legacypw123!")
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "employee"


def test_seeded_superadmin_username_is_unaffected(client):
    """The platform account signs in with `superadmin`. If the
    identifier change broke it there'd be no way back in."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        sa = (
            db.session.query(User)
            .filter(User.role == "superadmin").first()
        )
        assert sa is not None
        # Whatever it is, it is not required to be an email.
        assert sa.username


def test_set_login_phone_keeps_display_and_canonical_in_step():
    """Assigning `phone` directly would leave `login_phone` stale and
    silently break phone sign-in — the setter is the only safe path."""
    from api.Modules.Tenancy.Models import User
    u = User(store_id=None, username="setter@x.com", role="employee")
    u.set_login_phone("(555) 321-7654")
    assert u.phone == "(555) 321-7654"   # as the operator typed it
    assert u.login_phone == "5553217654"  # canonical, for lookup
    u.set_login_phone("")
    assert u.phone == ""
    assert u.login_phone == ""
