# Landing Page + Self-Service Signup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public marketing landing page, self-service signup with 7-day free trial, trial enforcement with grace-period banners, and Stripe Checkout for plan upgrades — all in the existing Flask/Jinja2 codebase.

**Architecture:** All server logic lives in `app.py`. The landing and signup pages are standalone HTML templates (no sidebar). Trial enforcement is handled by a `get_trial_status()` helper, a `@app.context_processor` for banner injection, and a guard inside `login_required`. Stripe Checkout (hosted) handles billing; a webhook handler updates `store.plan` on payment.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, stripe==9.12.0, python-slugify==8.0.4, pytest==8.2.0, pytest-flask==1.3.0

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add stripe, python-slugify, pytest, pytest-flask |
| `app.py` | Modify | Models, routes, helpers — all server logic |
| `templates/base.html` | Modify | Add trial status banners |
| `templates/landing.html` | Create | Standalone public landing page |
| `templates/signup.html` | Create | Standalone self-service signup form |
| `templates/subscribe.html` | Create | Plan selection page (extends base.html) |
| `templates/subscribe_success.html` | Create | Post-payment confirmation (extends base.html) |
| `tests/__init__.py` | Create | Empty package marker |
| `tests/conftest.py` | Create | pytest fixtures and test DB setup |
| `tests/test_landing.py` | Create | Landing page and login route tests |
| `tests/test_signup.py` | Create | Signup flow tests |
| `tests/test_trial.py` | Create | Trial status helper tests |
| `tests/test_subscribe.py` | Create | Subscribe, checkout, and webhook tests |

---

## Task 1: Dependencies and Test Infrastructure

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_landing.py`

- [ ] **Step 1: Update requirements.txt**

Replace the full file contents with:

```
flask==3.0.3
flask-sqlalchemy==3.1.1
werkzeug==3.0.3
requests==2.32.3
gunicorn==22.0.0
psycopg2-binary==2.9.9
stripe==9.12.0
python-slugify==8.0.4
pytest==8.2.0
pytest-flask==1.3.0
```

- [ ] **Step 2: Install new packages**

```bash
pip install stripe==9.12.0 python-slugify==8.0.4 pytest==8.2.0 pytest-flask==1.3.0
```

Expected: installs without errors.

- [ ] **Step 3: Create tests/__init__.py**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 4: Create tests/conftest.py**

```python
import os
# Set test database BEFORE importing app so SQLAlchemy uses it
os.environ["DATABASE_URL"] = "sqlite:///test_cambio.db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake_key")
os.environ.setdefault("STRIPE_BASIC_PRICE_ID", "price_basic_test")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

import pytest
from datetime import datetime, timedelta
from app import app as flask_app, db


def seed_test_data():
    from app import User, Store
    if not User.query.filter_by(username="superadmin", store_id=None).first():
        sa = User(username="superadmin", full_name="Platform Owner",
                  role="superadmin", store_id=None)
        sa.set_password("super2025!")
        db.session.add(sa)
    if not Store.query.filter_by(slug="test-store").first():
        s = Store(name="Test Store", slug="test-store",
                  email="admin@test.com", plan="trial",
                  trial_ends_at=datetime.utcnow() + timedelta(days=7),
                  grace_ends_at=datetime.utcnow() + timedelta(days=11))
        db.session.add(s)
        db.session.flush()
        a = User(store_id=s.id, username="admin@test.com",
                 full_name="Test Admin", role="admin")
        a.set_password("testpass123!")
        db.session.add(a)
    db.session.commit()


@pytest.fixture(autouse=True)
def clean_db():
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        seed_test_data()
    yield
    with flask_app.app_context():
        db.session.remove()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture
def logged_in_client():
    """Client pre-authenticated as the test store admin."""
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="admin@test.com").first()
        uid, sid = u.id, u.store_id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid
    return c
```

- [ ] **Step 5: Write smoke test in tests/test_landing.py**

```python
def test_app_loads(client):
    """Smoke test: pytest can import app and make a request."""
    resp = client.get("/login")
    assert resp.status_code in (200, 302, 404)
```

- [ ] **Step 6: Run tests**

```bash
cd "C:/Users/snehi/Desktop/Test Claude/DineroSync"
pytest tests/test_landing.py -v
```

Expected: 1 test collected, 1 passed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt tests/
git commit -m "feat: add stripe/slugify deps and pytest test infrastructure"
```

---

## Task 2: Store Model Changes + New Imports

**Files:**
- Modify: `app.py` (imports block + Store model)

- [ ] **Step 1: Write failing test — add to tests/test_landing.py**

```python
def test_store_has_trial_columns(client):
    """Store model must have trial_ends_at and grace_ends_at columns."""
    with client.application.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert hasattr(s, "trial_ends_at")
        assert hasattr(s, "grace_ends_at")
        assert s.trial_ends_at is not None
        assert s.grace_ends_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_landing.py::test_store_has_trial_columns -v
```

Expected: FAILED — `Store` has no attribute `trial_ends_at`

- [ ] **Step 3: Update imports at top of app.py**

The current line 4 reads:
```python
from datetime import datetime, date
```
Change it to:
```python
from datetime import datetime, date, timedelta
```

Add these two lines immediately after the existing imports block (after `import requests, base64, os, calendar, logging`):

```python
import stripe
from slugify import slugify
```

After `db = SQLAlchemy(app)` (line 19), add:

```python
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
```

- [ ] **Step 4: Add columns to Store model**

In the `Store` model, after the `created_at` column (line 34), add:

```python
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    grace_ends_at = db.Column(db.DateTime, nullable=True)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_landing.py::test_store_has_trial_columns -v
```

Expected: PASSED

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: add trial_ends_at/grace_ends_at to Store model + stripe/slugify imports"
```

---

## Task 3: Move Login from / to /login

**Files:**
- Modify: `app.py` (login route URL + stub landing route)

- [ ] **Step 1: Write failing tests — add to tests/test_landing.py**

```python
def test_login_at_new_route(client):
    resp = client.get("/login")
    assert resp.status_code == 200

