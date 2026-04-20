# Account Management & Secure Employee Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a store-scoped employee login URL, restrict main `/login` to admins only, and build a tabbed `/admin/settings` page covering Store Info, Security (password change), and Team (employee password resets).

**Architecture:** All new routes are added to `app.py` following the existing single-file Flask pattern. Three new templates are created. No schema changes required — `Store` and `User` models already have all needed fields. `re` is added to existing imports for email validation.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, pytest-flask, in-memory SQLite for tests.

---

## File Structure

| File | Change |
|---|---|
| `app.py` | Add `import re`. Add `login_store` route. Modify `login` route to block employees. Add `admin_settings` route. Add `admin_reset_employee_password` route. |
| `templates/login_store.html` | Create — standalone employee login page scoped to a store. |
| `templates/admin_settings.html` | Create — tabbed settings page (Store Info / Security / Team). |
| `templates/base.html` | Add "Settings" nav link for admin role (pointing to `/admin/settings`). |
| `tests/test_account_management.py` | Create — all tests for this feature. |

---

## Task 1: Store-Scoped Employee Login (`/login/<slug>`)

**Files:**
- Modify: `app.py` (add `import re`, add `login_store` route after the `login` route)
- Create: `templates/login_store.html`
- Test: `tests/test_account_management.py`

- [ ] **Step 1: Create the test file with failing tests**

Create `tests/test_account_management.py`:

```python
import pytest
from app import app as flask_app, db


def make_employee(client, store_id, username="cashier", password="emppass123!"):
    """Helper: create an employee for the given store_id."""
    with flask_app.app_context():
        from app import User
        e = User(store_id=store_id, username=username,
                 full_name="Test Cashier", role="employee")
        e.set_password(password)
        db.session.add(e)
        db.session.commit()
        return e.id


def get_store_id(slug="test-store"):
    with flask_app.app_context():
        from app import Store
        return Store.query.filter_by(slug=slug).first().id


# ── Task 1: /login/<slug> ─────────────────────────────────────

def test_employee_login_with_valid_credentials(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/login/test-store", data={
        "username": "cashier",
        "password": "emppass123!"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


def test_employee_login_wrong_password(client):
    sid = get_store_id()
    make_employee(client, sid)
    resp = client.post("/login/test-store", data={
        "username": "cashier",
        "password": "wrongpassword"
    })
    assert resp.status_code == 200
    assert b"Invalid username or password" in resp.data


def test_employee_login_unknown_slug_returns_404(client):
    resp = client.get("/login/no-such-store")
    assert resp.status_code == 404


def test_employee_login_get_page_shows_store_context(client):
    resp = client.get("/login/test-store")
    assert resp.status_code == 200
    assert b"Test Store" in resp.data or b"test-store" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_account_management.py::test_employee_login_with_valid_credentials tests/test_account_management.py::test_employee_login_wrong_password tests/test_account_management.py::test_employee_login_unknown_slug_returns_404 tests/test_account_management.py::test_employee_login_get_page_shows_store_context -v
```

Expected: FAIL with 404 (route not yet defined).

- [ ] **Step 3: Add `import re` to app.py**

In `app.py`, find the existing imports line:

```python
import requests, base64, os, calendar, logging
```

Change it to:

```python
import requests, base64, os, calendar, logging, re
```

- [ ] **Step 4: Add the `login_store` route to app.py**

In `app.py`, after the `login` route (after line `return render_template("login.html",error=error)`), add:

```python
@app.route("/login/<slug>", methods=["GET", "POST"])
def login_store(slug):
    store = Store.query.filter_by(slug=slug).first_or_404()
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        u = User.query.filter_by(username=username, store_id=store.id).first()
        if u and u.is_active and u.check_password(request.form.get("password", "")):
            session["user_id"] = u.id
            session["role"] = u.role
            session["store_id"] = u.store_id
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login_store.html", store=store, error=error)
```

