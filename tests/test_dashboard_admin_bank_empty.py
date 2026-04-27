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
    state + connect-button branch must render, and the form must sit
    inside the centered .empty-state div."""
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data.decode()

    card = _bank_card(body)
    # The empty-state copy must render (confirms we're on the expected branch).
    assert "No bank connected yet" in card
    assert "Connect Bank via Stripe" in card

    # The Connect form must appear before .empty-state closes — i.e.
    # it's nested inside the centered block. We find the start of the
    # empty-state div and the matching close tag, and assert the form
    # is between them.
    empty_open  = card.find('<div class="empty-state"')
    assert empty_open != -1, ".empty-state div missing"
    # Naively match the next </div> after the form open: the empty-state
    # block has exactly one level of nested form, so the next </div>
    # after the form's close is the wrapper close.
    form_open  = card.find("<form", empty_open)
    form_close = card.find("</form>", form_open)
    empty_close_after = card.find("</div>", form_close)
    assert form_open != -1 and form_close != -1 and empty_close_after != -1
    # The form must be bracketed by the empty-state div.
    assert empty_open < form_open < form_close < empty_close_after, \
        "Connect Bank form escaped the centered .empty-state block"
