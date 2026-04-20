# Multi-Store Owner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a single owner user to view aggregate stats and per-store summaries across multiple linked stores, with an invite-code system for admins to grant access.

**Architecture:** Two new DB models (`StoreOwnerLink`, `OwnerInviteCode`) link owners to stores via redeemable invite codes. A new `owner_required` decorator guards owner-only routes. Owner accounts are view-only with a dedicated `base_owner.html` layout and `owner_dashboard.html`. Admin settings gains a 4th "Owner Access" tab for code management.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, pytest-flask, SQLite in-memory for tests, `secrets` + `string` stdlib modules.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app.py` | Modify | Add `import secrets, string`; add `StoreOwnerLink`, `OwnerInviteCode` models; add `owner_required` decorator; update `_TRIAL_EXEMPT` and `inject_trial_context`; add `signup_owner`, `owner_dashboard`, `owner_link_store`, `owner_unlink_store`, `admin_generate_owner_code`, `admin_remove_owner_access` routes; modify login redirect for owners; modify `admin_settings` to pass owner-tab context |
| `templates/base_owner.html` | Create | Simplified sidebar layout for owner — Dashboard link only, no operational nav |
| `templates/owner_dashboard.html` | Create | Aggregate stats + period filter + per-store cards + code entry form |
| `templates/signup_owner.html` | Create | Owner signup form (Full Name, Email, Password) |
| `templates/signup.html` | Modify | Add footer link to `/signup/owner` |
| `templates/admin_settings.html` | Modify | Add "Owner Access" 4th tab with code management UI |
| `tests/test_multi_store_owner.py` | Create | All owner feature tests |

---

### Task 1: Add `StoreOwnerLink` and `OwnerInviteCode` models

**Files:**
- Modify: `app.py` (after `SimpleFINConfig` model, before `# ── Auth ──`)
- Create: `tests/test_multi_store_owner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_multi_store_owner.py`:

```python
import pytest
from app import app as flask_app, db


def test_store_owner_link_model_exists():
    with flask_app.app_context():
        from app import StoreOwnerLink
        assert hasattr(StoreOwnerLink, "owner_id")
        assert hasattr(StoreOwnerLink, "store_id")
        assert hasattr(StoreOwnerLink, "linked_at")


def test_owner_invite_code_model_exists():
    with flask_app.app_context():
        from app import OwnerInviteCode
        assert hasattr(OwnerInviteCode, "store_id")
        assert hasattr(OwnerInviteCode, "code")
        assert hasattr(OwnerInviteCode, "created_by")
        assert hasattr(OwnerInviteCode, "expires_at")
        assert hasattr(OwnerInviteCode, "used_at")
        assert hasattr(OwnerInviteCode, "used_by_owner_id")


def test_store_owner_link_unique_constraint():
    with flask_app.app_context():
        from app import StoreOwnerLink, User, Store
        import sqlalchemy
        store = Store.query.filter_by(slug="test-store").first()
        owner = User(username="owner@test.com", full_name="Owner", role="owner", store_id=None)
        owner.set_password("pass1234!")
        db.session.add(owner)
        db.session.flush()
        link1 = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        link2 = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link1)
        db.session.flush()
        db.session.add(link2)
        with pytest.raises(Exception):
            db.session.flush()
        db.session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

```
cd "C:\Users\snehi\Desktop\Test Claude\DineroSync"
python -m pytest tests/test_multi_store_owner.py -v
```

Expected: `ImportError: cannot import name 'StoreOwnerLink'`

- [ ] **Step 3: Add `import secrets, string` to `app.py`**

In `app.py` line 7, change:
```python
import requests, base64, os, calendar, logging, re
```
to:
```python
import requests, base64, os, calendar, logging, re, secrets, string
```

- [ ] **Step 4: Add the two models to `app.py`**

Add after the `SimpleFINConfig` model (after line ~232, before `# ── Auth ──`):

```python
class StoreOwnerLink(db.Model):
    __tablename__ = "store_owner_link"
    id        = db.Column(db.Integer, primary_key=True)
    owner_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    store_id  = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    linked_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("owner_id", "store_id"),)

class OwnerInviteCode(db.Model):
    __tablename__ = "owner_invite_code"
    id               = db.Column(db.Integer, primary_key=True)
    store_id         = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    code             = db.Column(db.String(8), unique=True, nullable=False)
    created_by       = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at       = db.Column(db.DateTime, nullable=False)
    used_at          = db.Column(db.DateTime, nullable=True)
    used_by_owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_multi_store_owner.py -v
```

Expected: 3 PASS

- [ ] **Step 6: Run full suite to check for regressions**

```
python -m pytest --tb=short -q
```

Expected: all existing tests pass

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_multi_store_owner.py
git commit -m "feat: add StoreOwnerLink and OwnerInviteCode models"
```

---

### Task 2: `owner_required` decorator, trial exemption, login redirect, trial context

**Files:**
- Modify: `app.py` (auth section + login route + inject_trial_context)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_multi_store_owner.py`:

```python
def test_owner_required_blocks_non_owner(client):
    """Non-owner users get 403 from owner-only routes."""
    # logged_in_client is admin — should be blocked
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="admin@test.com").first()
        uid, sid = u.id, u.store_id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid
    rv = client.get("/owner/dashboard")
    assert rv.status_code == 403


def test_owner_required_blocks_unauthenticated(client):
    rv = client.get("/owner/dashboard")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_login_redirects_owner_to_owner_dashboard(client):
    with flask_app.app_context():
        from app import User
        o = User(username="owner@test.com", full_name="Test Owner", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.commit()
    rv = client.post("/login", data={"username": "owner@test.com", "password": "ownerpass123"})
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_multi_store_owner.py::test_owner_required_blocks_non_owner tests/test_multi_store_owner.py::test_owner_required_blocks_unauthenticated tests/test_multi_store_owner.py::test_login_redirects_owner_to_owner_dashboard -v
```

Expected: FAIL (route `/owner/dashboard` does not exist yet)

- [ ] **Step 3: Add `owner_required` decorator to `app.py`**

Add after `superadmin_required` (after line ~270), before `# ── Trial Status ──`:

```python
def owner_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = current_user()
        if not u or u.role != "owner":
            abort(403)
        return f(*a, **k)
    return d
```

- [ ] **Step 4: Update `_TRIAL_EXEMPT` and `inject_trial_context`**

