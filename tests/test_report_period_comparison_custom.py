"""Custom Period Comparison — operator can pick an arbitrary second
period via `?compare_from=YYYY-MM-DD&compare_to=YYYY-MM-DD`. Both
must be set; if either is missing or invalid the report falls back
to the auto-prior same-length window."""
from datetime import date


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid; s["role"] = "admin"
        s["store_id"] = store_id


def _make_transfer(client, store_id, *, send_date, amount, fee=0.0,
                   federal_tax=0.0, company="Intermex",
                   confirm="X", status="Sent"):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name="S", recipient_name="R",
            country="MX", confirm_number=confirm,
            company=company, send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
        )
        db.session.add(t); db.session.commit()
        return t.id


def test_custom_compare_dates_override_auto_prior(client, test_store_id):
    """Pick a current month + a non-adjacent compare window and
    verify the comparison row reflects that window's data, not the
    immediately-prior month's."""
    _admin_login(client, test_store_id)
    # Current period: May 2026 — $1000 Sent.
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=1000, confirm="C1")
    # Auto-prior would be April 2026 — leave it empty.
    # Custom compare: March 2026 — $500.
    _make_transfer(client, test_store_id, send_date=date(2026, 3, 10),
                   amount=500, confirm="P1")
    # No compare params → auto-prior (April) → 0 in prior column.
    auto = client.get(
        "/reports/period-comparison?from=2026-05-01&to=2026-05-31"
    ).get_data(as_text=True)
    assert "$1,000.00" in auto
    assert "$500.00" not in auto  # March transfer not in auto-prior

    # With custom compare → March 2026 → $500 in prior column.
    custom = client.get(
        "/reports/period-comparison?from=2026-05-01&to=2026-05-31"
        "&compare_from=2026-03-01&compare_to=2026-03-31"
    ).get_data(as_text=True)
    assert "$1,000.00" in custom
    assert "$500.00" in custom


def test_custom_compare_period_label_shows_in_legend(client,
                                                      test_store_id):
    """The legend / column header on the comparison page should
    reflect the chosen compare window when it differs from the
    auto-prior."""
    _admin_login(client, test_store_id)
    body = client.get(
        "/reports/period-comparison?from=2026-05-01&to=2026-05-31"
        "&compare_from=2025-05-01&compare_to=2025-05-31"
    ).get_data(as_text=True)
    # Custom prior label uses chosen window.
    assert "May 01" in body and "May 31, 2025" in body


def test_custom_compare_inputs_render_in_form(client, test_store_id):
    """The Period Comparison page should expose Compare-from /
    Compare-to date inputs in the period filter form."""
    _admin_login(client, test_store_id)
    body = client.get("/reports/period-comparison").get_data(as_text=True)
    assert 'name="compare_from"' in body
    assert 'name="compare_to"' in body
    assert ">Compare from<" in body
    assert ">Compare to<" in body


def test_partial_compare_falls_back_to_auto_prior(client, test_store_id):
    """If only one of compare_from / compare_to is set, the report
    still uses the auto-prior — both must be set for custom."""
    _admin_login(client, test_store_id)
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=100, confirm="P1")
    _make_transfer(client, test_store_id, send_date=date(2026, 4, 10),
                   amount=200, confirm="P2")
    body = client.get(
        "/reports/period-comparison?from=2026-05-01&to=2026-05-31"
        "&compare_from=2025-01-01"  # no compare_to
    ).get_data(as_text=True)
    # Auto prior (April) used — $200 shows up.
    assert "$200.00" in body


def test_invalid_compare_dates_fall_back(client, test_store_id):
    """Garbage compare_from / compare_to → fall back to auto."""
    _admin_login(client, test_store_id)
    body = client.get(
        "/reports/period-comparison?from=2026-05-01&to=2026-05-31"
        "&compare_from=not-a-date&compare_to=also-not"
    ).get_data(as_text=True)
    # Renders without 500.
    assert "Period Comparison" in body


def test_compare_dates_swap_when_reversed(client, test_store_id):
    """If compare_from > compare_to, the data fn auto-swaps so the
    user doesn't get an empty window."""
    _admin_login(client, test_store_id)
    _make_transfer(client, test_store_id, send_date=date(2026, 3, 15),
                   amount=300, confirm="S1")
    body = client.get(
        "/reports/period-comparison?from=2026-05-01&to=2026-05-31"
        "&compare_from=2026-03-31&compare_to=2026-03-01"  # reversed
    ).get_data(as_text=True)
    assert "$300.00" in body


def test_custom_compare_csv_export_includes_period_columns(client,
                                                            test_store_id):
    """The CSV column headers use the dynamic period labels — verify
    the custom compare window shows up as a column header."""
    _admin_login(client, test_store_id)
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=100, confirm="X1")
    resp = client.get(
        "/reports/period-comparison.csv?from=2026-05-01&to=2026-05-31"
        "&compare_from=2025-05-01&compare_to=2025-05-31"
    )
    body = resp.get_data(as_text=True)
    # Custom compare window appears as a CSV column header.
    assert "May 01" in body and "May 31, 2025" in body