- [ ] **Step 5: Create `templates/login_store.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ store.name }} — Sign In</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'DM Sans', sans-serif;
  background: #0f1f3d;
  min-height: 100vh; display: flex;
}
.login-left {
  flex: 1; display: flex; flex-direction: column;
  justify-content: center; align-items: center;
  padding: 60px;
  background: linear-gradient(145deg, #0f1f3d 0%, #1a3a6e 100%);
  position: relative; overflow: hidden;
}
.login-left::before {
  content: '';
  position: absolute; width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(201,151,58,0.12) 0%, transparent 70%);
  top: -100px; right: -100px; pointer-events: none;
}
.brand-block { text-align: center; position: relative; z-index: 1; }
.brand-icon { font-size: 52px; margin-bottom: 20px; }
.brand-name {
  font-family: 'DM Serif Display', serif;
  font-size: 36px; color: #f0c060;
  letter-spacing: 1px; line-height: 1;
}
.brand-store {
  font-size: 14px; color: rgba(255,255,255,0.55);
  margin-top: 8px; letter-spacing: 0.5px;
}
.brand-tagline {
  font-size: 12px; color: rgba(255,255,255,0.35);
  margin-top: 6px; letter-spacing: 1.5px; text-transform: uppercase;
}
.login-right {
  width: 440px; background: #faf7f2;
  display: flex; flex-direction: column;
  justify-content: center; padding: 60px 48px;
}
.login-heading {
  font-family: 'DM Serif Display', serif;
  font-size: 28px; color: #0f1f3d; margin-bottom: 8px;
}
.login-sub { font-size: 14px; color: #6b7280; margin-bottom: 36px; }
.field { display: flex; flex-direction: column; gap: 7px; margin-bottom: 18px; }
label { font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.7px; }
input {
  padding: 12px 16px; border: 1.5px solid #e8e8ec; border-radius: 9px;
  font-size: 15px; font-family: 'DM Sans', sans-serif; color: #1a1a2e;
  background: #fff; transition: border-color 0.15s; width: 100%;
}
input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
.error-msg {
  background: #fee2e2; color: #b91c1c;
  border: 1px solid #fecaca; border-radius: 8px;
  padding: 11px 16px; font-size: 13.5px; margin-bottom: 18px;
}
.btn-login {
  width: 100%; padding: 13px;
  background: #1a4080; color: #fff;
  border: none; border-radius: 9px;
  font-size: 15px; font-weight: 600;
  font-family: 'DM Sans', sans-serif;
  cursor: pointer; transition: background 0.15s; margin-top: 6px;
}
.btn-login:hover { background: #2a5caa; }
.login-footer { margin-top: 40px; font-size: 12px; color: #9ca3af; text-align: center; }
</style>
</head>
<body>
<div class="login-left">
  <div class="brand-block">
    <div class="brand-icon">💱</div>
    <div class="brand-name">Cambio Express</div>
    <div class="brand-store">{{ store.name }}</div>
    <div class="brand-tagline">Employee Portal</div>
  </div>
</div>
<div class="login-right">
  <div class="login-heading">Employee Sign In</div>
  <div class="login-sub">Sign in to {{ store.name }}</div>
  {% if error %}
  <div class="error-msg">{{ error }}</div>
  {% endif %}
  <form method="POST">
    <div class="field">
      <label>Username</label>
      <input type="text" name="username" placeholder="Enter your username" autofocus required>
    </div>
    <div class="field">
      <label>Password</label>
      <input type="password" name="password" placeholder="Enter your password" required>
    </div>
    <button type="submit" class="btn-login">Sign In →</button>
  </form>
  <div class="login-footer">{{ store.name }} · Cambio Express</div>
</div>
</body>
</html>
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_account_management.py::test_employee_login_with_valid_credentials tests/test_account_management.py::test_employee_login_wrong_password tests/test_account_management.py::test_employee_login_unknown_slug_returns_404 tests/test_account_management.py::test_employee_login_get_page_shows_store_context -v
```

