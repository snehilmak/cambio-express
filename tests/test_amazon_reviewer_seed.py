"""seed-amazon-reviewer CLI — provisions the comped test account
Amazon's reviewers use to verify the DineroBook TV Fire TV app.

The CLI is the single supported way to create that account; tests
pin the security-relevant invariants (employee role, comped plan,
addon active, sample data populated) so future refactors can't
accidentally drop the reviewer to "trial" or "admin"."""
import re

from app import (
    db, User, Store,
    TVDisplay, TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    store_has_addon,
)


REVIEWER_SLUG = "amazon-reviewer"
REVIEWER_USERNAME = "amazon-review@dinerobook.com"


def _run(client, *args):
    """Tiny helper — invoke the CLI and return the click Result."""
    runner = client.application.test_cli_runner()
    return runner.invoke(args=["seed-amazon-reviewer", *args])


# ── Provisioning ───────────────────────────────────────────────

def test_first_run_creates_store_user_and_sample_data(client):
    """A fresh DB has no reviewer state. One CLI invocation should
    produce a fully-paired-readiness account: store + employee +
    addon comped + Mexico/Guatemala sample rates."""
    result = _run(client)
    assert result.exit_code == 0, result.output
    assert "Amazon Reviewer account ready" in result.output

    with client.application.app_context():
        store = Store.query.filter_by(slug=REVIEWER_SLUG).first()
        assert store is not None
        # Plan + addon + active flag must all be set; the reviewer
        # would otherwise hit either the trial gate or the addon gate.
        assert store.plan == "basic"
        assert store_has_addon(store, "tv_display")
        assert store.is_active is True

        user = User.query.filter_by(
            store_id=store.id, username=REVIEWER_USERNAME).first()
        assert user is not None
        # *** Reviewer is an EMPLOYEE, not an admin. *** Less surface
        # area to misuse — they can pair Fire TVs and edit rates but
        # can't reach billing, team management, or store deletion.
        assert user.role == "employee"
        assert user.is_active is True

        # Display + the canonical 2-country sample matrix.
        display = TVDisplay.query.filter_by(store_id=store.id).first()
        assert display is not None
        countries = TVDisplayCountry.query.filter_by(
            display_id=display.id).all()
        assert {c.country_code for c in countries} == {"MX", "GT"}


def test_first_run_seeds_realistic_rate_grid(client):
    """The seeded grid has Mexico × 3 banks × 3 columns + Guatemala
    × 2 banks × 2 columns = 13 rate cells. Reviewer sees a realistic
    board, not an empty matrix."""
    _run(client)
    with client.application.app_context():
        rate_count = TVDisplayRate.query.count()
        assert rate_count == 13

        # Spot-check one number to guard against accidental zeroing.
        bancomer = TVDisplayPayoutBank.query.filter_by(
            bank_name="Bancomer").first()
        rate = TVDisplayRate.query.filter_by(
            bank_id=bancomer.id, mt_company="Maxi").first()
        assert rate.rate > 18.0


def test_password_is_printed_once_and_works(client):
    """The CLI prints the password to stdout exactly once. Anyone
    with shell access at run time captures it; we never persist it
    to the DB in plaintext."""
    result = _run(client)
    assert result.exit_code == 0
    m = re.search(r"Password:\s+(\S+)", result.output)
    assert m, f"Password line missing from: {result.output}"
    pw = m.group(1)
    assert len(pw) >= 12  # generated default is 16+ from token_urlsafe(12)

    with client.application.app_context():
        user = User.query.filter_by(username=REVIEWER_USERNAME).first()
        assert user.check_password(pw)
        assert not user.check_password(pw + "x"), \
            "wrong password must not authenticate (sanity)"


def test_login_url_includes_store_slug(client):
    """Reviewer copy/pastes the URL into Amazon's submission form;
    must end in /login/<slug>, not the generic /login."""
    result = _run(client)
    assert "/login/amazon-reviewer" in result.output


def test_explicit_password_is_accepted(client):
    custom = "ReviewerPassword2026!"
    result = _run(client, "--password", custom)
    assert result.exit_code == 0
    assert custom in result.output  # printed back so the operator can copy it
    with client.application.app_context():
        user = User.query.filter_by(username=REVIEWER_USERNAME).first()
        assert user.check_password(custom)


def test_short_password_is_rejected(client):
    result = _run(client, "--password", "short")
    assert result.exit_code != 0
    assert "at least 12 chars" in result.output


# ── Idempotency ────────────────────────────────────────────────

