"""Bank Accounts card on the admin dashboard — the "Connect Bank via
Stripe" button belongs inside the centered .empty-state block so it
lines up under the explanatory copy. Regression test for the button
drifting out of the .empty-state wrapper and landing at the left edge
of the card.
"""
import re


def _bank_card(body):
    """Return the 'Bank Accounts' card block from the rendered page."""
    m = re.search(
        r'<span class="card-title">Bank Accounts</span>[\s\S]+?</div>\s*</div>\s*</div>',
        body,
    )
    assert m, "Bank Accounts card not found on dashboard"
    return m.group(0)


def test_connect_button_is_inside_empty_state(logged_in_client):
    """A fresh admin store has no Stripe bank connected — the empty
    state + connect-button branch must render, and the connect CTA
    must sit inside the centered .empty-state div. The dashboard CTA
    is a link to /bank (where the Stripe.js modal lives) — the FC
    connect flow itself happens on /bank, not on the dashboard."""
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data.decode()

    card = _bank_card(body)
    assert "No bank connected yet" in card
    assert "Connect Bank via Stripe" in card

    empty_open = card.find('<div class="empty-state"')
    assert empty_open != -1, ".empty-state div missing"
    # The CTA is now an <a href="/bank">; assert it sits inside the
    # empty-state block. The closing </a> + the wrapper </div> after
    # it must both come before .empty-state closes.
    link_open  = card.find('<a ', empty_open)
    link_close = card.find("</a>", link_open)
    after_close = card.find("</div>", link_close)
    assert link_open != -1 and link_close != -1 and after_close != -1
    assert empty_open < link_open < link_close < after_close, \
        "Connect Bank CTA escaped the centered .empty-state block"
    assert 'href="/bank"' in card or "href=\"/bank\"" in card, \
        "Dashboard CTA must link to /bank where the Stripe.js modal lives"