Expected: 4 PASSED.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/login_store.html tests/test_account_management.py
git commit -m "feat: store-scoped employee login at /login/<slug>"
```

---

## Task 2: Restrict Main `/login` to Admin and Superadmin Roles

**Files:**
- Modify: `app.py` (login route, lines ~377–388)
- Test: `tests/test_account_management.py` (append tests)

- [ ] **Step 1: Add failing tests to `tests/test_account_management.py`**

Append to the file:

```python
# ── Task 2: main /login restricted to admin/superadmin ───────

def test_employee_blocked_on_main_login(client):
    sid = get_store_id()
    make_employee(client, sid, username="blockeduser", password="emppass123!")
    resp = client.post("/login", data={
        "username": "blockeduser",
        "password": "emppass123!"
    })
    assert resp.status_code == 200
    assert b"store" in resp.data.lower()
    # must NOT have set session (not redirected to dashboard)
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_admin_can_still_use_main_login(client):
    resp = client.post("/login", data={
        "username": "admin@test.com",
        "password": "testpass123!"
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_account_management.py::test_employee_blocked_on_main_login tests/test_account_management.py::test_admin_can_still_use_main_login -v
```

Expected: `test_employee_blocked_on_main_login` FAILS (employee currently logs in successfully), `test_admin_can_still_use_main_login` PASSES.

- [ ] **Step 3: Modify the `login` route in app.py**

Find this block in `app.py`:

```python
        if u and u.is_active and u.check_password(request.form.get("password","")):
            session["user_id"]=u.id; session["role"]=u.role; session["store_id"]=u.store_id
            return redirect(url_for("dashboard"))
        error="Invalid username or password."
```

Replace it with:

```python
        if u and u.is_active and u.check_password(request.form.get("password","")):
            if u.role == "employee":
                error = "Please use your store's login link."
            else:
                session["user_id"]=u.id; session["role"]=u.role; session["store_id"]=u.store_id
                return redirect(url_for("dashboard"))
        else:
            error="Invalid username or password."
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_account_management.py::test_employee_blocked_on_main_login tests/test_account_management.py::test_admin_can_still_use_main_login -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_account_management.py
git commit -m "feat: restrict main /login to admin and superadmin roles"
```

---

## Task 3: Settings Page + Store Info Tab

**Files:**
- Modify: `app.py` (add `admin_settings` route)
- Create: `templates/admin_settings.html`
- Test: `tests/test_account_management.py` (append tests)

- [ ] **Step 1: Add failing tests to `tests/test_account_management.py`**

Append:

```python
# ── Task 3: /admin/settings — Store Info tab ─────────────────

def test_settings_page_loads(logged_in_client):
    resp = logged_in_client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"Settings" in resp.data
    assert b"Store Info" in resp.data


def test_settings_store_info_updates_store(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Updated Store Name",
        "email": "updated@test.com",
        "phone": "555-9999"
    }, follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert s.name == "Updated Store Name"
        assert s.email == "updated@test.com"
        assert s.phone == "555-9999"


def test_settings_store_info_updates_admin_username(logged_in_client):
    logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Test Store",
        "email": "newemail@test.com",
        "phone": ""
    }, follow_redirects=True)
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="newemail@test.com").first()
        assert u is not None
        assert u.role == "admin"


def test_settings_store_info_rejects_blank_name(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "",
        "email": "admin@test.com",
        "phone": ""
    })
    assert resp.status_code == 200
    assert b"required" in resp.data.lower() or b"name" in resp.data.lower()
    with flask_app.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert s.name == "Test Store"  # unchanged


