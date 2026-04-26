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


# ── Regression: tabs broke when a read-only line-item widget had no
#                Add button. initLineItemWidget('return_payback') threw
#                a TypeError on addBtn.addEventListener, which halted
#                the <script> tag and prevented the tab-switcher IIFE
#                below it from binding the click handler. Result:
#                cashier was stuck on the Receipts tab.
#
# The fix is a `if (!addBtn) return;` guard inside initLineItemWidget,
# placed AFTER the toggle wiring (which uses `root` only) and BEFORE
# the addBtn / tbody event bindings. These tests pin both surfaces of
# the contract so a future refactor can't silently re-break the
# tabs.

def test_return_payback_widget_has_no_add_button(logged_in_client):
    """The read-only return_payback widget must NOT render an
    `id='li-return_payback-add'` element. If a future change re-adds
    one, the guard test below stops being meaningful — but on the
    other hand the original crash path also stops applying."""
    body = _get_body(logged_in_client)
    assert 'id="li-return_payback-details"' in body, \
        "return_payback widget should still mount"
    assert 'id="li-return_payback-add"' not in body, \
        "read-only widget shouldn't render an Add button"


def test_init_line_item_widget_guards_against_missing_add_button(logged_in_client):
    """The inline JS must early-return when the Add button isn't on
    the page — otherwise binding `addBtn.addEventListener` throws a
    TypeError, halts the <script> tag, and the tab switcher (defined
    in the same script block) never wires up. That bug stranded
    cashiers on the Receipts tab.

    We can't execute JS in pytest cheaply, so we pin the source: the
    guard `if (!addBtn) return;` must appear AFTER `addBtn = q('add')`
    and BEFORE `addBtn.addEventListener`. The exact text of the guard
    doesn't matter, but its existence and position do.
    """
    body = _get_body(logged_in_client)
    # Find the relevant slice of the script tag.
    fn_start = body.find("function initLineItemWidget(")
    assert fn_start != -1, "initLineItemWidget function must be in the script"
    # End of function = the .forEach(initLineItemWidget) call site.
    fn_end = body.find(".forEach(initLineItemWidget)", fn_start)
    assert fn_end != -1
    fn_body = body[fn_start:fn_end]

    add_decl_idx = fn_body.find("addBtn  = q('add')")
    if add_decl_idx == -1:
        add_decl_idx = fn_body.find('addBtn = q("add")')
    assert add_decl_idx != -1, "addBtn decl must exist"

    # Anchor on `addBtn.addEventListener(` (with paren) so any prose
    # comment that mentions the call doesn't get matched first.
    add_listen_idx = fn_body.find("addBtn.addEventListener(")
    assert add_listen_idx != -1
    assert add_listen_idx > add_decl_idx

    # The guard must sit between the decl and the listener-bind.
    guard_idx = fn_body.find("if (!addBtn) return;")
    assert guard_idx != -1, (
        "initLineItemWidget is missing the `if (!addBtn) return;` "
        "guard — without it, read-only line-item widgets crash the "
        "<script> tag and break the daily-book tab switcher."
    )
    assert add_decl_idx < guard_idx < add_listen_idx, (
        "the `if (!addBtn) return;` guard is in the wrong place — "
        "it must sit AFTER addBtn is declared and BEFORE the first "
        "addBtn.addEventListener call."
    )


def test_daily_book_tab_switcher_iife_present(logged_in_client):
    """Pin that the tab-switcher IIFE is still in the rendered page
    (a guard against accidentally deleting the whole block)."""
    body = _get_body(logged_in_client)
    # The IIFE binds a click on `#db-tabs` and toggles aria-selected;
    # match on the click registration to be resilient to whitespace.
    assert "getElementById('db-tabs')" in body
    # And the click listener that drives `activate(btn.dataset.tab)`
    assert "btn.dataset.tab" in body


# ── Desktop grid layout (≥901px): all four panels visible at once ──
#
# The cashier's existing spreadsheet has Receipts + Disbursements
# side-by-side and Money Transfers + Other Reports below — much less
# clicking than tabs. The .db-grid wrapper makes the same 2×2 layout
# happen on desktop while leaving mobile (which uses the tab bar) alone.

