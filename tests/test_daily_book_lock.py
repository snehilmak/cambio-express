"""Lock / unlock feature for the Daily Book.

Backend contract:
  - POST /daily/<ds>/lock   sets locked_at + locked_by
  - POST /daily/<ds>/unlock clears both
  - Every write route rejects while locked:
        POST /daily/<ds>                                   (main form)
        POST /daily/<ds>/drops/new + /<id>/delete
        POST /daily/<ds>/check-deposits/new + /<id>/delete
        POST /daily/<ds>/line-items/<kind>/new + /<id>/delete

UI contract:
  - Header swaps between Lock / Unlock buttons + matching badge.
  - Form carries data-locked="1" when locked so the client-side JS
    mirrors the server-side gate.
  - Save bar hides the Save button when locked.
"""
import json
import re
from datetime import date, time


def _today_ds():
    return date.today().isoformat()


def _lock(client, ds=None):
    ds = ds or _today_ds()
    resp = client.post(f"/daily/{ds}/lock")
    assert resp.status_code == 302


def _unlock(client, ds=None):
    ds = ds or _today_ds()
    resp = client.post(f"/daily/{ds}/unlock")
    assert resp.status_code == 302


def _form_tag(body):
    m = re.search(r'<form method="POST" id="daily-form"[^>]*>', body)
    assert m, "daily-form tag not found"
    return m.group(0)


def test_lock_sets_locked_at_and_locked_by(logged_in_client, test_store_id, test_admin_id):
    """Lock POST stamps locked_at + locked_by onto the DailyReport row,
    creating the row if it doesn't exist yet."""
    from app import DailyReport
    ds = _today_ds()
    _lock(logged_in_client, ds)
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt is not None, "locking an empty day must still create the row"
        assert rpt.locked_at is not None
        assert rpt.locked_by == test_admin_id


def test_unlock_clears_lock_fields(logged_in_client, test_store_id):
    from app import DailyReport
    ds = _today_ds()
    _lock(logged_in_client, ds)
    _unlock(logged_in_client, ds)
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt.locked_at is None
        assert rpt.locked_by is None


def test_main_form_save_rejected_while_locked(logged_in_client, test_store_id):
    """A form POST carrying spoofed data must be ignored while locked."""
    from app import DailyReport
    ds = _today_ds()
    _lock(logged_in_client, ds)
    resp = logged_in_client.post(f"/daily/{ds}", data={"taxable_sales": "999.99"})
    assert resp.status_code in (200, 302)  # redirect back, not 500
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert (rpt.taxable_sales or 0) == 0, \
            "main form save must not persist while locked"


