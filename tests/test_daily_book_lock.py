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


def test_drops_new_returns_json_403_while_locked(logged_in_client):
    from app import DailyDrop
    ds = _today_ds()
    _lock(logged_in_client, ds)
    r = logged_in_client.post(
        f"/daily/{ds}/drops/new",
        data={"drop_time": "10:00", "amount": "50"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 403
    payload = json.loads(r.data)
    assert payload["ok"] is False
    assert "locked" in payload["error"].lower()
    with logged_in_client.application.app_context():
        assert DailyDrop.query.count() == 0, "no drop should have been created"


def test_drops_delete_rejected_while_locked(logged_in_client, test_store_id):
    """Drop delete must also be gated — you can't trim existing line items."""
    from app import DailyDrop, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        d = DailyDrop(store_id=test_store_id, report_date=date.today(),
                      drop_time=time(9, 0), amount=100.0)
        db.session.add(d); db.session.commit()
        drop_id = d.id
    _lock(logged_in_client, ds)
    r = logged_in_client.post(
        f"/daily/{ds}/drops/{drop_id}/delete",
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 403
    with logged_in_client.application.app_context():
        assert DailyDrop.query.filter_by(id=drop_id).first() is not None, \
            "drop must not have been deleted"


def test_check_deposit_new_rejected_while_locked(logged_in_client):
    from app import CheckDeposit
    ds = _today_ds()
    _lock(logged_in_client, ds)
    r = logged_in_client.post(
        f"/daily/{ds}/check-deposits/new",
        data={"deposit_time": "09:00", "amount": "250"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 403
    with logged_in_client.application.app_context():
        assert CheckDeposit.query.count() == 0


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