def test_db_grid_wrapper_wraps_all_four_panels(logged_in_client):
    """The four panels must sit inside <div class='db-grid'> so the
    desktop 2x2 grid CSS has something to attach to. The wrapper opens
    BEFORE panel-receipts and closes AFTER panel-transfers."""
    body = _get_body(logged_in_client)
    grid_open  = body.find('class="db-grid"')
    rec_open   = body.find('id="panel-receipts"')
    tx_close   = body.rfind('</section><!-- /panel-transfers -->')
    grid_close = body.find('</div><!-- /db-grid -->')
    for name, idx in [('db-grid open', grid_open),
                      ('panel-receipts', rec_open),
                      ('panel-transfers close', tx_close),
                      ('db-grid close', grid_close)]:
        assert idx != -1, f"missing: {name}"
    assert grid_open < rec_open < tx_close < grid_close, (
        "db-grid wrapper must enclose ALL four panels (receipts first, "
        "transfers last in DOM order)")


def test_desktop_css_hides_tab_bar_and_shows_all_panels(logged_in_client):
    """Pin the desktop CSS contract so a future refactor doesn't drop
    one of the rules and silently re-break either the mobile tab UX
    or the desktop all-visible layout."""
    body = _get_body(logged_in_client)
    # Find the @media (min-width: 901px) block. Must contain:
    #   .db-grid { display: grid; ... 1fr 1fr ... }
    #   .db-grid > .db-tab-panel[hidden] { display: block ...}
    #   .db-tab-bar { display: none; }
    media_idx = body.find("@media (min-width: 901px)")
    assert media_idx != -1
    media_end = body.find("</style>", media_idx)
    block = body[media_idx:media_end]

    assert ".db-grid {" in block, "db-grid block missing on desktop"
    assert "grid-template-columns: 1fr 1fr" in block, \
        "desktop should use 2-column grid"
    assert "[hidden]" in block and "display: block" in block, (
        "desktop must override the [hidden] attribute so all four "
        "panels are visible at once")
    assert ".db-tab-bar { display: none; }" in block, (
        "desktop should hide the tab bar (everything's already on "
        "screen, the bar would be visual noise)")


def test_desktop_panel_order_matches_excel_layout(logged_in_client):
    """The legacy spreadsheet has Receipts + Disbursements on the top
    row and Money Transfers + Over/Short on the bottom — the grid
    `order:` rules in the desktop CSS must reproduce that pairing.
    DOM order is receipts/disbursements/summary/transfers, so without
    the order overrides the grid would lay out as receipts |
    disbursements / summary | transfers — wrong (transfers and
    summary swapped)."""
    body = _get_body(logged_in_client)
    media_idx = body.find("@media (min-width: 901px)")
    block = body[media_idx:body.find("</style>", media_idx)]
    # Each panel needs an explicit order. Receipts must be 1, disb 2,
    # transfers 3 (NOT 4), summary 4 (NOT 3).
    import re
    def order_for(panel):
        m = re.search(r"#panel-" + panel + r"\s*\{\s*order:\s*(\d+)", block)
        assert m, f"#panel-{panel} missing an `order:` rule on desktop"
        return int(m.group(1))
    assert order_for("receipts") == 1
    assert order_for("disbursements") == 2
    assert order_for("transfers") == 3
    assert order_for("summary") == 4


def test_mobile_tab_bar_still_renders(logged_in_client):
    """Sanity: hiding the tab bar is gated on the desktop @media
    block. The default markup must still render the bar so mobile
    keeps its navigation."""
    body = _get_body(logged_in_client)
    # The bar is server-rendered unconditionally; CSS at ≥901px hides
    # it. The element must be present in the DOM.
    assert 'class="db-tab-bar"' in body
    # And the four tab buttons that drive the mobile single-panel view.
    for tab in ("receipts", "disbursements", "transfers", "summary"):
        assert f'data-tab="{tab}"' in body