def test_settings_store_info_rejects_duplicate_email(logged_in_client, client):
    # Create a second store with a different admin email
    client.post("/signup", data={
        "store_name": "Other Store",
        "email": "other@example.com",
        "password": "securepass1!",
        "phone": ""
    })
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Test Store",
        "email": "other@example.com",
        "phone": ""
    })
    assert resp.status_code == 200
    assert b"already registered" in resp.data.lower() or b"already" in resp.data.lower()
    with flask_app.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert s.email == "admin@test.com"  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_account_management.py::test_settings_page_loads tests/test_account_management.py::test_settings_store_info_updates_store tests/test_account_management.py::test_settings_store_info_updates_admin_username tests/test_account_management.py::test_settings_store_info_rejects_blank_name tests/test_account_management.py::test_settings_store_info_rejects_duplicate_email -v
```

Expected: all FAIL with 404 (route not yet defined).

- [ ] **Step 3: Add the `admin_settings` route to app.py**

In `app.py`, after the `admin_edit_user` route, add:

```python
@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    user = current_user()
    store = current_store()
    active_tab = request.args.get("tab", "store")
    errors = {}

    if request.method == "POST":
        form_tab = request.form.get("_tab", "store")
        active_tab = form_tab

        if form_tab == "store":
            name = request.form.get("store_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()

            if not name:
                errors["store_name"] = "Store name is required."
            if not email:
                errors["email"] = "Email is required."
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                errors["email"] = "Enter a valid email address."
            if not errors:
                taken = User.query.filter(
                    User.username == email,
                    User.role == "admin",
                    User.store_id != store.id
                ).first()
                if taken:
                    errors["email"] = "That email is already registered to another account."

            if not errors:
                store.name = name
                store.email = email
                store.phone = phone
                user.username = email
                db.session.commit()
                flash("Store info updated.", "success")
                return redirect(url_for("admin_settings", tab="store"))

        elif form_tab == "security":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")

            if not user.check_password(current_pw):
                errors["current_password"] = "Current password is incorrect."
            elif len(new_pw) < 8:
                errors["new_password"] = "Password must be at least 8 characters."
            elif new_pw != confirm_pw:
                errors["confirm_password"] = "Passwords do not match."

            if not errors:
                user.set_password(new_pw)
                db.session.commit()
                flash("Password updated.", "success")
                return redirect(url_for("admin_settings", tab="security"))

    employees = User.query.filter(
        User.store_id == store.id,
        User.id != user.id
    ).order_by(User.full_name).all()

    return render_template("admin_settings.html",
        user=user, store=store,
        active_tab=active_tab, errors=errors,
        employees=employees)
```

- [ ] **Step 4: Create `templates/admin_settings.html`**

```html
{% extends "base.html" %}
{% block title %}Settings — Cambio Express{% endblock %}
{% block page_title %}Settings{% endblock %}
{% block head %}
<style>
.tab-bar {
  display: flex; gap: 0; border-bottom: 2px solid var(--gray2);
  margin-bottom: 28px;
}
.tab-link {
  padding: 10px 20px; font-size: 13.5px; font-weight: 500;
  color: var(--gray4); text-decoration: none;
  border-bottom: 2px solid transparent; margin-bottom: -2px;
  transition: all 0.15s;
}
.tab-link:hover { color: var(--navy); }
.tab-link.active { color: var(--navy); border-bottom-color: var(--blue); font-weight: 600; }
.field-error { font-size: 12px; color: var(--red); margin-top: 3px; }
</style>
{% endblock %}
{% block content %}

<div class="tab-bar">
  <a href="{{ url_for('admin_settings', tab='store') }}"
     class="tab-link {% if active_tab == 'store' %}active{% endif %}">Store Info</a>
  <a href="{{ url_for('admin_settings', tab='security') }}"
     class="tab-link {% if active_tab == 'security' %}active{% endif %}">Security</a>
  <a href="{{ url_for('admin_settings', tab='team') }}"
     class="tab-link {% if active_tab == 'team' %}active{% endif %}">Team</a>
</div>

{% if active_tab == 'store' %}
<div class="card" style="max-width:560px;">
  <div class="card-header"><span class="card-title">Store Info</span></div>
  <div class="card-body">
    <form method="POST">
      <input type="hidden" name="_tab" value="store">
      <div class="form-grid cols-1">
        <div class="field">
          <label>Store Name *</label>
          <input type="text" name="store_name" value="{{ store.name }}" required>
          {% if errors.store_name %}<div class="field-error">{{ errors.store_name }}</div>{% endif %}
        </div>
        <div class="field">
          <label>Contact Email *</label>
          <input type="email" name="email" value="{{ store.email }}">
          {% if errors.email %}<div class="field-error">{{ errors.email }}</div>{% endif %}
          <div style="font-size:11px;color:var(--gray4);margin-top:3px;">
            This is also your login username. Changing it takes effect immediately.
          </div>
        </div>
        <div class="field">
          <label>Phone</label>
          <input type="text" name="phone" value="{{ store.phone }}" placeholder="Optional">
        </div>
      </div>
      <div style="margin-top:24px;">
        <button type="submit" class="btn btn-primary">💾 Save Changes</button>
      </div>
    </form>
  </div>
</div>

{% elif active_tab == 'security' %}
<div class="card" style="max-width:480px;">
  <div class="card-header"><span class="card-title">Change Password</span></div>
  <div class="card-body">
    <form method="POST">
      <input type="hidden" name="_tab" value="security">
      <div class="form-grid cols-1">
        <div class="field">
          <label>Current Password *</label>
          <input type="password" name="current_password" required>
          {% if errors.current_password %}<div class="field-error">{{ errors.current_password }}</div>{% endif %}
        </div>
        <div class="field">
          <label>New Password *</label>
          <input type="password" name="new_password" placeholder="Min 8 characters" required>
          {% if errors.new_password %}<div class="field-error">{{ errors.new_password }}</div>{% endif %}
        </div>
        <div class="field">
          <label>Confirm New Password *</label>
          <input type="password" name="confirm_password" required>
          {% if errors.confirm_password %}<div class="field-error">{{ errors.confirm_password }}</div>{% endif %}
        </div>
      </div>
      <div style="margin-top:24px;">
        <button type="submit" class="btn btn-primary">🔒 Update Password</button>
      </div>
    </form>
  </div>
</div>

{% elif active_tab == 'team' %}
{% set login_url = url_for('login_store', slug=store.slug, _external=True) %}
<div class="card mb-3" style="max-width:700px;">
  <div class="card-header"><span class="card-title">Employee Login Link</span></div>
  <div class="card-body">
    <div style="font-size:13px;color:var(--gray4);margin-bottom:10px;">
      Share this link with your employees so they can sign in:
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <input type="text" id="emp-url" value="{{ login_url }}" readonly
        style="flex:1;background:var(--gray1);color:var(--dark);font-family:'JetBrains Mono',monospace;font-size:13px;">
      <button type="button" class="btn btn-outline btn-sm" onclick="copyLoginUrl()">Copy</button>
    </div>
  </div>
</div>

<div class="card" style="max-width:700px;">
  <div class="card-header">
    <span class="card-title">Employees</span>
    <a href="{{ url_for('admin_new_user') }}" class="btn btn-primary btn-sm">＋ Add Employee</a>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Full Name</th><th>Username</th><th>Role</th><th>Status</th><th>Reset Password</th>
        </tr>
      </thead>
      <tbody>
        {% for emp in employees %}
        <tr>
          <td>{{ emp.full_name or '—' }}</td>
          <td class="mono">{{ emp.username }}</td>
          <td>
            {% if emp.role == 'admin' %}
            <span class="badge badge-navy">Admin</span>
            {% else %}
            <span class="badge badge-blue">Employee</span>
            {% endif %}
          </td>
          <td>
            {% if emp.is_active %}
            <span class="badge badge-green">Active</span>
            {% else %}
            <span class="badge badge-red">Inactive</span>
            {% endif %}
          </td>
          <td>
            <button type="button" class="btn btn-outline btn-sm"
              onclick="showReset({{ emp.id }}, '{{ emp.full_name or emp.username }}')">
              Reset
            </button>
          </td>
        </tr>
        {% endfor %}
        {% if not employees %}
        <tr><td colspan="5" style="text-align:center;color:var(--gray4);padding:24px;">
          No employees yet. Add one to get started.
        </td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>
</div>

<!-- Reset password modal -->
<div id="reset-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:200;align-items:center;justify-content:center;">
  <div style="background:var(--white);border-radius:12px;padding:32px;width:380px;box-shadow:0 20px 60px rgba(0,0,0,0.2);">
    <div style="font-family:'DM Serif Display',serif;font-size:20px;color:var(--navy);margin-bottom:6px;">Reset Password</div>
    <div id="reset-name" style="font-size:13px;color:var(--gray4);margin-bottom:20px;"></div>
    <form id="reset-form" method="POST">
      <div class="field" style="margin-bottom:14px;">
        <label>New Password</label>
        <input type="password" name="password" placeholder="Min 8 characters" required>
      </div>
      <div class="field" style="margin-bottom:20px;">
        <label>Confirm Password</label>
        <input type="password" name="confirm_password" placeholder="Repeat password" required>
      </div>
      <div style="display:flex;gap:10px;">
        <button type="submit" class="btn btn-primary">Set Password</button>
        <button type="button" class="btn btn-outline" onclick="closeReset()">Cancel</button>
      </div>
    </form>
  </div>
</div>
{% endif %}

{% endblock %}
{% block scripts %}
<script>
function copyLoginUrl() {
  var el = document.getElementById('emp-url');
  el.select();
  document.execCommand('copy');
  alert('Login link copied!');
}
function showReset(uid, name) {
  document.getElementById('reset-name').textContent = 'Setting new password for: ' + name;
  document.getElementById('reset-form').action = '/admin/settings/team/' + uid;
  var modal = document.getElementById('reset-modal');
  modal.style.display = 'flex';
}
function closeReset() {
  document.getElementById('reset-modal').style.display = 'none';
}
</script>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_account_management.py::test_settings_page_loads tests/test_account_management.py::test_settings_store_info_updates_store tests/test_account_management.py::test_settings_store_info_updates_admin_username tests/test_account_management.py::test_settings_store_info_rejects_blank_name tests/test_account_management.py::test_settings_store_info_rejects_duplicate_email -v
```

Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin_settings.html tests/test_account_management.py
git commit -m "feat: admin settings page with Store Info tab"
```

---

## Task 4: Security Tab (Admin Password Change)

**Files:**
- `app.py` already contains the security tab handler (added in Task 3).
- Test: `tests/test_account_management.py` (append tests)

- [ ] **Step 1: Add failing tests to `tests/test_account_management.py`**

Append:

```python
# ── Task 4: Security tab ─────────────────────────────────────

def test_security_wrong_current_password(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "security",
        "current_password": "wrongpassword",
        "new_password": "newpassword123!",
        "confirm_password": "newpassword123!"
    })
    assert resp.status_code == 200
    assert b"incorrect" in resp.data.lower()
    # verify old password still works
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="admin@test.com").first()
        assert u.check_password("testpass123!")


def test_security_new_password_too_short(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "security",
        "current_password": "testpass123!",
        "new_password": "short",
        "confirm_password": "short"
    })
    assert resp.status_code == 200
    assert b"8" in resp.data


def test_security_passwords_do_not_match(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "security",
        "current_password": "testpass123!",
        "new_password": "newpassword123!",
        "confirm_password": "differentpassword!"
    })
    assert resp.status_code == 200
    assert b"match" in resp.data.lower()


def test_security_valid_password_change(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "security",
        "current_password": "testpass123!",
        "new_password": "brandnew123!",
        "confirm_password": "brandnew123!"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"updated" in resp.data.lower()
    with flask_app.app_context():
        from app import User
        u = User.query.filter_by(username="admin@test.com").first()
        assert u.check_password("brandnew123!")
        assert not u.check_password("testpass123!")
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_account_management.py::test_security_wrong_current_password tests/test_account_management.py::test_security_new_password_too_short tests/test_account_management.py::test_security_passwords_do_not_match tests/test_account_management.py::test_security_valid_password_change -v
```

Expected: FAIL — the security tab POST is implemented but no `?tab=security` is sent, so tests should PASS or FAIL depending on template rendering. If any fail, the route was already wired in Task 3 — re-run to confirm.

- [ ] **Step 3: Run all security tests**

```
pytest tests/test_account_management.py::test_security_wrong_current_password tests/test_account_management.py::test_security_new_password_too_short tests/test_account_management.py::test_security_passwords_do_not_match tests/test_account_management.py::test_security_valid_password_change -v
```

Expected: 4 PASSED (route was already added in Task 3).

- [ ] **Step 4: Commit**

```bash
git add tests/test_account_management.py
git commit -m "test: security tab password change tests"
```

---

## Task 5: Team Tab + Employee Password Reset

**Files:**
- Modify: `app.py` (add `admin_reset_employee_password` route)
- Test: `tests/test_account_management.py` (append tests)

- [ ] **Step 1: Add failing tests to `tests/test_account_management.py`**

Append:

```python
# ── Task 5: Team tab + employee password reset ───────────────

def test_team_tab_loads_and_shows_employees(logged_in_client):
    sid = get_store_id()
    make_employee(logged_in_client, sid, username="emp1")
    resp = logged_in_client.get("/admin/settings?tab=team")
    assert resp.status_code == 200
    assert b"emp1" in resp.data or b"Test Cashier" in resp.data


def test_team_tab_shows_employee_login_url(logged_in_client):
    resp = logged_in_client.get("/admin/settings?tab=team")
    assert resp.status_code == 200
    assert b"login/test-store" in resp.data


def test_team_reset_employee_password(logged_in_client):
    sid = get_store_id()
    emp_id = make_employee(logged_in_client, sid, username="resetme", password="oldpass123!")
    resp = logged_in_client.post(f"/admin/settings/team/{emp_id}", data={
        "password": "newpass456!",
        "confirm_password": "newpass456!"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"updated" in resp.data.lower() or b"password" in resp.data.lower()
    with flask_app.app_context():
        from app import User
        emp = User.query.get(emp_id)
        assert emp.check_password("newpass456!")
        assert not emp.check_password("oldpass123!")


def test_team_reset_scoped_to_store(logged_in_client, client):
    # Create a second store and its employee
    client.post("/signup", data={
        "store_name": "Other Store",
        "email": "other2@example.com",
        "password": "securepass1!",
        "phone": ""
    })
    with flask_app.app_context():
        from app import Store, User
        other_store = Store.query.filter_by(email="other2@example.com").first()
        other_emp = User(store_id=other_store.id, username="otherworker",
                         full_name="Other Worker", role="employee")
        other_emp.set_password("original123!")
        db.session.add(other_emp)
        db.session.commit()
        other_emp_id = other_emp.id

    resp = logged_in_client.post(f"/admin/settings/team/{other_emp_id}", data={
        "password": "hacked123!!",
        "confirm_password": "hacked123!!"
    })
    # Should 404 because user is not in this admin's store
    assert resp.status_code == 404
    with flask_app.app_context():
        from app import User
        emp = User.query.get(other_emp_id)
        assert emp.check_password("original123!")


def test_team_reset_password_too_short(logged_in_client):
    sid = get_store_id()
    emp_id = make_employee(logged_in_client, sid, username="shortpw")
    resp = logged_in_client.post(f"/admin/settings/team/{emp_id}", data={
        "password": "short",
        "confirm_password": "short"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"8" in resp.data


def test_team_reset_passwords_do_not_match(logged_in_client):
    sid = get_store_id()
    emp_id = make_employee(logged_in_client, sid, username="mismatch")
    resp = logged_in_client.post(f"/admin/settings/team/{emp_id}", data={
        "password": "newpass123!",
        "confirm_password": "different123!"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"match" in resp.data.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_account_management.py::test_team_tab_loads_and_shows_employees tests/test_account_management.py::test_team_tab_shows_employee_login_url tests/test_account_management.py::test_team_reset_employee_password tests/test_account_management.py::test_team_reset_scoped_to_store tests/test_account_management.py::test_team_reset_password_too_short tests/test_account_management.py::test_team_reset_passwords_do_not_match -v
```

Expected: `test_team_tab_*` may PASS (template renders), reset tests FAIL with 405 (route not yet defined).

- [ ] **Step 3: Add the `admin_reset_employee_password` route to app.py**

In `app.py`, immediately after the `admin_settings` route, add:

```python
@app.route("/admin/settings/team/<int:uid>", methods=["POST"])
@admin_required
def admin_reset_employee_password(uid):
    sid = session["store_id"]
    emp = User.query.filter_by(id=uid, store_id=sid).first_or_404()
    pw = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    if len(pw) < 8:
        flash("Password must be at least 8 characters.", "error")
    elif pw != confirm:
        flash("Passwords do not match.", "error")
    else:
        emp.set_password(pw)
        db.session.commit()
        flash(f"Password updated for {emp.full_name or emp.username}.", "success")
    return redirect(url_for("admin_settings", tab="team"))
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_account_management.py::test_team_tab_loads_and_shows_employees tests/test_account_management.py::test_team_tab_shows_employee_login_url tests/test_account_management.py::test_team_reset_employee_password tests/test_account_management.py::test_team_reset_scoped_to_store tests/test_account_management.py::test_team_reset_password_too_short tests/test_account_management.py::test_team_reset_passwords_do_not_match -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_account_management.py
git commit -m "feat: team tab with employee password reset at /admin/settings/team/<uid>"
```

---

## Task 6: Add Settings Nav Link to Sidebar

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Update `templates/base.html` to add a Settings nav link**

Find this block in `templates/base.html`:

```html
      <div class="nav-section">Settings</div>
      <a href="{{ url_for('admin_users') }}" class="nav-link {% if 'admin_user' in request.endpoint %}active{% endif %}">
        <span class="icon">👥</span> Users
      </a>
```

Replace it with:

```html
      <div class="nav-section">Settings</div>
      <a href="{{ url_for('admin_users') }}" class="nav-link {% if 'admin_user' in request.endpoint %}active{% endif %}">
        <span class="icon">👥</span> Users
      </a>
      <a href="{{ url_for('admin_settings') }}" class="nav-link {% if request.endpoint == 'admin_settings' or request.endpoint == 'admin_reset_employee_password' %}active{% endif %}">
        <span class="icon">⚙️</span> Settings
      </a>
```

- [ ] **Step 2: Run the full test suite to confirm nothing is broken**

```
pytest tests/ -v
```

Expected: all tests PASS (including existing test_landing.py, test_signup.py, test_trial.py, test_subscribe.py, and test_account_management.py).

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add Settings nav link to admin sidebar"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] `/login/<slug>` — Task 1
- [x] Main `/login` restricted to admin/superadmin — Task 2
- [x] Store Info tab (name, email, phone, admin username sync) — Task 3
- [x] Security tab (password change with current password check) — Task 4
- [x] Team tab (employee list, login URL, reset password) — Task 5
- [x] `?tab=` redirect param on all redirects — implemented in route
- [x] Nav link — Task 6
- [x] Employee blocked from main login with helpful message — Task 2

**No placeholders found.**

**Type consistency:** `admin_settings`, `login_store`, `admin_reset_employee_password` used consistently across all tasks.