def test_root_is_no_longer_login(client):
    resp = client.get("/")
    assert resp.status_code in (200, 302)
    # If 200, it must NOT be the login page — it must be the landing page stub
    if resp.status_code == 200:
        # The login form has a username field; the stub does not
        assert b'name="username"' not in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_landing.py::test_login_at_new_route tests/test_landing.py::test_root_is_no_longer_login -v
```

Expected: both FAILED

- [ ] **Step 3: Change the login route URL in app.py**

Find (around line 319):
```python
@app.route("/",methods=["GET","POST"])
def login():
```
Change to:
```python
@app.route("/login", methods=["GET", "POST"])
def login():
```

- [ ] **Step 4: Add stub landing route above login in app.py**

Directly above the login route, add:

```python
@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return "Landing page coming soon", 200
```

- [ ] **Step 5: Check login.html form action**

```bash
grep -n "action=" templates/login.html
```

If you see `action="/"`, change it to `action="/login"`. If it uses `action=""` or no action attribute, leave it as-is (the browser will POST to the current URL which is now `/login`).

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_landing.py -v
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add app.py templates/login.html
git commit -m "feat: move login to /login, add stub landing at /"
```

---

## Task 4: get_trial_status Helper

**Files:**
- Modify: `app.py` (add helper after superadmin_required decorator)
- Create: `tests/test_trial.py`

- [ ] **Step 1: Write failing tests in tests/test_trial.py**

```python
from datetime import datetime, timedelta


def _store(plan="trial", trial_ends_at=None, grace_ends_at=None):
    class S:
        pass
    s = S()
    s.plan = plan
    s.trial_ends_at = trial_ends_at
    s.grace_ends_at = grace_ends_at
    return s


def test_none_store_is_exempt():
    from app import get_trial_status
    assert get_trial_status(None) == "exempt"

def test_no_trial_dates_is_exempt():
    from app import get_trial_status
    assert get_trial_status(_store(plan="trial", trial_ends_at=None)) == "exempt"

def test_basic_plan_is_exempt():
    from app import get_trial_status
    assert get_trial_status(_store(plan="basic",
        trial_ends_at=datetime.utcnow() - timedelta(days=1),
        grace_ends_at=datetime.utcnow() + timedelta(days=3))) == "exempt"

def test_pro_plan_is_exempt():
    from app import get_trial_status
    assert get_trial_status(_store(plan="pro",
        trial_ends_at=datetime.utcnow() - timedelta(days=1),
        grace_ends_at=datetime.utcnow() + timedelta(days=3))) == "exempt"

def test_inactive_plan_is_expired():
    from app import get_trial_status
    assert get_trial_status(_store(plan="inactive")) == "expired"

def test_active_trial_with_days_remaining():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() + timedelta(days=7),
               grace_ends_at=datetime.utcnow() + timedelta(days=11))
    assert get_trial_status(s) == "active"

def test_expiring_soon_within_3_days():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() + timedelta(hours=36),
               grace_ends_at=datetime.utcnow() + timedelta(days=4))
    assert get_trial_status(s) == "expiring_soon"

def test_grace_after_trial_end():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() - timedelta(hours=12),
               grace_ends_at=datetime.utcnow() + timedelta(days=3))
    assert get_trial_status(s) == "grace"

def test_expired_after_grace_end():
    from app import get_trial_status
    s = _store(plan="trial",
               trial_ends_at=datetime.utcnow() - timedelta(days=5),
               grace_ends_at=datetime.utcnow() - timedelta(days=1))
    assert get_trial_status(s) == "expired"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_trial.py -v
```

Expected: all FAILED — `cannot import name 'get_trial_status'`

- [ ] **Step 3: Add get_trial_status to app.py**

Add this block immediately after the `superadmin_required` decorator (around line 258), before the SimpleFIN section:

```python
# ── Trial Status ─────────────────────────────────────────────
def get_trial_status(store):
    """Return trial status string for the given store.

    Returns: "exempt" | "active" | "expiring_soon" | "grace" | "expired"
    """
    if store is None:
        return "exempt"
    if store.plan in ("basic", "pro"):
        return "exempt"
    if store.plan == "inactive":
        return "expired"
    if store.trial_ends_at is None:
        return "exempt"
    now = datetime.utcnow()
    if now >= store.grace_ends_at:
        return "expired"
    if now >= store.trial_ends_at:
        return "grace"
    if now >= store.trial_ends_at - timedelta(days=3):
        return "expiring_soon"
    return "active"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_trial.py -v
```

Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_trial.py
git commit -m "feat: get_trial_status helper with full test coverage"
```

---

## Task 5: Trial Enforcement — login_required + Context Processor + Banners

**Files:**
- Modify: `app.py` (login_required decorator + new context processor)
- Modify: `templates/base.html` (add banner HTML)

- [ ] **Step 1: Write failing tests — append to tests/test_trial.py**

```python
def test_expired_store_redirected_to_subscribe(client):
    from app import db, Store, User
    with client.application.app_context():
        s = Store(name="Expired Co", slug="expired-co",
                  email="expired@test.com", plan="trial",
                  trial_ends_at=datetime.utcnow() - timedelta(days=5),
                  grace_ends_at=datetime.utcnow() - timedelta(days=1))
        db.session.add(s)
        db.session.flush()
        u = User(store_id=s.id, username="expired@test.com",
                 full_name="Expired Admin", role="admin")
        u.set_password("testpass123!")
        db.session.add(u)
        db.session.commit()
        uid, sid = u.id, s.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid

    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in resp.headers["Location"]