Change `_TRIAL_EXEMPT` (around line 237):
```python
_TRIAL_EXEMPT = {"subscribe", "subscribe_checkout", "subscribe_success", "logout",
                 "owner_dashboard", "owner_link_store", "owner_unlink_store"}
```

In `inject_trial_context` (around line 299), add the owner exemption after the superadmin check:
```python
    if not user:
        return {"trial_status": "exempt", "trial_days_left": 0}
    if user.role == "superadmin":
        return {"trial_status": "exempt", "trial_days_left": 0}
    if user.role == "owner":
        return {"trial_status": "exempt", "trial_days_left": 0}
```

- [ ] **Step 5: Add a stub `owner_dashboard` route (will be fully implemented in Task 4)**

Add to `app.py` after the `logout` route:

```python
@app.route("/owner/dashboard")
@owner_required
def owner_dashboard():
    return "owner dashboard stub", 200
```

- [ ] **Step 6: Update the `login` route to redirect owners to `owner_dashboard`**

Find this block in the `login` route (around line 384-392):
```python
        if u and u.is_active and u.check_password(request.form.get("password","")):
            if u.role == "employee":
                error = "Please use your store's login link."
            else:
                session["user_id"]=u.id; session["role"]=u.role; session["store_id"]=u.store_id
                return redirect(url_for("dashboard"))
```

Replace with:
```python
        if u and u.is_active and u.check_password(request.form.get("password","")):
            if u.role == "employee":
                error = "Please use your store's login link."
            else:
                session["user_id"]=u.id; session["role"]=u.role; session["store_id"]=u.store_id
                if u.role == "owner":
                    return redirect(url_for("owner_dashboard"))
                return redirect(url_for("dashboard"))
```

- [ ] **Step 7: Run tests to verify they pass**

```
python -m pytest tests/test_multi_store_owner.py::test_owner_required_blocks_non_owner tests/test_multi_store_owner.py::test_owner_required_blocks_unauthenticated tests/test_multi_store_owner.py::test_login_redirects_owner_to_owner_dashboard -v
```

Expected: 3 PASS

- [ ] **Step 8: Run full suite**

```
python -m pytest --tb=short -q
```

Expected: all existing tests pass

- [ ] **Step 9: Commit**

```bash
git add app.py
git commit -m "feat: add owner_required decorator, trial exemption, login redirect for owner role"
```

---

### Task 3: Owner signup route + `signup_owner.html` + footer link on `signup.html`

**Files:**
- Modify: `app.py` (add `signup_owner` route)
- Create: `templates/signup_owner.html`
- Modify: `templates/signup.html`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_multi_store_owner.py`:

```python
def test_owner_signup_success(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner",
        "email": "jane@example.com",
        "password": "password123",
    })
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="jane@example.com", store_id=None).first()
        assert u is not None
        assert u.role == "owner"
        assert u.store_id is None
        assert u.full_name == "Jane Owner"


def test_owner_signup_sets_session(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner",
        "email": "jane@example.com",
        "password": "password123",
    })
    with client.session_transaction() as sess:
        assert sess["role"] == "owner"
        assert sess.get("store_id") is None


def test_owner_signup_duplicate_email_rejected(client):
    client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "jane@example.com", "password": "password123",
    })
    rv = client.post("/signup/owner", data={
        "full_name": "Jane 2", "email": "jane@example.com", "password": "password123",
    })
    assert rv.status_code == 200
    assert b"already exists" in rv.data


def test_owner_signup_short_password_rejected(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "jane@example.com", "password": "short",
    })
    assert rv.status_code == 200
    assert b"8 characters" in rv.data


def test_owner_signup_invalid_email_rejected(client):
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "notanemail", "password": "password123",
    })
    assert rv.status_code == 200
    assert b"valid email" in rv.data


def test_owner_signup_blocks_admin_email(client):
    """Existing store admin email cannot be reused as an owner."""
    rv = client.post("/signup/owner", data={
        "full_name": "Jane Owner", "email": "admin@test.com", "password": "password123",
    })
    assert rv.status_code == 200
    assert b"already exists" in rv.data


def test_owner_signup_get_renders_form(client):
    rv = client.get("/signup/owner")
    assert rv.status_code == 200
    assert b"owner" in rv.data.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_multi_store_owner.py -k "signup" -v
```

Expected: FAIL (route `/signup/owner` does not exist)

- [ ] **Step 3: Add `signup_owner` route to `app.py`**

Add after the `signup` route (after line ~465, before `logout`):

```python
@app.route("/signup/owner", methods=["GET", "POST"])
def signup_owner():
    if "user_id" in session:
        u = current_user()
        if u and u.role == "owner":
            return redirect(url_for("owner_dashboard"))
        return redirect(url_for("dashboard"))
    errors = {}
    form = {}
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email     = request.form.get("email", "").strip().lower()
        password  = request.form.get("password", "")
        form = {"full_name": full_name, "email": email}
        if not full_name:
            errors["full_name"] = "Full name is required."
        if not email:
            errors["email"] = "Email is required."
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors["email"] = "Enter a valid email address."
        if not password:
            errors["password"] = "Password is required."
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        if not errors:
            taken_null  = User.query.filter(User.username == email, User.store_id.is_(None)).first()
            taken_admin = User.query.filter(User.username == email, User.role == "admin").first()
            if taken_null or taken_admin:
                errors["email"] = "An account with this email already exists."
        if not errors:
            u = User(store_id=None, username=email, full_name=full_name, role="owner")
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"]  = u.id
            session["role"]     = "owner"
            session["store_id"] = None
            return redirect(url_for("owner_dashboard"))
    return render_template("signup_owner.html", errors=errors, form=form)
