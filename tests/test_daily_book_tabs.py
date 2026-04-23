"""Daily Book page uses a sticky top bar (3-card totals + tab bar) +
four <section> panels (receipts / disbursements / transfers / summary).
These tests guard the structural contract so a future refactor can't
silently drop a tab or break the full-form save round-trip.
"""
import re
from datetime import date


def _today_ds():
    return date.today().isoformat()


def _get_body(client, ds=None):
    ds = ds or _today_ds()
    resp = client.get(f"/daily/{ds}")
    assert resp.status_code == 200
    return resp.data.decode()


def test_totals_strip_and_tab_bar_present(logged_in_client):
    body = _get_body(logged_in_client)
    # Sticky wrapper + 3 totals cards with live-update ids
    assert 'class="db-topbar"' in body
    assert 'db-totals-strip' in body
    for tid in ("top-sum-rec", "top-sum-dis", "top-sum-net", "top-net-card"):
        assert f'id="{tid}"' in body, f"totals-strip id missing: {tid}"
    # Tab bar exists with the expected tab ids
    assert 'id="db-tabs"' in body
    for tab in ("receipts", "disbursements", "transfers", "summary"):
        assert f'data-tab="{tab}"' in body, f"tab button missing: {tab}"


def test_exactly_one_tab_selected_on_load(logged_in_client):
    """Default active tab is Receipts — one and only one aria-selected=true
    among the tab buttons. Guards against the tab state diverging."""
    body = _get_body(logged_in_client)
    # Slice out just the tab bar to avoid matching the CSS selector
    m = re.search(r'<div class="db-tab-bar"[^>]*>([\s\S]+?)</div>', body)
    assert m, "tab bar block not found"
    tab_bar = m.group(1)
    true_count  = tab_bar.count('aria-selected="true"')
    false_count = tab_bar.count('aria-selected="false"')
    assert true_count == 1, f"expected 1 tab selected, got {true_count}"
    assert false_count == 3, f"expected 3 unselected tabs, got {false_count}"
    # The selected one is Receipts
    assert re.search(r'aria-selected="true"[^>]*data-tab="receipts"', tab_bar), \
        "Receipts should be the default-selected tab"


def test_four_panels_with_correct_default_visibility(logged_in_client):
    """Receipts visible, other three hidden by default."""
    body = _get_body(logged_in_client)
    panels = re.findall(r'<section class="db-tab-panel"[^>]*id="panel-(\w+)"([^>]*)>', body)
    ids = [name for name, _ in panels]
    assert set(ids) == {"receipts", "disbursements", "transfers", "summary"}, ids
    by_id = dict(panels)
    assert "hidden" not in by_id["receipts"], "receipts panel should be visible"
    for name in ("disbursements", "transfers", "summary"):
        assert "hidden" in by_id[name], f"{name} panel should be hidden by default"


def test_section_boxes_moved_into_correct_panels(logged_in_client):
    """Each section-box ends up in the expected panel. Slice the rendered
    HTML by panel id and assert the right section-box headers live inside."""
    body = _get_body(logged_in_client)

    def panel_html(name):
        m = re.search(
            rf'<section class="db-tab-panel"[^>]*id="panel-{name}"[\s\S]*?</section>',
            body,
        )
        assert m, f"panel-{name} not found"
        return m.group(0)

    rec = panel_html("receipts")
    assert "RECEIPTS" in rec and "TOTAL RECEIPTS" in rec
    # Widgets that should be in Receipts
    assert "Return Check Paid Back" in rec

    dis = panel_html("disbursements")
    assert "DISBURSEMENTS" in dis and "TOTAL DISBURSEMENTS" in dis
    # Line-item widgets + drops + checks live under Disbursements
    for label in ("Cash Purchases", "Cash Expense", "Check Purchases",
                  "Check Expense", "Outside Cash & Drops", "Checks Deposit",
                  "Cash Deposit", "Safe Balance", "Payroll Expense",
                  "Other Cash Out"):
        assert label in dis, f"missing in Disbursements: {label}"

    xfr = panel_html("transfers")
    assert "MONEY TRANSFERS" in xfr
    assert "EMPLOYEE TRANSFERS THIS DAY" in xfr

    summ = panel_html("summary")
    assert "OVER / SHORT" in summ
    assert "NOTES" in summ
    assert 'name="over_short"' in summ
    assert 'name="notes"' in summ


def test_save_round_trip_persists_fields_from_all_tabs(logged_in_client, test_store_id):
    """Even though only one tab is visible at render time, every panel's
    inputs are still inside the same <form> — submitting saves them all.
    Regression guard: a future refactor that moves a panel outside the
    form would silently lose data from that tab."""
    from app import DailyReport
    ds = _today_ds()
    resp = logged_in_client.post(f"/daily/{ds}", data={
        "taxable_sales": "100.00",       # Receipts tab
        "cash_deposit": "250.00",        # Disbursements tab
        "safe_balance": "9000.00",       # Disbursements tab
        "over_short":   "5.25",          # Summary tab
        "notes":        "end of day",    # Summary tab
        "mt_amount_intermex": "500.00",  # Transfers tab
    })
    assert resp.status_code in (200, 302)
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt is not None
        assert rpt.taxable_sales == 100.0
        assert rpt.cash_deposit  == 250.0
        assert rpt.safe_balance  == 9000.0
        assert rpt.over_short    == 5.25
        assert rpt.notes         == "end of day"
        # money_transfer is derived from the MT table — Intermex sub-row
        # flows into the grand total.
        assert rpt.money_transfer == 500.0


def test_sticky_save_bar_remains_outside_the_panels(logged_in_client):
    """The save bar must NOT be inside any tab panel — otherwise it would
    disappear when the user switches tabs."""
    body = _get_body(logged_in_client)
    # Find the sticky save bar and the closing </section> of the last panel.
    save_pos = body.find('class="sticky-save-bar"')
    assert save_pos != -1, "sticky-save-bar not present"
    # Every .db-tab-panel should close before the save bar.
    last_panel_close = body.rfind("</section><!-- /panel-")
    assert last_panel_close != -1 and last_panel_close < save_pos, \
        "save bar is nested inside a tab panel; switching tabs would hide it"
