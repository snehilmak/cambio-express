"""The Stripe Connection card on /superadmin/controls?tab=overview
must not show the account_id twice when the connected account has no
email. Earlier the "Account" row fell back to account_id, which then
duplicated the dedicated "Account ID" row right below it.
"""
import re
from unittest.mock import patch


def _superadmin_client(client):
    from app import User
    with client.application.app_context():
        uid = User.query.filter_by(username="superadmin", store_id=None).first().id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "superadmin"
    return client


def _fake_account(email):
    """Mimic the dict-style accessor used by stripe_health_check()."""
    return {"id": "acct_TEST123", "email": email}


def _account_section(body):
    """Slice from 'Stripe connection' card title to the next card boundary."""
    m = re.search(
        r'card-title">Stripe connection.*?(?=<div class="card mb-3"|</div>\s*</div>\s*{% if|<!--)',
        body, re.S,
    )
    return m.group(0) if m else body


def test_no_account_row_when_email_missing(client):
    """Empty email → only the dedicated 'Account ID' row renders.
    Guards the duplicate-ID regression."""
    _superadmin_client(client)
    with patch("app.stripe.Account.retrieve", return_value=_fake_account("")):
        body = client.get("/superadmin/controls?tab=overview").data.decode()

    section = _account_section(body)
    # 'Account ID' label still present; bare 'Account' label should not be.
    assert "Account ID" in section
    # The bare "Account" label appears only when wrapped in <span class="k">Account</span>.
    # Match the exact label cell to avoid catching "Account ID" or "account".
    assert '<span class="k">Account</span>' not in section
    # The acct ID appears exactly once in this card.
    assert section.count("acct_TEST123") == 1


def test_account_row_renders_when_email_present(client):
    """Real email → 'Account' shows the email, 'Account ID' shows the ID."""
    _superadmin_client(client)
    with patch("app.stripe.Account.retrieve",
               return_value=_fake_account("ops@dinerobook.com")):
        body = client.get("/superadmin/controls?tab=overview").data.decode()

    section = _account_section(body)
    assert '<span class="k">Account</span>' in section
    assert "ops@dinerobook.com" in section
    assert "acct_TEST123" in section
    # Email must not also appear in the ID slot, and ID must not be duplicated.
    assert section.count("acct_TEST123") == 1
