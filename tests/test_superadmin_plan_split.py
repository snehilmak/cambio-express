"""Superadmin Overview tab splits BASIC and PRO counts into monthly
and yearly, and computes an amortized MRR. Guards the data the
redesigned cards depend on."""
import re


def _make_store(client, *, plan, billing_cycle, slug_suffix, name="Paid Shop"):
    from app import Store, db
    with client.application.app_context():
        s = Store(
            name=f"{name} {slug_suffix}",
            slug=f"paid-{slug_suffix}",
            plan=plan,
            billing_cycle=billing_cycle,
        )
        db.session.add(s)
        db.session.commit()
        return s.id


def _superadmin_client(client):
    """Log in as the seeded superadmin. Bypasses the real TOTP flow since
    the seeded superadmin has no totp_secret."""
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(username="superadmin", store_id=None).first()
        assert u is not None
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "superadmin"
    return client


def test_plan_counts_split_by_cycle(client):
    _superadmin_client(client)
    _make_store(client, plan="basic", billing_cycle="monthly", slug_suffix="bm1")
    _make_store(client, plan="basic", billing_cycle="monthly", slug_suffix="bm2")
    _make_store(client, plan="basic", billing_cycle="yearly",  slug_suffix="by1")
    _make_store(client, plan="pro",   billing_cycle="monthly", slug_suffix="pm1")
    _make_store(client, plan="pro",   billing_cycle="yearly",  slug_suffix="py1")
    _make_store(client, plan="pro",   billing_cycle="yearly",  slug_suffix="py2")

    resp = client.get("/superadmin/controls?tab=overview")
    assert resp.status_code == 200
    body = resp.data.decode()

    # Both BASIC and PRO cards render. Each has a .plan-split-row for
    # Monthly and one for Yearly → 4 data rows total (the substring
    # also matches .plan-split-rows in CSS/markup, so count the exact
    # `<div class="plan-split-row">` opening).
    assert body.count('<div class="plan-split-row">') == 4  # 2 per card × 2 cards

    # Grab the card contents to assert counts + MRR. Simple slice by
    # the label, then look for the two numeric tokens.
    def card_text(label):
        # From the card-label to the closing of plan-split-rows
        m = re.search(
            r'<div class="stat-label">\s*' + label +
            r'\s*</div>.*?</div>\s*</div>\s*</div>',
            body, re.S,
        )
        assert m, f"card not found: {label}"
        return m.group(0)

    basic = card_text("Basic")
    # Total count in headline: 2 monthly + 1 yearly = 3
    assert ">3<" in basic
    # Monthly row shows "2" and "$40/mo"; yearly row shows "1" and "$17/mo"
    # ($200/yr / 12 = $16.67 → rounded to 17).
    assert ">2<" in basic and "$40/mo" in basic
    assert ">1<" in basic and "$17/mo" in basic

    pro = card_text("Pro")
    # Total: 1 monthly + 2 yearly = 3
    assert ">3<" in pro
    # Monthly 1 × $30 = $30/mo; yearly 2 × $300 / 12 = $50/mo.
    assert ">1<" in pro and "$30/mo" in pro
    assert ">2<" in pro and "$50/mo" in pro


def test_estimated_mrr_is_amortized_total(client):
    """Est. MRR combines monthly (at rate) + yearly (at rate/12)."""
    _superadmin_client(client)
    _make_store(client, plan="basic", billing_cycle="monthly", slug_suffix="m1")  # $20
    _make_store(client, plan="pro",   billing_cycle="yearly",  slug_suffix="y1")  # $25
    # Expected MRR: 20 + 25 = 45.

    resp = client.get("/superadmin/controls?tab=overview")
    body = resp.data.decode()
    # The Est. MRR card shows "$45" as its stat-value.
    m = re.search(
        r'<div class="stat-label">\s*Est\. MRR\s*</div>\s*<div class="stat-value">\$(\d[\d,]*)</div>',
        body,
    )
    assert m, "MRR card not found"
    assert int(m.group(1).replace(",", "")) == 45


def test_superadmin_overview_still_lists_trial_and_inactive(client):
    """The other four tiles (total / trial / inactive / MRR) shouldn't
    regress when plan-split is added."""
    _superadmin_client(client)
    resp = client.get("/superadmin/controls?tab=overview")
    body = resp.data.decode()
    for label in ("Total stores", "Trial", "Basic", "Pro", "Inactive", "Est. MRR"):
        assert label in body, f"missing card label: {label}"