def test_drops_new_returns_json_403_while_locked(logged_in_client, test_store_id):
    """Drops are now `kind='drop'` rows in DailyLineItem (after the
    DailyDrop → DailyLineItem unification). The lock guard still
    rejects the add, just via the generic line-items route."""
    from app import DailyLineItem
    ds = _today_ds()
    _lock(logged_in_client, ds)
    r = logged_in_client.post(
        f"/daily/{ds}/line-items/drop/new",
        data={"at_time": "10:00", "amount": "50"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 403
    payload = json.loads(r.data)
    assert payload["ok"] is False
    assert "locked" in payload["error"].lower()
    with logged_in_client.application.app_context():
        assert DailyLineItem.query.filter_by(
            store_id=test_store_id, kind="drop"
        ).count() == 0, "no drop should have been created"


def test_drops_delete_rejected_while_locked(logged_in_client, test_store_id):
    """Drop delete is gated through the generic line-items delete
    route — locked reports refuse to trim existing entries of any
    kind, drops included."""
    from app import DailyLineItem, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        d = DailyLineItem(store_id=test_store_id, report_date=date.today(),
                          kind="drop", at_time=time(9, 0), amount=100.0)
        db.session.add(d); db.session.commit()
        drop_id = d.id
    _lock(logged_in_client, ds)
    r = logged_in_client.post(
        f"/daily/{ds}/line-items/drop/{drop_id}/delete",
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 403
    with logged_in_client.application.app_context():
        assert db.session.get(DailyLineItem, drop_id) is not None, \
            "drop must not have been deleted"


def test_check_deposit_new_rejected_while_locked(logged_in_client, test_store_id):
    """Check deposits are now `kind='check_deposit'` rows in
    DailyLineItem. The lock guard rejects the add via the generic
    line-items route; the legacy CheckDeposit table is untouched."""
    from app import DailyLineItem
    ds = _today_ds()
    _lock(logged_in_client, ds)
    r = logged_in_client.post(
        f"/daily/{ds}/line-items/check_deposit/new",
        data={"at_time": "09:00", "amount": "250"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 403
    with logged_in_client.application.app_context():
        assert DailyLineItem.query.filter_by(
            store_id=test_store_id, kind="check_deposit"
        ).count() == 0


def test_line_item_new_rejected_for_every_kind_while_locked(logged_in_client):
    """Every _LINE_ITEM_KINDS value must reject new rows while locked —
    guards the shared _reject_if_locked path for the generic route."""
    from app import DailyLineItem, _LINE_ITEM_KINDS
    ds = _today_ds()
    _lock(logged_in_client, ds)
    for kind in _LINE_ITEM_KINDS.keys():
        r = logged_in_client.post(
            f"/daily/{ds}/line-items/{kind}/new",
            data={"at_time": "09:00", "amount": "50"},
            headers={"Accept": "application/json"},
        )
        assert r.status_code == 403, f"kind={kind} should reject while locked"
    with logged_in_client.application.app_context():
        assert DailyLineItem.query.count() == 0


def test_line_item_delete_rejected_while_locked(logged_in_client, test_store_id):
    from app import DailyLineItem, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        r = DailyLineItem(store_id=test_store_id, report_date=date.today(),
                          kind="cash_expense", at_time=time(9, 0), amount=50.0)
        db.session.add(r); db.session.commit()
        item_id = r.id
    _lock(logged_in_client, ds)
    resp = logged_in_client.post(
        f"/daily/{ds}/line-items/cash_expense/{item_id}/delete",
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 403
    with logged_in_client.application.app_context():
        assert DailyLineItem.query.filter_by(id=item_id).first() is not None


def test_save_works_after_unlock(logged_in_client, test_store_id):
    """Round-trip: lock → save fails → unlock → save persists."""
    from app import DailyReport
    ds = _today_ds()
    _lock(logged_in_client, ds)
    logged_in_client.post(f"/daily/{ds}", data={"taxable_sales": "111.00"})
    _unlock(logged_in_client, ds)
    resp = logged_in_client.post(f"/daily/{ds}", data={"taxable_sales": "123.45"})
    assert resp.status_code in (200, 302)
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt.taxable_sales == 123.45


def test_template_renders_locked_ui(logged_in_client):
    """Locked state: badge, Unlock button, data-locked attribute, save
    bar message. Unlocked state: Lock button, Save button, no
    data-locked on the form tag."""
    ds = _today_ds()

    body = logged_in_client.get(f"/daily/{ds}").data.decode()
    assert "Lock Day" in body
    assert "Save Daily Report" in body
    assert "Unlock to Edit" not in body
    assert "data-locked" not in _form_tag(body), \
        "form tag should not carry data-locked when unlocked"

    _lock(logged_in_client, ds)
    body = logged_in_client.get(f"/daily/{ds}").data.decode()
    assert "🔒 Locked" in body
    assert "Unlock to Edit" in body
    assert "Lock Day" not in body
    assert "Save Daily Report" not in body
    assert "Unlock above to edit" in body
    assert 'data-locked="1"' in _form_tag(body)


# ── Calendar view surfaces the locked state ────────────────────
#
# Without this indicator the calendar looked identical whether a day
# was locked or not — admins had to click through to see. We match
# the locked state three ways for accessibility + clarity:
#   - `.cal-cell` gets a `locked` CSS class (drives the dimmed /
#     dashed-border styling)
#   - the green `.cal-dot` is replaced with a padlock SVG
#   - `title` attribute carries a tooltip with the lock timestamp

def _calendar_cell_for(body, ds):
    """Extract the <a> opening tag for the calendar cell whose href
    is the given YYYY-MM-DD. Returns (class_attr, title_attr_or_None)."""
    m = re.search(
        r'<a\s+href="[^"]*' + re.escape(ds) +
        r'[^"]*"\s+class="([^"]*)"(?:[^>]*?title="([^"]*)")?',
        body)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def test_calendar_cell_shows_locked_class_and_tooltip(logged_in_client,
                                                       test_store_id,
                                                       test_admin_id):
    """A day with locked_at set renders `<a class="... locked"
    title="Locked on ...">` so CSS + tooltip + screen readers all
    know the state."""
    from datetime import date, datetime
    from app import db, DailyReport
    ds = "2026-03-15"
    with logged_in_client.application.app_context():
        r = DailyReport(store_id=test_store_id,
                        report_date=date(2026, 3, 15),
                        taxable_sales=100.0,
                        locked_at=datetime(2026, 3, 16, 9, 0, 0),
                        locked_by=test_admin_id)
        db.session.add(r); db.session.commit()

    body = logged_in_client.get("/daily?year=2026&month=3").data.decode()
    classes, title = _calendar_cell_for(body, ds)
    assert classes is not None, "calendar cell for 2026-03-15 not found"
    assert "locked" in classes.split(), (
        f"expected 'locked' class on a locked day; got: {classes!r}")
    assert title and "Locked on" in title, (
        f"expected 'Locked on ...' tooltip; got: {title!r}")


def test_calendar_cell_unlocked_day_has_no_locked_class(logged_in_client,
                                                        test_store_id):
    """Regression guard: a report WITHOUT locked_at must not pick up
    the .locked class — the previous state would've treated every
    report equally."""
    from datetime import date
    from app import db, DailyReport
    ds = "2026-03-05"
    with logged_in_client.application.app_context():
        r = DailyReport(store_id=test_store_id,
                        report_date=date(2026, 3, 5),
                        taxable_sales=50.0)
        db.session.add(r); db.session.commit()

    body = logged_in_client.get("/daily?year=2026&month=3").data.decode()
    classes, _ = _calendar_cell_for(body, ds)
    assert classes is not None
    assert "locked" not in classes.split(), (
        f"unlocked day should not have the locked class; got: {classes!r}")
    assert "has-report" in classes.split()


def test_calendar_cell_no_report_has_no_locked_class(logged_in_client):
    """An empty day (no report at all) likewise must not be flagged
    locked. Needed because the template guard is `report and
    report.locked_at`, and we want the falsy-report path tested."""
    body = logged_in_client.get("/daily?year=2026&month=3").data.decode()
    classes, _ = _calendar_cell_for(body, "2026-03-20")
    assert classes is not None
    assert "locked" not in classes.split()


def test_calendar_legend_includes_locked_swatch(logged_in_client):
    """The calendar legend at the bottom of the page gains a 'Locked'
    entry with the matching padlock SVG so users know what the icon
    means."""
    body = logged_in_client.get("/daily").data.decode()
    assert "Locked" in body
    # Legend SVG uses the same rect shape as the cell icon, so we grep
    # for the pattern. There's at least one in the legend; more if any
    # day on the current month is locked. >=1 is the safe assertion.
    assert body.count('<rect x="3" y="11" width="18" height="11" rx="2"/>') >= 1
