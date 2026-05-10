"""Sidebar reorganization — admin sidebar consolidates to 2 sections
(top group + Books + Account) with New Transfer promoted to a topbar
button; superadmin sidebar collapses Monitoring into Configuration."""










def test_superadmin_sidebar_collapses_monitoring_into_configuration(client):
    """Superadmin sidebar now has Platform / Configuration / Reports
    (3 sections, was 4). System Status moved from a one-item
    Monitoring section into Configuration."""
    from app import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id
    with client.session_transaction() as s:
        s["user_id"] = sa_id; s["role"] = "superadmin"; s["store_id"] = None
    body = client.get("/superadmin/controls?tab=overview").get_data(as_text=True)
    # Monitoring header retired.
    assert ">Monitoring<" not in body
    # Three sections only.
    assert ">Platform<"      in body
    assert ">Configuration<" in body
    assert ">Reports<"       in body
    # System Status link still present (under Configuration now).
    assert "System Status" in body