def test_re_run_rotates_password_and_keeps_state(client):
    """Operator pre-rotates the password before a fresh review
    submission. Same store, same user id, fresh password."""
    _run(client)
    with client.application.app_context():
        user_id_before = User.query.filter_by(
            username=REVIEWER_USERNAME).first().id
        store_id_before = Store.query.filter_by(slug=REVIEWER_SLUG).first().id

    result = _run(client)
    assert result.exit_code == 0
    new_pw = re.search(r"Password:\s+(\S+)", result.output).group(1)

    with client.application.app_context():
        user = User.query.filter_by(username=REVIEWER_USERNAME).first()
        store = Store.query.filter_by(slug=REVIEWER_SLUG).first()
        # Same row, not a duplicate.
        assert user.id == user_id_before
        assert store.id == store_id_before
        # Fresh password works.
        assert user.check_password(new_pw)


def test_re_run_re_comps_addon_if_yanked(client):
    """If superadmin manually toggles the reviewer addon off (or
    Stripe webhook expired the plan during a between-review window),
    re-running the CLI restores everything."""
    _run(client)
    with client.application.app_context():
        s = Store.query.filter_by(slug=REVIEWER_SLUG).first()
        s.plan = "trial"; s.addons = ""; db.session.commit()
        assert not store_has_addon(s, "tv_display")

    _run(client)
    with client.application.app_context():
        s = Store.query.filter_by(slug=REVIEWER_SLUG).first()
        assert s.plan == "basic"
        assert store_has_addon(s, "tv_display")


def test_re_run_resets_employee_role_if_promoted(client):
    """Defense in depth — if the reviewer account ever gets
    accidentally promoted to admin (via superadmin tools), the next
    seed run reverts to employee. Reviewers should never have admin
    access to a store; they're testing the Fire TV pair flow, not
    poking at billing."""
    _run(client)
    with client.application.app_context():
        u = User.query.filter_by(username=REVIEWER_USERNAME).first()
        u.role = "admin"; db.session.commit()

    _run(client)
    with client.application.app_context():
        u = User.query.filter_by(username=REVIEWER_USERNAME).first()
        assert u.role == "employee"


def test_re_run_default_reseeds_sample_data(client):
    """Default behavior wipes and re-seeds the sample matrix so the
    reviewer always sees the same canonical board, even if a prior
    reviewer (or test) edited it. Counter case below tests --keep-data."""
    _run(client)
    with client.application.app_context():
        # Mutate the data: rename a bank.
        bank = TVDisplayPayoutBank.query.filter_by(
            bank_name="Bancomer").first()
        bank.bank_name = "Reviewer Test Edit"
        db.session.commit()

    _run(client)
    with client.application.app_context():
        # Bancomer is back; the edit was wiped.
        assert TVDisplayPayoutBank.query.filter_by(
            bank_name="Bancomer").first() is not None
        assert TVDisplayPayoutBank.query.filter_by(
            bank_name="Reviewer Test Edit").first() is None


def test_keep_data_flag_preserves_existing_grid(client):
    """--keep-data is the safety hatch for an operator who wants to
    rotate the password without touching the rate matrix (e.g. the
    reviewer is mid-test on a specific rate set)."""
    _run(client)
    with client.application.app_context():
        bank = TVDisplayPayoutBank.query.filter_by(
            bank_name="Bancomer").first()
        bank.bank_name = "Operator Live Edit"
        db.session.commit()

    result = _run(client, "--keep-data")
    assert result.exit_code == 0
    assert "Sample data: untouched" in result.output

    with client.application.app_context():
        # Edit survived.
        assert TVDisplayPayoutBank.query.filter_by(
            bank_name="Operator Live Edit").first() is not None


# ── Pair-code flow against the seeded account ──────────────────

def test_seeded_account_can_actually_claim_a_pair_code(client):
    """End-to-end: the whole point of this CLI. Sign in as the
    reviewer, simulate a Fire TV calling /api/tv-pair/init, then
    have the reviewer claim the code via /tv-display/claim. If this
    test fails, the reviewer can't pair the test Fire TV and our
    Amazon submission gets rejected."""
    _run(client)
    with client.application.app_context():
        user = User.query.filter_by(username=REVIEWER_USERNAME).first()
        store = Store.query.filter_by(slug=REVIEWER_SLUG).first()
        uid, sid = user.id, store.id

    # 1. Simulate the Fire TV opening the app — public, no auth.
    body = client.post("/api/tv-pair/init", json={}).get_json()
    assert "code" in body and "device_token" in body

    # 2. Sign in as the reviewer (role employee, store_id pinned).
    c = client.application.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "employee"
        sess["store_id"] = sid

    # 3. Reviewer types the code on /tv-display.
    resp = c.post("/tv-display/claim", data={"code": body["code"]})
    assert resp.status_code == 302, \
        f"reviewer couldn't claim pair code: {resp.status_code}"

    # 4. The Fire TV's next /status poll flips to "claimed".
    poll = client.get("/api/tv-pair/status",
                       query_string={"token": body["device_token"]}).get_json()
    assert poll["status"] == "claimed"
    assert "display_url" in poll