def test_active_trial_reaches_dashboard(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200


def test_subscribe_is_accessible_when_expired(client):
    """Expired stores must be able to reach /subscribe (not infinite redirect)."""
    from app import db, Store, User
    with client.application.app_context():
        s = Store(name="Exp2 Co", slug="exp2-co",
                  email="exp2@test.com", plan="trial",
                  trial_ends_at=datetime.utcnow() - timedelta(days=5),
                  grace_ends_at=datetime.utcnow() - timedelta(days=1))
        db.session.add(s)
        db.session.flush()
        u = User(store_id=s.id, username="exp2@test.com",
                 full_name="Exp2 Admin", role="admin")
        u.set_password("testpass123!")
        db.session.add(u)
        db.session.commit()
        uid, sid = u.id, s.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid

    resp = client.get("/subscribe")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_trial.py::test_expired_store_redirected_to_subscribe tests/test_trial.py::test_active_trial_reaches_dashboard tests/test_trial.py::test_subscribe_is_accessible_when_expired -v
```

Expected: FAILED

- [ ] **Step 3: Add _TRIAL_EXEMPT set and update login_required in app.py**

Add this line immediately before the `login_required` function:

```python
_TRIAL_EXEMPT = {"subscribe", "subscribe_checkout", "subscribe_success", "logout"}
```

Replace the existing `login_required` function with:

```python
def login_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = current_user()
        if user and user.role != "superadmin" and f.__name__ not in _TRIAL_EXEMPT:
            store = current_store()
            if store and get_trial_status(store) == "expired":
                return redirect(url_for("subscribe"))
        return f(*a, **k)
    return d
```

- [ ] **Step 4: Add context processor to app.py**

Add this block immediately after the `get_trial_status` function:

```python
@app.context_processor
def inject_trial_context():
    """Inject trial_status and trial_days_left into every template."""
    user = current_user()
    if not user:
        return {"trial_status": "exempt", "trial_days_left": 0}
    if user.role == "superadmin":
        return {"trial_status": "exempt", "trial_days_left": 0}
    store = current_store()
    status = get_trial_status(store)
    days_left = 0
    if store and store.trial_ends_at:
        delta = store.trial_ends_at - datetime.utcnow()
        days_left = max(0, delta.days)
    return {"trial_status": status, "trial_days_left": days_left}
```

- [ ] **Step 5: Add banners to templates/base.html**

Find this line in base.html (around line 304):
```html
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
```

Replace it with:
```html
    <div class="content">
      {% if trial_status == "expiring_soon" %}
      <div style="background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:12px 18px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;">
        <span style="color:#713f12;font-size:13.5px;font-weight:500;">⏳ Your free trial ends in <strong>{{ trial_days_left }} day{{ 's' if trial_days_left != 1 else '' }}</strong>.</span>
        <a href="{{ url_for('subscribe') }}" style="background:#ca8a04;color:white;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;">Choose a Plan →</a>
      </div>
      {% elif trial_status == "grace" %}
      <div style="background:#fee2e2;border:1px solid #fca5a5;border-radius:8px;padding:12px 18px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;">
        <span style="color:#7f1d1d;font-size:13.5px;font-weight:500;">🔴 Your free trial has ended. Upgrade now to keep full access.</span>
        <a href="{{ url_for('subscribe') }}" style="background:#dc2626;color:white;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none;">Upgrade Now →</a>
      </div>
      {% endif %}
      {% with messages = get_flashed_messages(with_categories=true) %}
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add app.py templates/base.html
git commit -m "feat: trial enforcement in login_required + banners in base.html"
```

---

## Task 6: Landing Page

**Files:**
- Modify: `app.py` (replace stub landing route)
- Create: `templates/landing.html`

- [ ] **Step 1: Write failing tests — add to tests/test_landing.py**

```python
def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200

def test_landing_has_headline(client):
    resp = client.get("/")
    assert b"Crystal Clear" in resp.data

def test_landing_has_pricing(client):
    resp = client.get("/")
    assert b"$20" in resp.data
    assert b"$30" in resp.data

def test_landing_has_signup_link(client):
    resp = client.get("/")
    assert b"/signup" in resp.data

def test_landing_redirects_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_landing.py -v
```

Expected: landing tests FAILED (stub returns plain text)

- [ ] **Step 3: Replace stub landing route in app.py**

Find the stub:
```python
@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return "Landing page coming soon", 200
```
Replace with:
```python
@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")
```

- [ ] **Step 4: Create templates/landing.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cambio Express — MSB Manager</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--navy:#0f1f3d;--blue:#1a4080;--mid:#2a5caa;--gold:#c9973a;--gold2:#f0c060;--cream:#faf7f2;--white:#ffffff;--gray1:#f5f5f7;--gray2:#e8e8ec;--gray3:#b0b4c0;--gray4:#6b7280;--dark:#1a1a2e}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--dark)}
nav{position:sticky;top:0;z-index:100;background:var(--navy);padding:0 48px;height:64px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.08)}
.nav-brand{font-family:'DM Serif Display',serif;color:var(--gold2);font-size:20px;text-decoration:none;display:flex;flex-direction:column;line-height:1.1}
.nav-brand span{font-family:'DM Sans',sans-serif;font-size:10px;color:rgba(255,255,255,0.4);letter-spacing:1.5px;text-transform:uppercase;font-weight:400}
.nav-links{display:flex;align-items:center;gap:28px}
.nav-links a{color:rgba(255,255,255,0.65);text-decoration:none;font-size:13.5px;transition:color .15s}
.nav-links a:hover{color:var(--white)}
.nav-links .cta{background:var(--gold);color:var(--white);padding:8px 20px;border-radius:8px;font-weight:600;font-size:13px}
.nav-links .cta:hover{background:var(--gold2);color:var(--navy)}
.hero{background:linear-gradient(135deg,var(--navy) 0%,var(--mid) 100%);padding:100px 48px;text-align:center;color:white}
.hero-eyebrow{font-size:11px;letter-spacing:2.5px;color:var(--gold2);text-transform:uppercase;margin-bottom:20px;font-weight:500}
.hero h1{font-family:'DM Serif Display',serif;font-size:54px;line-height:1.15;margin-bottom:22px}
.hero p{font-size:18px;color:rgba(255,255,255,0.72);max-width:600px;margin:0 auto 38px;line-height:1.65}
.hero-ctas{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
.btn-gold{background:var(--gold);color:white;padding:14px 32px;border-radius:10px;font-size:15px;font-weight:600;text-decoration:none;transition:background .15s}
.btn-gold:hover{background:var(--gold2);color:var(--navy)}
.btn-outline{background:transparent;color:white;border:1.5px solid rgba(255,255,255,0.4);padding:14px 28px;border-radius:10px;font-size:15px;font-weight:500;text-decoration:none;transition:all .15s}
.btn-outline:hover{border-color:white;background:rgba(255,255,255,0.06)}
.hero-note{margin-top:18px;font-size:12px;color:rgba(255,255,255,0.38);letter-spacing:.4px}
.features{padding:88px 48px;background:var(--cream)}
.section-eyebrow{text-align:center;font-size:11px;font-weight:600;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.section-heading{text-align:center;font-family:'DM Serif Display',serif;font-size:36px;color:var(--navy);margin-bottom:52px}
.features-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;max-width:1040px;margin:0 auto}
.feature-card{background:var(--white);border-radius:12px;border:1px solid var(--gray2);padding:28px 24px}
.feature-icon{font-size:30px;margin-bottom:14px}
.feature-card h3{font-size:15px;font-weight:600;color:var(--navy);margin-bottom:8px}
.feature-card p{font-size:13.5px;color:var(--gray4);line-height:1.65}
.pro-badge{display:inline-block;background:var(--navy);color:var(--gold2);font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;margin-left:6px;vertical-align:middle}
.pricing{padding:88px 48px;background:var(--white)}
.pricing-grid{display:grid;grid-template-columns:1fr 1.15fr 1fr;gap:20px;max-width:920px;margin:0 auto;align-items:start}
.plan{background:var(--gray1);border:1.5px solid var(--gray2);border-radius:14px;padding:32px 28px;position:relative}
.plan.featured{background:var(--navy);border-color:var(--gold)}
.plan-badge{position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:var(--gold);color:white;font-size:10px;font-weight:700;letter-spacing:1px;padding:3px 14px;border-radius:999px;white-space:nowrap}
.plan-name{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--gray4);margin-bottom:8px}
.plan.featured .plan-name{color:var(--gold2)}
.plan-price{font-family:'DM Serif Display',serif;font-size:42px;color:var(--navy);line-height:1;margin-bottom:4px}
.plan.featured .plan-price{color:white}
.plan-period{font-size:13px;color:var(--gray4);margin-bottom:22px}
.plan.featured .plan-period{color:rgba(255,255,255,0.5)}
.plan-features{list-style:none;margin-bottom:28px}
.plan-features li{font-size:13.5px;padding:7px 0;border-bottom:1px solid var(--gray2);color:var(--dark)}
.plan.featured .plan-features li{color:rgba(255,255,255,0.85);border-bottom-color:rgba(255,255,255,0.1)}
.plan-features li.no{color:var(--gray3)}
.plan.featured .plan-features li.no{color:rgba(255,255,255,0.25)}
.plan-btn{display:block;text-align:center;padding:12px;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none;transition:all .15s}
.btn-navy{background:var(--navy);color:white}
.btn-navy:hover{background:var(--mid)}
.btn-border{border:1.5px solid var(--blue);color:var(--blue);background:transparent}
.btn-border:hover{background:var(--blue);color:white}
.btn-gold2{background:var(--gold);color:white}
.btn-gold2:hover{background:var(--gold2);color:var(--navy)}
footer{background:var(--navy);padding:32px 48px;display:flex;align-items:center;justify-content:space-between}
footer p{color:rgba(255,255,255,0.35);font-size:13px}
footer a{color:rgba(255,255,255,0.45);text-decoration:none;font-size:13px;transition:color .15s}
footer a:hover{color:var(--gold2)}
@media(max-width:768px){.features-grid,.pricing-grid{grid-template-columns:1fr}.hero h1{font-size:36px}.hero,.features,.pricing{padding:60px 24px}nav{padding:0 20px}}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-brand">Cambio Express<span>MSB Manager</span></a>
  <div class="nav-links">
    <a href="#features">Features</a>
    <a href="#pricing">Pricing</a>
    <a href="/login">Login</a>
    <a href="/signup" class="cta">Start Free Trial</a>
  </div>
</nav>

<section class="hero">
  <div class="hero-eyebrow">Built for MSB Store Owners</div>
  <h1>Your Business.<br>Crystal Clear.</h1>
  <p>Stop managing your store on paper or spreadsheets. Cambio Express gives you real-time visibility into transfers, daily cash, and monthly profits.</p>
  <div class="hero-ctas">
    <a href="/signup" class="btn-gold">Try Free for 7 Days</a>
    <a href="#features" class="btn-outline">Learn More ↓</a>
  </div>
  <p class="hero-note">No credit card required &middot; Cancel anytime</p>
</section>

<section class="features" id="features">
  <div class="section-eyebrow">What's Included</div>
  <div class="section-heading">Everything Your Store Needs</div>
  <div class="features-grid">
    <div class="feature-card">
      <div class="feature-icon">📅</div>
      <h3>Daily Books</h3>
      <p>Track cash in/out, sales, money orders, and check cashing every day. Your daily record, always organized.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">💸</div>
      <h3>Money Transfers</h3>
      <p>Log Intermex, Maxi, and Barri transfers with full sender and recipient detail. Find any transfer instantly.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">📦</div>
      <h3>ACH Batches</h3>
      <p>Reconcile ACH deposits against your transfer totals. Spot variances before they become problems.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">📊</div>
      <h3>Monthly P&amp;L</h3>
      <p>Auto-populated profit &amp; loss from your daily reports. Know exactly where your money went each month.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🏦</div>
      <h3>Bank Sync <span class="pro-badge">Pro</span></h3>
      <p>Connect via SimpleFIN to see live bank balances alongside your books. No more tab-switching.</p>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🔍</div>
      <h3>Reports</h3>
      <p>Filter transfers by date, company, and status. Review any time window with a click.</p>
    </div>
  </div>
</section>

<section class="pricing" id="pricing">
  <div class="section-eyebrow">Simple Pricing</div>
  <div class="section-heading">Start Free. Upgrade When Ready.</div>
  <div class="pricing-grid">

    <div class="plan">
      <div class="plan-name">Basic</div>
      <div class="plan-price">$20</div>
      <div class="plan-period">per store / month</div>
      <ul class="plan-features">
        <li>✓ Daily books &amp; cash tracking</li>
        <li>✓ Money transfer logging</li>
        <li>✓ ACH batch reconciliation</li>
        <li>✓ Monthly P&amp;L reports</li>
        <li class="no">✗ Bank sync (Pro only)</li>
      </ul>
      <a href="/signup?plan=basic" class="plan-btn btn-border">Get Started</a>
    </div>

    <div class="plan featured">
      <div class="plan-badge">MOST POPULAR</div>
      <div class="plan-name">Pro</div>
      <div class="plan-price">$30</div>
      <div class="plan-period">per store / month</div>
      <ul class="plan-features">
        <li>✓ Everything in Basic</li>
        <li>✓ SimpleFIN bank sync</li>
        <li>✓ Live balance visibility</li>
        <li>✓ Multi-store (coming soon)</li>
      </ul>
      <a href="/signup?plan=pro" class="plan-btn btn-gold2">Get Pro</a>
    </div>

    <div class="plan">
      <div class="plan-name">Free Trial</div>
      <div class="plan-price">$0</div>
      <div class="plan-period">7 days &middot; full Pro access</div>
      <ul class="plan-features">
        <li>✓ All Pro features</li>
        <li>✓ No credit card needed</li>
        <li>✓ Instant access</li>
      </ul>
      <a href="/signup" class="plan-btn btn-navy">Start Free</a>
    </div>

  </div>
</section>

<footer>
  <p>&copy; 2026 Cambio Express. All rights reserved.</p>
  <a href="/login">Sign In →</a>
</footer>

</body>
</html>
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_landing.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add app.py templates/landing.html
git commit -m "feat: public landing page at / with hero, features, and pricing"
```

---

## Task 7: Signup Flow

**Files:**
- Modify: `app.py` (add /signup route)
- Create: `templates/signup.html`
- Create: `tests/test_signup.py`

- [ ] **Step 1: Write failing tests in tests/test_signup.py**

```python
def test_signup_page_loads(client):
    resp = client.get("/signup")
    assert resp.status_code == 200
    assert b"Store Name" in resp.data or b"store_name" in resp.data

def test_signup_redirects_to_dashboard(client):
    resp = client.post("/signup", data={
        "store_name": "New Test Store",
        "email": "newowner@example.com",
        "password": "securepass1!",
        "phone": "555-1234"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]

def test_signup_creates_store_in_db(client):
    client.post("/signup", data={
        "store_name": "DB Check Store",
        "email": "dbcheck@example.com",
        "password": "securepass1!",
        "phone": ""
    })
    with client.application.app_context():
        from app import Store, User
        s = Store.query.filter_by(email="dbcheck@example.com").first()
        assert s is not None
        assert s.plan == "trial"
        assert s.trial_ends_at is not None
        assert s.grace_ends_at is not None
        u = User.query.filter_by(username="dbcheck@example.com").first()
        assert u is not None
        assert u.role == "admin"
        assert u.store_id == s.id

def test_signup_rejects_duplicate_email(client):
    data = {"store_name": "First", "email": "dup@example.com",
            "password": "securepass1!", "phone": ""}
    client.post("/signup", data=data)
    resp = client.post("/signup", data={**data, "store_name": "Second"})
    assert resp.status_code == 200
    assert b"already exists" in resp.data.lower()

def test_signup_rejects_short_password(client):
    resp = client.post("/signup", data={
        "store_name": "Short Pass", "email": "short@example.com",
        "password": "abc", "phone": ""
    })
    assert resp.status_code == 200
    assert b"8" in resp.data

def test_signup_rejects_missing_store_name(client):
    resp = client.post("/signup", data={
        "store_name": "", "email": "noname@example.com",
        "password": "securepass1!", "phone": ""
    })
    assert resp.status_code == 200
    assert b"required" in resp.data.lower() or b"store name" in resp.data.lower()
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_signup.py -v
```

Expected: all FAILED — no /signup route

- [ ] **Step 3: Add /signup route to app.py**

Add this route after the `/login` route:

```python
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    errors = {}
    form = {}
    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        form = {"store_name": store_name, "email": email, "phone": phone}

        if not store_name:
            errors["store_name"] = "Store name is required."
        if not email:
            errors["email"] = "Email is required."
        if not password:
            errors["password"] = "Password is required."
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."

        if not errors:
            existing = User.query.filter_by(username=email).filter(
                User.store_id != None).first()
            if existing:
                errors["email"] = "An account with this email already exists."

        if not errors:
            slug_base = slugify(store_name)
            slug = slug_base
            counter = 1
            while Store.query.filter_by(slug=slug).first():
                slug = f"{slug_base}-{counter}"
                counter += 1
            s = Store(name=store_name, slug=slug, email=email,
                      phone=phone, plan="trial")
            db.session.add(s)
            db.session.flush()
            s.trial_ends_at = datetime.utcnow() + timedelta(days=7)
            s.grace_ends_at = s.trial_ends_at + timedelta(days=4)
            u = User(store_id=s.id, username=email,
                     full_name=store_name, role="admin")
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"] = u.id
            session["role"] = u.role
            session["store_id"] = s.id
            flash("Welcome! Your 7-day free trial has started.", "success")
            return redirect(url_for("dashboard"))

    return render_template("signup.html", errors=errors, form=form)
```

- [ ] **Step 4: Create templates/signup.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Create Account — Cambio Express</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{--navy:#0f1f3d;--blue:#1a4080;--gold:#c9973a;--gold2:#f0c060;--cream:#faf7f2;--white:#ffffff;--gray2:#e8e8ec;--gray4:#6b7280;--dark:#1a1a2e;--red:#dc2626;--sky:#3b82f6}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans',sans-serif;background:var(--cream);min-height:100vh;display:flex;flex-direction:column}
nav{background:var(--navy);padding:0 40px;height:60px;display:flex;align-items:center;justify-content:space-between}
.nav-brand{font-family:'DM Serif Display',serif;color:var(--gold2);font-size:18px;text-decoration:none}
.nav-login{color:rgba(255,255,255,0.55);font-size:13px;text-decoration:none}
.nav-login:hover{color:white}
.page{flex:1;display:flex;align-items:center;justify-content:center;padding:48px 24px}
.card{background:var(--white);border-radius:16px;border:1px solid var(--gray2);padding:40px 44px;width:100%;max-width:460px;box-shadow:0 4px 24px rgba(0,0,0,0.06)}
.trial-badge{display:inline-flex;align-items:center;gap:6px;background:#dcfce7;color:#15803d;border-radius:999px;padding:4px 12px;font-size:12px;font-weight:600;margin-bottom:22px}
.card-title{font-family:'DM Serif Display',serif;font-size:26px;color:var(--navy);margin-bottom:6px}
.card-sub{font-size:13.5px;color:var(--gray4);margin-bottom:28px}
.field{margin-bottom:18px}
label{display:block;font-size:11px;font-weight:600;color:var(--gray4);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}
input{width:100%;padding:11px 14px;border:1.5px solid var(--gray2);border-radius:8px;font-size:14px;font-family:'DM Sans',sans-serif;color:var(--dark);transition:border-color .15s}
input:focus{outline:none;border-color:var(--sky);box-shadow:0 0 0 3px rgba(59,130,246,0.1)}
input.has-error{border-color:var(--red)}
.error-msg{font-size:12px;color:var(--red);margin-top:5px}
.optional{color:var(--gray4);font-weight:400;font-size:10px;margin-left:4px}
.submit-btn{width:100%;background:var(--gold);color:white;border:none;padding:13px;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;margin-top:8px;transition:background .15s}
.submit-btn:hover{background:var(--gold2);color:var(--navy)}
.login-prompt{text-align:center;margin-top:20px;font-size:13px;color:var(--gray4)}
.login-prompt a{color:var(--blue);text-decoration:none;font-weight:500}
</style>
</head>
<body>
<nav>
  <a href="/" class="nav-brand">Cambio Express</a>
  <a href="/login" class="nav-login">Already have an account? Sign in</a>
</nav>
<div class="page">
  <div class="card">
    <div class="trial-badge">✓ 7-day free trial &middot; No credit card needed</div>
    <div class="card-title">Create your account</div>
    <div class="card-sub">Start managing your store in minutes.</div>
    <form method="POST" action="/signup">
      <div class="field">
        <label>Store Name</label>
        <input type="text" name="store_name"
               value="{{ form.get('store_name','') }}"
               placeholder="e.g. Cambio Express Lamar"
               class="{{ 'has-error' if errors.get('store_name') else '' }}" required>
        {% if errors.get('store_name') %}
          <div class="error-msg">{{ errors.store_name }}</div>
        {% endif %}
      </div>
      <div class="field">
        <label>Store Email</label>
        <input type="email" name="email"
               value="{{ form.get('email','') }}"
               placeholder="store@example.com"
               class="{{ 'has-error' if errors.get('email') else '' }}" required>
        {% if errors.get('email') %}
          <div class="error-msg">{{ errors.email }}</div>
        {% endif %}
      </div>
      <div class="field">
        <label>Password</label>
        <input type="password" name="password"
               placeholder="Min. 8 characters"
               class="{{ 'has-error' if errors.get('password') else '' }}" required>
        {% if errors.get('password') %}
          <div class="error-msg">{{ errors.password }}</div>
        {% endif %}
      </div>
      <div class="field">
        <label>Phone <span class="optional">(optional)</span></label>
        <input type="tel" name="phone"
               value="{{ form.get('phone','') }}"
               placeholder="555-000-0000">
      </div>
      <button type="submit" class="submit-btn">Start Free Trial →</button>
    </form>
    <div class="login-prompt">Already have an account? <a href="/login">Sign in</a></div>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_signup.py -v
```

Expected: all 6 PASSED

- [ ] **Step 6: Commit**

```bash
git add app.py templates/signup.html tests/test_signup.py
git commit -m "feat: self-service signup with 7-day trial at /signup"
```

---

## Task 8: Subscribe Page

**Files:**
- Modify: `app.py` (add /subscribe route)
- Create: `templates/subscribe.html`
- Create: `tests/test_subscribe.py`

- [ ] **Step 1: Write failing tests in tests/test_subscribe.py**

```python
def test_subscribe_requires_login(client):
    resp = client.get("/subscribe", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_subscribe_loads_for_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/subscribe")
    assert resp.status_code == 200
    assert b"$20" in resp.data
    assert b"$30" in resp.data
    assert b"Basic" in resp.data
    assert b"Pro" in resp.data
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_subscribe.py -v
```

Expected: FAILED — no /subscribe route

- [ ] **Step 3: Add /subscribe route to app.py**

Add after the `/signup` route:

```python
@app.route("/subscribe")
@login_required
def subscribe():
    user = current_user()
    store = current_store()
    return render_template("subscribe.html", user=user, store=store)
```

- [ ] **Step 4: Create templates/subscribe.html**

```html
{% extends "base.html" %}
{% block title %}Choose Your Plan — Cambio Express{% endblock %}
{% block page_title %}Choose Your Plan{% endblock %}
{% block content %}

<div style="max-width:800px;margin:0 auto;text-align:center;margin-bottom:40px;">
  <div style="font-family:'DM Serif Display',serif;font-size:28px;color:var(--navy);margin-bottom:10px;">Upgrade to keep your access</div>
  <div style="color:var(--gray4);font-size:14px;">No contracts. Cancel anytime.</div>
</div>

<div style="display:grid;grid-template-columns:1fr 1.1fr;gap:24px;max-width:700px;margin:0 auto;">

  <div style="background:var(--white);border:1.5px solid var(--gray2);border-radius:14px;padding:32px 28px;">
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;color:var(--gray4);margin-bottom:8px;">Basic</div>
    <div style="font-family:'DM Serif Display',serif;font-size:40px;color:var(--navy);line-height:1;">$20</div>
    <div style="font-size:13px;color:var(--gray4);margin-bottom:20px;">per store / month</div>
    <ul style="list-style:none;margin-bottom:28px;">
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid var(--gray2);">✓ Daily books &amp; cash tracking</li>
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid var(--gray2);">✓ Money transfer logging</li>
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid var(--gray2);">✓ ACH batch reconciliation</li>
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid var(--gray2);">✓ Monthly P&amp;L reports</li>
      <li style="font-size:13.5px;padding:7px 0;color:var(--gray3);">✗ Bank sync</li>
    </ul>
    <form method="POST" action="/subscribe/checkout">
      <input type="hidden" name="plan" value="basic">
      <button type="submit" style="width:100%;background:transparent;color:var(--blue);border:1.5px solid var(--blue);padding:12px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;">Choose Basic</button>
    </form>
  </div>

  <div style="background:var(--navy);border:2px solid var(--gold);border-radius:14px;padding:32px 28px;position:relative;">
    <div style="position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:var(--gold);color:white;font-size:10px;font-weight:700;letter-spacing:1px;padding:3px 14px;border-radius:999px;white-space:nowrap;">MOST POPULAR</div>
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;color:var(--gold2);margin-bottom:8px;">Pro</div>
    <div style="font-family:'DM Serif Display',serif;font-size:40px;color:white;line-height:1;">$30</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.55);margin-bottom:20px;">per store / month</div>
    <ul style="list-style:none;margin-bottom:28px;">
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.85);">✓ Everything in Basic</li>
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.85);">✓ SimpleFIN bank sync</li>
      <li style="font-size:13.5px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.85);">✓ Live balance visibility</li>
      <li style="font-size:13.5px;padding:7px 0;color:rgba(255,255,255,0.85);">✓ Multi-store (coming soon)</li>
    </ul>
    <form method="POST" action="/subscribe/checkout">
      <input type="hidden" name="plan" value="pro">
      <button type="submit" style="width:100%;background:var(--gold);color:white;border:none;padding:12px;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;">Choose Pro</button>
    </form>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_subscribe.py -v
```

Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add app.py templates/subscribe.html tests/test_subscribe.py
git commit -m "feat: plan selection page at /subscribe"
```

---

## Task 9: Stripe Checkout Route

**Files:**
- Modify: `app.py` (add /subscribe/checkout route)

- [ ] **Step 1: Write failing tests — append to tests/test_subscribe.py**

```python
from unittest.mock import patch, MagicMock

def test_checkout_rejects_invalid_plan(logged_in_client):
    resp = logged_in_client.post("/subscribe/checkout",
                                  data={"plan": "enterprise"},
                                  follow_redirects=False)
    # Must not redirect to Stripe
    if resp.status_code == 302:
        assert "stripe.com" not in resp.headers.get("Location", "")

def test_checkout_redirects_to_stripe_for_basic(logged_in_client):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-basic"
    with patch("stripe.checkout.Session.create", return_value=mock_session):
        resp = logged_in_client.post("/subscribe/checkout",
                                      data={"plan": "basic"},
                                      follow_redirects=False)
    assert resp.status_code == 303
    assert "stripe.com" in resp.headers["Location"]

def test_checkout_redirects_to_stripe_for_pro(logged_in_client):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test-pro"
    with patch("stripe.checkout.Session.create", return_value=mock_session):
        resp = logged_in_client.post("/subscribe/checkout",
                                      data={"plan": "pro"},
                                      follow_redirects=False)
    assert resp.status_code == 303
    assert "stripe.com" in resp.headers["Location"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_subscribe.py::test_checkout_rejects_invalid_plan tests/test_subscribe.py::test_checkout_redirects_to_stripe_for_basic tests/test_subscribe.py::test_checkout_redirects_to_stripe_for_pro -v
```

Expected: FAILED — no /subscribe/checkout route

- [ ] **Step 3: Add /subscribe/checkout route to app.py**

Add after the `/subscribe` route:

```python
@app.route("/subscribe/checkout", methods=["POST"])
@login_required
def subscribe_checkout():
    store = current_store()
    plan = request.form.get("plan", "").strip()
    price_map = {
        "basic": os.environ.get("STRIPE_BASIC_PRICE_ID", ""),
        "pro":   os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    }
    if plan not in price_map or not price_map[plan]:
        flash("Invalid plan selected.", "error")
        return redirect(url_for("subscribe"))
    try:
        kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_map[plan], "quantity": 1}],
            metadata={"store_id": str(store.id)},
            success_url=url_for("subscribe_success", _external=True),
            cancel_url=url_for("subscribe", _external=True),
        )
        if store.stripe_customer_id:
            kwargs["customer"] = store.stripe_customer_id
        checkout_session = stripe.checkout.Session.create(**kwargs)
        return redirect(checkout_session.url, code=303)
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe error: {e}")
        flash("Payment service error. Please try again.", "error")
        return redirect(url_for("subscribe"))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_subscribe.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: Stripe Checkout session creation at /subscribe/checkout"
```

---

## Task 10: Subscribe Success Page

**Files:**
- Modify: `app.py` (add /subscribe/success route)
- Create: `templates/subscribe_success.html`

- [ ] **Step 1: Write failing test — append to tests/test_subscribe.py**

```python
def test_subscribe_success_loads(logged_in_client):
    resp = logged_in_client.get("/subscribe/success")
    assert resp.status_code == 200
    assert b"payment" in resp.data.lower() or b"plan" in resp.data.lower()
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_subscribe.py::test_subscribe_success_loads -v
```

Expected: FAILED — no /subscribe/success route

- [ ] **Step 3: Add /subscribe/success route to app.py**

```python
@app.route("/subscribe/success")
@login_required
def subscribe_success():
    user = current_user()
    store = current_store()
    return render_template("subscribe_success.html", user=user, store=store)
```

- [ ] **Step 4: Create templates/subscribe_success.html**

```html
{% extends "base.html" %}
{% block title %}Payment Received — Cambio Express{% endblock %}
{% block page_title %}Payment Received{% endblock %}
{% block content %}

<div style="max-width:560px;margin:60px auto;text-align:center;">
  {% if store and store.plan in ('basic', 'pro') %}
    <div style="font-size:52px;margin-bottom:20px;">🎉</div>
    <div style="font-family:'DM Serif Display',serif;font-size:28px;color:var(--navy);margin-bottom:12px;">
      You're on {{ store.plan|capitalize }}!
    </div>
    <div style="color:var(--gray4);font-size:14px;line-height:1.7;margin-bottom:32px;">
      Your account is active. You now have full access to all {{ store.plan|capitalize }} features.
    </div>
    <a href="{{ url_for('dashboard') }}" class="btn btn-primary" style="font-size:15px;padding:12px 28px;">
      Go to Dashboard →
    </a>
  {% else %}
    <div style="font-size:52px;margin-bottom:20px;">⏳</div>
    <div style="font-family:'DM Serif Display',serif;font-size:28px;color:var(--navy);margin-bottom:12px;">
      Payment Received!
    </div>
    <div style="color:var(--gray4);font-size:14px;line-height:1.7;margin-bottom:32px;">
      We've received your payment and are activating your account.
      This usually takes a few seconds — please refresh or go to your dashboard.
    </div>
    <div style="display:flex;gap:12px;justify-content:center;">
      <a href="{{ url_for('subscribe_success') }}" class="btn btn-outline">Refresh</a>
      <a href="{{ url_for('dashboard') }}" class="btn btn-primary">Go to Dashboard →</a>
    </div>
  {% endif %}
</div>

{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_subscribe.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add app.py templates/subscribe_success.html
git commit -m "feat: post-payment confirmation at /subscribe/success"
```

---

## Task 11: Stripe Webhook

**Files:**
- Modify: `app.py` (replace stub webhook with full handler)

- [ ] **Step 1: Write failing tests — append to tests/test_subscribe.py**

```python
import json

def test_webhook_rejects_invalid_signature(client):
    resp = client.post("/webhooks/stripe",
                       data=b'{"type":"checkout.session.completed"}',
                       headers={"Stripe-Signature": "bad",
                                "Content-Type": "application/json"})
    assert resp.status_code == 400

def test_webhook_checkout_completed_updates_plan(client):
    from app import db, Store
    with client.application.app_context():
        s = Store(name="Webhook Store", slug="webhook-store",
                  email="webhook@test.com", plan="trial",
                  stripe_customer_id="cus_test123")
        db.session.add(s)
        db.session.commit()
        sid = s.id

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"store_id": str(sid)},
            "customer": "cus_test123",
            "subscription": "sub_test456",
        }}
    }
    mock_sub = {"items": {"data": [{"price": {"id": "price_pro_test"}}]}}

    with patch("stripe.Webhook.construct_event", return_value=event_payload), \
         patch("stripe.Subscription.retrieve", return_value=mock_sub):
        resp = client.post("/webhooks/stripe",
                           data=json.dumps(event_payload).encode(),
                           headers={"Stripe-Signature": "valid",
                                    "Content-Type": "application/json"})

    assert resp.status_code == 200
    with client.application.app_context():
        s = Store.query.get(sid)
        assert s.plan == "pro"
        assert s.stripe_subscription_id == "sub_test456"

def test_webhook_subscription_deleted_sets_inactive(client):
    from app import db, Store
    with client.application.app_context():
        s = Store(name="Cancel Store", slug="cancel-store",
                  email="cancel@test.com", plan="pro",
                  stripe_subscription_id="sub_cancel789")
        db.session.add(s)
        db.session.commit()
        sid = s.id

    event_payload = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_cancel789"}}
    }
    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        resp = client.post("/webhooks/stripe",
                           data=json.dumps(event_payload).encode(),
                           headers={"Stripe-Signature": "valid",
                                    "Content-Type": "application/json"})

    assert resp.status_code == 200
    with client.application.app_context():
        s = Store.query.get(sid)
        assert s.plan == "inactive"
        assert s.stripe_subscription_id == ""
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_subscribe.py::test_webhook_rejects_invalid_signature tests/test_subscribe.py::test_webhook_checkout_completed_updates_plan tests/test_subscribe.py::test_webhook_subscription_deleted_sets_inactive -v
```

Expected: FAILED — webhook is a stub

- [ ] **Step 3: Replace stripe_webhook stub in app.py**

Find the existing `stripe_webhook` function and replace it entirely:

```python
@app.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        store_id = obj.get("metadata", {}).get("store_id")
        if store_id:
            store = Store.query.get(int(store_id))
            if store:
                sub_id = obj.get("subscription", "")
                customer_id = obj.get("customer", "")
                try:
                    sub = stripe.Subscription.retrieve(sub_id)
                    price_id = sub["items"]["data"][0]["price"]["id"]
                    basic_pid = os.environ.get("STRIPE_BASIC_PRICE_ID", "")
                    store.plan = "basic" if price_id == basic_pid else "pro"
                except Exception as e:
                    app.logger.error(f"Stripe sub retrieve error: {e}")
                    store.plan = "pro"
                store.stripe_customer_id = customer_id
                store.stripe_subscription_id = sub_id
                db.session.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"].get("id", "")
        store = Store.query.filter_by(stripe_subscription_id=sub_id).first()
        if store:
            store.plan = "inactive"
            store.stripe_subscription_id = ""
            db.session.commit()

    return jsonify({"received": True}), 200
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASSED, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_subscribe.py
git commit -m "feat: full Stripe webhook handler for checkout and subscription events"
```

---

## Task 12: Deploy to Production

- [ ] **Step 1: Run DB migration on Render**

In the Render PostgreSQL dashboard → Shell, run:

```sql
ALTER TABLE store ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP;
ALTER TABLE store ADD COLUMN IF NOT EXISTS grace_ends_at TIMESTAMP;
```

This is only needed for the existing database. New databases handled automatically by `db.create_all()`.

- [ ] **Step 2: Add environment variables in Render dashboard**

Go to your Render web service → Environment → Add these vars:

| Key | Where to get it |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe Dashboard → Developers → API keys |
| `STRIPE_BASIC_PRICE_ID` | Stripe Dashboard → Products → create $20/mo Basic product → copy Price ID |
| `STRIPE_PRO_PRICE_ID` | Stripe Dashboard → Products → create $30/mo Pro product → copy Price ID |
| `STRIPE_WEBHOOK_SECRET` | Stripe Dashboard → Developers → Webhooks → Add endpoint (step 3 below) |

- [ ] **Step 3: Register webhook with Stripe**

In Stripe Dashboard → Developers → Webhooks → Add endpoint:
- **URL:** `https://your-app.onrender.com/webhooks/stripe`
- **Events:** select `checkout.session.completed` and `customer.subscription.deleted`
- Copy the **Signing secret** → paste as `STRIPE_WEBHOOK_SECRET` in Render

- [ ] **Step 4: Push and verify deploy**

```bash
git push origin main
```

After Render deploys, verify:
1. `https://your-app.onrender.com/` → landing page loads
2. `https://your-app.onrender.com/signup` → signup form loads
3. Sign up → trial starts, dashboard accessible
4. `https://your-app.onrender.com/login` → login works