```

- [ ] **Step 4: Create `templates/signup_owner.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Owner Sign Up — Cambio Express</title>
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
.owner-badge{display:inline-flex;align-items:center;gap:6px;background:#dbeafe;color:#1d4ed8;border-radius:999px;padding:4px 12px;font-size:12px;font-weight:600;margin-bottom:22px}
.card-title{font-family:'DM Serif Display',serif;font-size:26px;color:var(--navy);margin-bottom:6px}
.card-sub{font-size:13.5px;color:var(--gray4);margin-bottom:28px}
.field{margin-bottom:18px}
label{display:block;font-size:11px;font-weight:600;color:var(--gray4);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}
input{width:100%;padding:11px 14px;border:1.5px solid var(--gray2);border-radius:8px;font-size:14px;font-family:'DM Sans',sans-serif;color:var(--dark);transition:border-color .15s}
input:focus{outline:none;border-color:var(--sky);box-shadow:0 0 0 3px rgba(59,130,246,0.1)}
input.has-error{border-color:var(--red)}
.error-msg{font-size:12px;color:var(--red);margin-top:5px}
.submit-btn{width:100%;background:var(--gold);color:white;border:none;padding:13px;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;margin-top:8px;transition:background .15s}
.submit-btn:hover{background:var(--gold2);color:var(--navy)}
.login-prompt{text-align:center;margin-top:20px;font-size:13px;color:var(--gray4)}
.login-prompt a{color:var(--blue);text-decoration:none;font-weight:500}
@media(max-width:600px){
  nav{padding:0 16px;height:56px}
  .page{padding:24px 14px}
  .card{padding:28px 22px;border-radius:14px}
  .card-title{font-size:22px}
  input{font-size:16px;padding:12px 14px}
  .submit-btn{padding:14px;font-size:15px}
}
</style>
</head>
<body>
<nav>
  <a href="/" class="nav-brand">Cambio Express</a>
  <a href="/login" class="nav-login">Already have an account? Sign in</a>
</nav>
<div class="page">
  <div class="card">
    <div class="owner-badge">&#9733; Multi-Store Owner Account</div>
    <div class="card-title">Create owner account</div>
    <div class="card-sub">Manage multiple store locations from one login.</div>
    <form method="POST" action="/signup/owner">
      <div class="field">
        <label>Full Name</label>
        <input type="text" name="full_name"
               value="{{ form.get('full_name','') }}"
               placeholder="Your full name"
               class="{{ 'has-error' if errors.get('full_name') else '' }}" required>
        {% if errors.get('full_name') %}
          <div class="error-msg">{{ errors.full_name }}</div>
        {% endif %}
      </div>
      <div class="field">
        <label>Email</label>
        <input type="email" name="email"
               value="{{ form.get('email','') }}"
               placeholder="you@example.com"
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
      <button type="submit" class="submit-btn">Create Owner Account &rarr;</button>
    </form>
    <div class="login-prompt">Already have an account? <a href="/login">Sign in</a></div>
    <div class="login-prompt" style="margin-top:10px;">Managing a single store? <a href="/signup">Sign up as a store</a></div>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 5: Add footer link to `templates/signup.html`**

Find in `signup.html`:
```html
    <div class="login-prompt">Already have an account? <a href="/login">Sign in</a></div>
```

Replace with:
```html
    <div class="login-prompt">Already have an account? <a href="/login">Sign in</a></div>
    <div class="login-prompt" style="margin-top:10px;">Own multiple locations? <a href="/signup/owner">Sign up as an owner &rarr;</a></div>
```

- [ ] **Step 6: Run signup tests**

```
python -m pytest tests/test_multi_store_owner.py -k "signup" -v
```

Expected: 7 PASS

- [ ] **Step 7: Run full suite**

```
python -m pytest --tb=short -q
```

Expected: all existing tests pass

- [ ] **Step 8: Commit**

```bash
git add app.py templates/signup_owner.html templates/signup.html
git commit -m "feat: owner signup route and template"
```

---

### Task 4: `base_owner.html` + `owner_dashboard` route + `owner_dashboard.html`

**Files:**
- Create: `templates/base_owner.html`
- Create: `templates/owner_dashboard.html`
- Modify: `app.py` (replace stub `owner_dashboard` with real implementation)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_multi_store_owner.py`:

```python
@pytest.fixture
def owner_client():
    """Client pre-authenticated as an owner with no stores linked."""
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User
        o = User(username="owner@dashboard.com", full_name="Test Owner", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.commit()
        oid = o.id
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return c


def test_owner_dashboard_loads_no_stores(owner_client):
    rv = owner_client.get("/owner/dashboard")
    assert rv.status_code == 200
    assert b"invite" in rv.data.lower() or b"connect" in rv.data.lower()


def test_owner_dashboard_shows_store_after_link(owner_client):
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
    rv = owner_client.get("/owner/dashboard")
    assert rv.status_code == 200
    assert b"Test Store" in rv.data


def test_owner_dashboard_period_filter_today(owner_client):
    rv = owner_client.get("/owner/dashboard?period=today")
    assert rv.status_code == 200


def test_owner_dashboard_period_filter_month(owner_client):
    rv = owner_client.get("/owner/dashboard?period=month")
    assert rv.status_code == 200


def test_owner_dashboard_period_filter_year(owner_client):
    rv = owner_client.get("/owner/dashboard?period=year")
    assert rv.status_code == 200


def test_owner_dashboard_aggregate_counts_transfers(owner_client):
    from datetime import date
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink, Transfer
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(link)
        admin = User.query.filter_by(username="admin@test.com").first()
        t = Transfer(store_id=store.id, created_by=admin.id, send_date=date.today(),
                     company="Intermex", sender_name="John", send_amount=100.0)
        db.session.add(t)
        db.session.commit()
    rv = owner_client.get("/owner/dashboard?period=today")
    assert rv.status_code == 200
    assert b"100" in rv.data
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_multi_store_owner.py -k "dashboard" -v
```

Expected: FAIL (stub returns plain text, templates missing)

- [ ] **Step 3: Create `templates/base_owner.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}Cambio Express — Owner{% endblock %}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --navy:#0f1f3d;--blue:#1a4080;--mid:#2a5caa;--sky:#3b82f6;
  --gold:#c9973a;--gold2:#f0c060;--cream:#faf7f2;--paper:#f3ede3;
  --white:#ffffff;--gray1:#f5f5f7;--gray2:#e8e8ec;--gray3:#b0b4c0;
  --gray4:#6b7280;--dark:#1a1a2e;--green:#16a34a;--red:#dc2626;
  --orange:#ea580c;--yellow:#ca8a04;--sidebar-w:240px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--dark)}
.layout{display:flex;min-height:100vh}
.sidebar{width:var(--sidebar-w);background:var(--navy);display:flex;flex-direction:column;position:fixed;top:0;left:0;height:100vh;z-index:100;overflow-y:auto}
.sidebar-logo{padding:24px 20px 16px;border-bottom:1px solid rgba(255,255,255,0.08)}
.sidebar-logo .brand{font-family:'DM Serif Display',serif;font-size:18px;color:var(--gold2);line-height:1.2;letter-spacing:0.3px}
.sidebar-logo .sub{font-size:11px;color:rgba(255,255,255,0.4);margin-top:3px;font-weight:300;letter-spacing:1px;text-transform:uppercase}
.sidebar-user{padding:14px 20px;border-bottom:1px solid rgba(255,255,255,0.08)}
.sidebar-user .uname{font-size:13px;font-weight:600;color:var(--white);line-height:1}
.sidebar-user .urole{font-size:11px;color:var(--gold);margin-top:3px;text-transform:uppercase;letter-spacing:0.8px}
.sidebar-nav{flex:1;padding:12px 0}
.nav-section{font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:1.2px;text-transform:uppercase;padding:16px 20px 6px}
.nav-link{display:flex;align-items:center;gap:10px;padding:10px 20px;color:rgba(255,255,255,0.65);text-decoration:none;font-size:13.5px;font-weight:400;transition:all 0.15s;border-left:3px solid transparent}
.nav-link:hover{color:var(--white);background:rgba(255,255,255,0.06)}
.nav-link.active{color:var(--gold2);border-left-color:var(--gold);background:rgba(201,151,58,0.08)}
.nav-link .icon{font-size:16px;width:20px;text-align:center}
.sidebar-footer{padding:16px 20px;border-top:1px solid rgba(255,255,255,0.08)}
.sidebar-footer a{font-size:12px;color:rgba(255,255,255,0.4);text-decoration:none;display:flex;align-items:center;gap:8px}
.sidebar-footer a:hover{color:rgba(255,255,255,0.7)}
.main{margin-left:var(--sidebar-w);flex:1;display:flex;flex-direction:column;min-height:100vh}
.topbar{background:var(--white);border-bottom:1px solid var(--gray2);padding:0 32px;height:58px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50}
.topbar-title{font-family:'DM Serif Display',serif;font-size:20px;color:var(--navy)}
.topbar-date{font-size:12px;color:var(--gray4);font-family:'JetBrains Mono',monospace}
.content{padding:32px;flex:1}
.card{background:var(--white);border-radius:12px;border:1px solid var(--gray2);overflow:hidden}
.card-header{padding:18px 24px;border-bottom:1px solid var(--gray2);display:flex;align-items:center;justify-content:space-between}
.card-title{font-weight:600;font-size:15px;color:var(--navy)}
.card-body{padding:24px}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;margin-bottom:28px}
.stat-card{background:var(--white);border-radius:12px;border:1px solid var(--gray2);padding:20px 22px;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent,var(--sky))}
.stat-label{font-size:11px;color:var(--gray4);text-transform:uppercase;letter-spacing:0.8px;font-weight:500}
.stat-value{font-family:'DM Serif Display',serif;font-size:30px;color:var(--navy);margin-top:6px;line-height:1}
.stat-sub{font-size:12px;color:var(--gray4);margin-top:6px}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;letter-spacing:0.3px}
.badge-green{background:#dcfce7;color:#15803d}
.badge-blue{background:#dbeafe;color:#1d4ed8}
.badge-gray{background:var(--gray2);color:var(--gray4)}
.badge-navy{background:var(--navy);color:var(--gold2)}
.btn{display:inline-flex;align-items:center;gap:7px;padding:9px 18px;border-radius:8px;font-size:13.5px;font-weight:500;cursor:pointer;border:none;text-decoration:none;transition:all 0.15s;font-family:'DM Sans',sans-serif}
.btn-primary{background:var(--blue);color:var(--white)}
.btn-primary:hover{background:var(--mid)}
.btn-outline{background:transparent;color:var(--blue);border:1.5px solid var(--blue)}
.btn-outline:hover{background:var(--blue);color:var(--white)}
.btn-sm{padding:6px 12px;font-size:12px}
.btn-danger{background:var(--red);color:var(--white)}
.field{display:flex;flex-direction:column;gap:6px}
label{font-size:12px;font-weight:600;color:var(--gray4);text-transform:uppercase;letter-spacing:0.6px}
input,select{padding:10px 14px;border:1.5px solid var(--gray2);border-radius:8px;font-size:14px;font-family:'DM Sans',sans-serif;color:var(--dark);background:var(--white);transition:border-color 0.15s;width:100%}
input:focus,select:focus{outline:none;border-color:var(--sky);box-shadow:0 0 0 3px rgba(59,130,246,0.1)}
.flash{padding:12px 18px;border-radius:8px;margin-bottom:20px;font-size:14px;font-weight:500}
.flash-success{background:#dcfce7;color:#15803d;border:1px solid #bbf7d0}
.flash-error{background:#fee2e2;color:#b91c1c;border:1px solid #fecaca}
.flash-info{background:#dbeafe;color:#1d4ed8;border:1px solid #bfdbfe}
.mt-2{margin-top:16px}.mt-3{margin-top:24px}.mb-2{margin-bottom:16px}.mb-3{margin-bottom:24px}
.flex{display:flex}.items-center{align-items:center}.gap-2{gap:8px}.gap-3{gap:16px}
.justify-between{justify-content:space-between}.ml-auto{margin-left:auto}
.text-sm{font-size:12px}.text-muted{color:var(--gray4)}
.amount-pos{color:var(--green);font-weight:600}
.amount-neg{color:var(--red);font-weight:600}
@media(max-width:900px){
  .sidebar{transform:translateX(-100%);transition:transform 0.25s ease}
  .sidebar.open{transform:translateX(0)}
  .main{margin-left:0}
  .topbar{padding:0 16px;height:56px}
  .content{padding:16px}
  .stats-grid{grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
}
@media(max-width:480px){
  .stats-grid{grid-template-columns:1fr}
  .content{padding:12px}
}
</style>
{% block head %}{% endblock %}
</head>
<body>
<div class="layout">
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-logo">
      <div class="brand">Cambio Express</div>
      <div class="sub">Owner Portal</div>
    </div>
    <div class="sidebar-user">
      <div class="uname">{{ user.full_name or user.username }}</div>
      <div class="urole">Owner</div>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section">Overview</div>
      <a href="{{ url_for('owner_dashboard') }}" class="nav-link {% if request.endpoint == 'owner_dashboard' %}active{% endif %}">
        <span class="icon">⬛</span> Dashboard
      </a>
    </nav>
    <div class="sidebar-footer">
      <a href="{{ url_for('logout') }}">&#x2192; Sign out</a>
    </div>
  </aside>
  <div class="main">
    <div class="topbar">
      <div class="topbar-title">{% block page_title %}{% endblock %}</div>
      <div class="topbar-date" id="topbar-date"></div>
    </div>
    <div class="content">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat, msg in messages %}
          <div class="flash flash-{{ cat }}">{{ msg }}</div>
        {% endfor %}
      {% endwith %}
      {% block content %}{% endblock %}
    </div>
  </div>
</div>
<script>
var d=new Date();
var el=document.getElementById('topbar-date');
if(el){el.textContent=d.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric'});}
</script>
{% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 4: Replace stub `owner_dashboard` route in `app.py`**

Replace:
```python
@app.route("/owner/dashboard")
@owner_required
def owner_dashboard():
    return "owner dashboard stub", 200
```

With:
```python
@app.route("/owner/dashboard")
@owner_required
def owner_dashboard():
    u = current_user()
    period = request.args.get("period", "today")
    today = date.today()

    links = StoreOwnerLink.query.filter_by(owner_id=u.id).all()
    store_ids = [l.store_id for l in links]
    stores = Store.query.filter(Store.id.in_(store_ids)).order_by(Store.name).all() if store_ids else []

    if period == "today":
        date_start = date_end = today
    elif period == "month":
        date_start = date(today.year, today.month, 1)
        date_end = today
    else:
        date_start = date(today.year, 1, 1)
        date_end = today

    if store_ids:
        agg_transfer_count = Transfer.query.filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= date_start,
            Transfer.send_date <= date_end
        ).count()
        agg_volume = db.session.query(db.func.sum(Transfer.send_amount)).filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= date_start,
            Transfer.send_date <= date_end
        ).scalar() or 0.0
        agg_over_short = db.session.query(db.func.sum(DailyReport.over_short)).filter(
            DailyReport.store_id.in_(store_ids),
            DailyReport.report_date >= date_start,
            DailyReport.report_date <= date_end
        ).scalar() or 0.0
    else:
        agg_transfer_count = 0
        agg_volume = 0.0
        agg_over_short = 0.0

    store_data = []
    for store in stores:
        t_count = Transfer.query.filter(
            Transfer.store_id == store.id,
            Transfer.send_date >= date_start,
            Transfer.send_date <= date_end
        ).count()
        t_volume = db.session.query(db.func.sum(Transfer.send_amount)).filter(
            Transfer.store_id == store.id,
            Transfer.send_date >= date_start,
            Transfer.send_date <= date_end
        ).scalar() or 0.0
        reports = DailyReport.query.filter(
            DailyReport.store_id == store.id,
            DailyReport.report_date >= date_start,
            DailyReport.report_date <= date_end
        ).all()
        total_receipts = sum(r.total_receipts for r in reports)
        over_short = sum(r.over_short for r in reports)
        store_data.append({
            "store": store,
            "transfer_count": t_count,
            "volume": t_volume,
            "total_receipts": total_receipts,
            "over_short": over_short,
        })

    return render_template("owner_dashboard.html",
        user=u, period=period,
        agg_transfer_count=agg_transfer_count,
        agg_volume=agg_volume,
        agg_over_short=agg_over_short,
        store_count=len(stores),
        store_data=store_data,
    )
```

- [ ] **Step 5: Create `templates/owner_dashboard.html`**

```html
{% extends "base_owner.html" %}
{% block title %}Dashboard — Cambio Express Owner{% endblock %}
{% block page_title %}Owner Dashboard{% endblock %}
{% block content %}

<!-- Period filter -->
<div style="display:flex;gap:8px;margin-bottom:24px;align-items:center;">
  <span style="font-size:13px;color:var(--gray4);font-weight:500;">Period:</span>
  <a href="{{ url_for('owner_dashboard', period='today') }}"
     class="btn btn-sm {% if period == 'today' %}btn-primary{% else %}btn-outline{% endif %}">Today</a>
  <a href="{{ url_for('owner_dashboard', period='month') }}"
     class="btn btn-sm {% if period == 'month' %}btn-primary{% else %}btn-outline{% endif %}">This Month</a>
  <a href="{{ url_for('owner_dashboard', period='year') }}"
     class="btn btn-sm {% if period == 'year' %}btn-primary{% else %}btn-outline{% endif %}">This Year</a>
</div>

<!-- Aggregate stat cards -->
<div class="stats-grid">
  <div class="stat-card" style="--accent:var(--sky)">
    <div class="stat-label">Transfers</div>
    <div class="stat-value">{{ agg_transfer_count }}</div>
    <div class="stat-sub">across all stores</div>
  </div>
  <div class="stat-card" style="--accent:var(--green)">
    <div class="stat-label">Volume</div>
    <div class="stat-value">${{ "%.0f"|format(agg_volume) }}</div>
    <div class="stat-sub">total sent</div>
  </div>
  <div class="stat-card" style="--accent:var(--gold)">
    <div class="stat-label">Stores</div>
    <div class="stat-value">{{ store_count }}</div>
    <div class="stat-sub">linked locations</div>
  </div>
  <div class="stat-card" style="--accent:{% if agg_over_short < 0 %}var(--red){% else %}var(--green){% endif %}">
    <div class="stat-label">Over / Short</div>
    <div class="stat-value {% if agg_over_short < 0 %}amount-neg{% else %}amount-pos{% endif %}">
      ${{ "%.2f"|format(agg_over_short) }}
    </div>
    <div class="stat-sub">daily reports</div>
  </div>
</div>

<!-- Per-store cards -->
{% if store_data %}
<div style="margin-bottom:12px;font-size:11px;font-weight:600;color:var(--gray4);text-transform:uppercase;letter-spacing:1px;">Locations</div>
<div style="display:grid;gap:16px;margin-bottom:32px;">
  {% for sd in store_data %}
  <div class="card">
    <div class="card-header">
      <div>
        <span class="card-title">{{ sd.store.name }}</span>
        {% if sd.store.plan == 'pro' %}
          <span class="badge badge-navy" style="margin-left:8px;">Pro</span>
        {% elif sd.store.plan == 'basic' %}
          <span class="badge badge-blue" style="margin-left:8px;">Basic</span>
        {% else %}
          <span class="badge badge-gray" style="margin-left:8px;">Trial</span>
        {% endif %}
      </div>
      <form method="POST" action="{{ url_for('owner_unlink_store', store_id=sd.store.id) }}"
            onsubmit="return confirm('Remove {{ sd.store.name }} from your account?')">
        <button type="submit" class="btn btn-sm" style="color:var(--red);border-color:var(--red);background:transparent;">Unlink</button>
      </form>
    </div>
    <div class="card-body">
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:16px;">
        <div>
          <div class="text-muted text-sm">Transfers</div>
          <div style="font-size:22px;font-family:'DM Serif Display',serif;color:var(--navy);margin-top:4px;">{{ sd.transfer_count }}</div>
          <div class="text-muted text-sm">${{ "%.0f"|format(sd.volume) }} volume</div>
        </div>
        <div>
          <div class="text-muted text-sm">Receipts</div>
          <div style="font-size:22px;font-family:'DM Serif Display',serif;color:var(--navy);margin-top:4px;">${{ "%.0f"|format(sd.total_receipts) }}</div>
          <div class="text-muted text-sm">daily reports</div>
        </div>
        <div>
          <div class="text-muted text-sm">Over/Short</div>
          <div style="font-size:22px;font-family:'DM Serif Display',serif;margin-top:4px;"
               class="{% if sd.over_short < 0 %}amount-neg{% else %}amount-pos{% endif %}">
            ${{ "%.2f"|format(sd.over_short) }}
          </div>
        </div>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<div class="card" style="max-width:560px;margin-bottom:32px;">
  <div class="card-body" style="text-align:center;padding:40px 24px;">
    <div style="font-size:32px;margin-bottom:12px;">&#127970;</div>
    <div style="font-family:'DM Serif Display',serif;font-size:20px;color:var(--navy);margin-bottom:8px;">No stores connected yet</div>
    <div style="font-size:13.5px;color:var(--gray4);">Enter an invite code from your store manager to connect your first store.</div>
  </div>
</div>
{% endif %}

<!-- Code entry form (always shown) -->
<div class="card" style="max-width:480px;">
  <div class="card-header"><span class="card-title">Connect a Store</span></div>
  <div class="card-body">
    <p style="font-size:13px;color:var(--gray4);margin-bottom:16px;">
      Enter the 8-character invite code from your store manager.
    </p>
    <form method="POST" action="{{ url_for('owner_link_store') }}" style="display:flex;gap:10px;align-items:flex-end;">
      <div class="field" style="flex:1;margin-bottom:0;">
        <label>Invite Code</label>
        <input type="text" name="code" placeholder="e.g. AB12CD34" maxlength="8"
               style="text-transform:uppercase;font-family:'JetBrains Mono',monospace;letter-spacing:2px;" required>
      </div>
      <button type="submit" class="btn btn-primary">Connect</button>
    </form>
  </div>
</div>

{% endblock %}
```

- [ ] **Step 6: Run dashboard tests**

```
python -m pytest tests/test_multi_store_owner.py -k "dashboard" -v
```

Expected: 6 PASS

- [ ] **Step 7: Run full suite**

```
python -m pytest --tb=short -q
```

Expected: all existing tests pass

- [ ] **Step 8: Commit**

```bash
git add app.py templates/base_owner.html templates/owner_dashboard.html
git commit -m "feat: owner dashboard with aggregate stats, period filter, and per-store cards"
```

---

### Task 5: `owner_link_store` and `owner_unlink_store` routes

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_multi_store_owner.py`:

```python
@pytest.fixture
def owner_with_store_client():
    """Returns (client, owner_id, store_id) with owner linked to test-store."""
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink, OwnerInviteCode
        from datetime import datetime, timedelta
        o = User(username="owner2@test.com", full_name="Owner2", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.flush()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink(owner_id=o.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
        oid, sid = o.id, store.id
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return c, oid, sid


def _make_valid_invite(store_id, admin_id):
    from app import OwnerInviteCode
    from datetime import datetime, timedelta
    invite = OwnerInviteCode(
        store_id=store_id,
        code="TESTCD01",
        created_by=admin_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def test_valid_code_links_owner_to_store(owner_client):
    with flask_app.app_context():
        from app import User, Store
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        _make_valid_invite(store.id, admin.id)
    rv = owner_client.post("/owner/link", data={"code": "TESTCD01"})
    assert rv.status_code == 302
    assert "owner/dashboard" in rv.headers["Location"]
    with flask_app.app_context():
        from app import User, StoreOwnerLink, Store
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink.query.filter_by(owner_id=owner.id, store_id=store.id).first()
        assert link is not None


def test_valid_code_marks_invite_used(owner_client):
    with flask_app.app_context():
        from app import User, Store, OwnerInviteCode
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        _make_valid_invite(store.id, admin.id)
    owner_client.post("/owner/link", data={"code": "TESTCD01"})
    with flask_app.app_context():
        from app import OwnerInviteCode
        invite = OwnerInviteCode.query.filter_by(code="TESTCD01").first()
        assert invite.used_at is not None


def test_expired_code_rejected(owner_client):
    with flask_app.app_context():
        from app import User, Store, OwnerInviteCode
        from datetime import datetime, timedelta
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        invite = OwnerInviteCode(
            store_id=store.id, code="EXPIRED1", created_by=admin.id,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(invite)
        db.session.commit()
    rv = owner_client.post("/owner/link", data={"code": "EXPIRED1"}, follow_redirects=True)
    assert b"expired" in rv.data.lower() or b"invalid" in rv.data.lower()


def test_used_code_rejected(owner_client):
    with flask_app.app_context():
        from app import User, Store, OwnerInviteCode
        from datetime import datetime, timedelta
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        invite = OwnerInviteCode(
            store_id=store.id, code="USED0001", created_by=admin.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
            used_at=datetime.utcnow(),
        )
        db.session.add(invite)
        db.session.commit()
    rv = owner_client.post("/owner/link", data={"code": "USED0001"}, follow_redirects=True)
    assert b"expired" in rv.data.lower() or b"invalid" in rv.data.lower()


def test_invalid_code_rejected(owner_client):
    rv = owner_client.post("/owner/link", data={"code": "BADCODE1"}, follow_redirects=True)
    assert b"invalid" in rv.data.lower() or b"expired" in rv.data.lower()


def test_already_linked_handled_gracefully(owner_client):
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink, OwnerInviteCode
        from datetime import datetime, timedelta
        store = Store.query.filter_by(slug="test-store").first()
        admin = User.query.filter_by(username="admin@test.com").first()
        owner = User.query.filter_by(username="owner@dashboard.com").first()
        existing = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        db.session.add(existing)
        invite = OwnerInviteCode(
            store_id=store.id, code="LINKDUP1", created_by=admin.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(invite)
        db.session.commit()
    rv = owner_client.post("/owner/link", data={"code": "LINKDUP1"}, follow_redirects=True)
    assert rv.status_code == 200
    assert b"already connected" in rv.data.lower()


def test_owner_can_unlink_store(owner_with_store_client):
    c, oid, sid = owner_with_store_client
    rv = c.post(f"/owner/unlink/{sid}")
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import StoreOwnerLink
        link = StoreOwnerLink.query.filter_by(owner_id=oid, store_id=sid).first()
        assert link is None


def test_unlink_nonexistent_returns_404(owner_client):
    rv = owner_client.post("/owner/unlink/99999")
    assert rv.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_multi_store_owner.py -k "link or unlink" -v
```

Expected: FAIL (routes do not exist)

- [ ] **Step 3: Add routes to `app.py`**

Add after the `owner_dashboard` route:

```python
@app.route("/owner/link", methods=["POST"])
@owner_required
def owner_link_store():
    u = current_user()
    code = request.form.get("code", "").strip().upper()
    now = datetime.utcnow()
    invite = OwnerInviteCode.query.filter(
        OwnerInviteCode.code == code,
        OwnerInviteCode.used_at.is_(None),
        OwnerInviteCode.expires_at > now
    ).first()
    if not invite:
        flash("Invalid or expired code.", "error")
        return redirect(url_for("owner_dashboard"))
    already = StoreOwnerLink.query.filter_by(owner_id=u.id, store_id=invite.store_id).first()
    if already:
        flash("You're already connected to this store.", "info")
        return redirect(url_for("owner_dashboard"))
    link = StoreOwnerLink(owner_id=u.id, store_id=invite.store_id)
    invite.used_at = now
    invite.used_by_owner_id = u.id
    db.session.add(link)
    db.session.commit()
    store = Store.query.get(invite.store_id)
    flash(f"{store.name} connected successfully.", "success")
    return redirect(url_for("owner_dashboard"))


@app.route("/owner/unlink/<int:store_id>", methods=["POST"])
@owner_required
def owner_unlink_store(store_id):
    u = current_user()
    link = StoreOwnerLink.query.filter_by(owner_id=u.id, store_id=store_id).first_or_404()
    db.session.delete(link)
    db.session.commit()
    flash("Store removed from your account.", "success")
    return redirect(url_for("owner_dashboard"))
```

- [ ] **Step 4: Run link/unlink tests**

```
python -m pytest tests/test_multi_store_owner.py -k "link or unlink" -v
```

Expected: 9 PASS

- [ ] **Step 5: Run full suite**

```
python -m pytest --tb=short -q
```

Expected: all existing tests pass

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: owner link and unlink store routes"
```

---

### Task 6: Admin Owner Access tab — generate/remove code routes + settings template update

**Files:**
- Modify: `app.py` (add `admin_generate_owner_code`, `admin_remove_owner_access`, update `admin_settings`)
- Modify: `templates/admin_settings.html`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_multi_store_owner.py`:

```python
def test_admin_generate_owner_code(logged_in_client):
    rv = logged_in_client.post("/admin/settings/owner/generate-code")
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import Store, OwnerInviteCode
        store = Store.query.filter_by(slug="test-store").first()
        code = OwnerInviteCode.query.filter_by(store_id=store.id).first()
        assert code is not None
        assert len(code.code) == 8
        assert code.code == code.code.upper()
        assert code.used_at is None


def test_generate_code_invalidates_previous(logged_in_client):
    logged_in_client.post("/admin/settings/owner/generate-code")
    logged_in_client.post("/admin/settings/owner/generate-code")
    with flask_app.app_context():
        from app import Store, OwnerInviteCode
        from datetime import datetime
        store = Store.query.filter_by(slug="test-store").first()
        active = OwnerInviteCode.query.filter(
            OwnerInviteCode.store_id == store.id,
            OwnerInviteCode.used_at.is_(None),
            OwnerInviteCode.expires_at > datetime.utcnow()
        ).all()
        assert len(active) == 1


def test_code_has_7_day_expiry(logged_in_client):
    from datetime import datetime, timedelta
    logged_in_client.post("/admin/settings/owner/generate-code")
    with flask_app.app_context():
        from app import Store, OwnerInviteCode
        store = Store.query.filter_by(slug="test-store").first()
        code = OwnerInviteCode.query.filter_by(store_id=store.id).order_by(OwnerInviteCode.created_at.desc()).first()
        delta = code.expires_at - code.created_at
        assert 6 <= delta.days <= 7


def test_admin_owner_access_tab_shows_no_code_state(logged_in_client):
    rv = logged_in_client.get("/admin/settings?tab=owner")
    assert rv.status_code == 200
    assert b"Generate" in rv.data or b"generate" in rv.data


def test_admin_owner_access_tab_shows_active_code(logged_in_client):
    logged_in_client.post("/admin/settings/owner/generate-code")
    rv = logged_in_client.get("/admin/settings?tab=owner")
    assert rv.status_code == 200


def test_admin_remove_owner_access(logged_in_client):
    with flask_app.app_context():
        from app import User, Store, StoreOwnerLink
        store = Store.query.filter_by(slug="test-store").first()
        o = User(username="owner3@test.com", full_name="Owner3", role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.flush()
        link = StoreOwnerLink(owner_id=o.id, store_id=store.id)
        db.session.add(link)
        db.session.commit()
        oid = o.id
    rv = logged_in_client.post("/admin/settings/owner/remove-access", data={"owner_id": oid})
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import Store, StoreOwnerLink
        store = Store.query.filter_by(slug="test-store").first()
        link = StoreOwnerLink.query.filter_by(store_id=store.id, owner_id=oid).first()
        assert link is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_multi_store_owner.py -k "admin" -v
```

Expected: FAIL (routes not yet present)

- [ ] **Step 3: Add `admin_generate_owner_code` and `admin_remove_owner_access` routes to `app.py`**

Add after `admin_reset_employee_password` (after the `# ── Superadmin ──` comment or just before it):

```python
@app.route("/admin/settings/owner/generate-code", methods=["POST"])
@admin_required
def admin_generate_owner_code():
    store = current_store()
    now = datetime.utcnow()
    OwnerInviteCode.query.filter(
        OwnerInviteCode.store_id == store.id,
        OwnerInviteCode.used_at.is_(None),
        OwnerInviteCode.expires_at > now
    ).update({"expires_at": now})
    db.session.flush()
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not OwnerInviteCode.query.filter_by(code=code).first():
            break
    invite = OwnerInviteCode(
        store_id=store.id,
        code=code,
        created_by=current_user().id,
        expires_at=now + timedelta(days=7),
    )
    db.session.add(invite)
    db.session.commit()
    flash("Invite code generated.", "success")
    return redirect(url_for("admin_settings", tab="owner"))


@app.route("/admin/settings/owner/remove-access", methods=["POST"])
@admin_required
def admin_remove_owner_access():
    store = current_store()
    owner_id = request.form.get("owner_id", type=int)
    if owner_id:
        StoreOwnerLink.query.filter_by(store_id=store.id, owner_id=owner_id).delete()
        db.session.commit()
        flash("Owner access removed.", "success")
    return redirect(url_for("admin_settings", tab="owner"))
```

- [ ] **Step 4: Update `admin_settings` route in `app.py` to pass owner-tab context**

Find the `return render_template("admin_settings.html", ...)` call near the end of `admin_settings()`. Replace it with:

```python
    now = datetime.utcnow()
    owner_invite = OwnerInviteCode.query.filter(
        OwnerInviteCode.store_id == store.id,
        OwnerInviteCode.used_at.is_(None),
        OwnerInviteCode.expires_at > now
    ).order_by(OwnerInviteCode.created_at.desc()).first()

    owner_link = StoreOwnerLink.query.filter_by(store_id=store.id).first()
    owner_user = User.query.get(owner_link.owner_id) if owner_link else None

    return render_template("admin_settings.html",
        user=user, store=store,
        active_tab=active_tab, errors=errors,
        employees=employees,
        owner_invite=owner_invite,
        owner_link=owner_link,
        owner_user=owner_user,
    )
```

- [ ] **Step 5: Add "Owner Access" tab to `templates/admin_settings.html`**

**5a.** In the tab bar, add the Owner Access tab. Find:
```html
  <a href="{{ url_for('admin_settings', tab='team') }}"
     class="tab-link {% if active_tab == 'team' %}active{% endif %}">Team</a>
</div>
```

Replace with:
```html
  <a href="{{ url_for('admin_settings', tab='team') }}"
     class="tab-link {% if active_tab == 'team' %}active{% endif %}">Team</a>
  <a href="{{ url_for('admin_settings', tab='owner') }}"
     class="tab-link {% if active_tab == 'owner' %}active{% endif %}">Owner Access</a>
</div>
```

**5b.** Add the owner tab content block. Find:
```html
{% endif %}

{% endblock %}
{% block scripts %}
```

Replace with:
```html
{% elif active_tab == 'owner' %}
<div class="card" style="max-width:560px;">
  <div class="card-header"><span class="card-title">Owner Access</span></div>
  <div class="card-body">

    {% if owner_link and owner_user %}
    <!-- State: owner linked -->
    <div style="margin-bottom:20px;padding:16px;background:var(--gray1);border-radius:8px;border:1px solid var(--gray2);">
      <div style="font-size:13px;font-weight:600;color:var(--navy);">{{ owner_user.full_name or owner_user.username }}</div>
      <div style="font-size:12px;color:var(--gray4);margin-top:3px;">{{ owner_user.username }} has access to this store.</div>
    </div>
    <form method="POST" action="{{ url_for('admin_remove_owner_access') }}"
          onsubmit="return confirm('Remove owner access for {{ owner_user.full_name or owner_user.username }}?')">
      <input type="hidden" name="owner_id" value="{{ owner_user.id }}">
      <button type="submit" class="btn btn-danger btn-sm">Remove Access</button>
    </form>

    {% elif owner_invite %}
    <!-- State: active unused code -->
    <p style="font-size:13px;color:var(--gray4);margin-bottom:16px;">
      Share this code with your store owner. It expires on {{ owner_invite.expires_at.strftime('%b %d, %Y') }}.
    </p>
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:20px;">
      <input type="text" id="owner-code" value="{{ owner_invite.code }}" readonly
             style="flex:1;background:var(--gray1);font-family:'JetBrains Mono',monospace;font-size:18px;letter-spacing:3px;font-weight:600;text-align:center;">
      <button type="button" class="btn btn-outline btn-sm" onclick="copyOwnerCode()">Copy</button>
    </div>
    <form method="POST" action="{{ url_for('admin_generate_owner_code') }}">
      <button type="submit" class="btn btn-outline btn-sm">Generate New Code</button>
    </form>

    {% else %}
    <!-- State: no code, no owner -->
    <p style="font-size:13px;color:var(--gray4);margin-bottom:20px;">
      Generate an invite code to share with your store owner. The code is valid for 7 days.
    </p>
    <form method="POST" action="{{ url_for('admin_generate_owner_code') }}">
      <button type="submit" class="btn btn-primary">Generate Invite Code</button>
    </form>
    {% endif %}

  </div>
</div>
{% endif %}

{% endblock %}
{% block scripts %}
```

- [ ] **Step 6: Add `copyOwnerCode` JS function to the scripts block**

In the `{% block scripts %}` section at the bottom, add `copyOwnerCode` after the existing functions:

```javascript
function copyOwnerCode() {
  var el = document.getElementById('owner-code');
  el.select();
  document.execCommand('copy');
  alert('Invite code copied!');
}
```

- [ ] **Step 7: Run admin tests**

```
python -m pytest tests/test_multi_store_owner.py -k "admin" -v
```

Expected: 6 PASS

- [ ] **Step 8: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: all tests pass (existing + new owner tests)

- [ ] **Step 9: Commit**

```bash
git add app.py templates/admin_settings.html
git commit -m "feat: admin Owner Access tab with invite code generation and access removal"
```

---

### Task 7: Final integration verification

- [ ] **Step 1: Run full test suite one final time**

```
python -m pytest -v
```

Expected: all tests pass (58 existing + new owner tests ~30+)

- [ ] **Step 2: Confirm test count**

```
python -m pytest --co -q
```

Review output — ensure `tests/test_multi_store_owner.py` tests are all collected.

- [ ] **Step 3: Push to remote**

```bash
git push origin main
```
