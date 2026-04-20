# Account Management & Secure Employee Login Design

## Goal

Add a tabbed admin settings page and a store-scoped employee login URL so store admins can manage their store info, change their password, and reset employee passwords — while preventing username collisions across different stores.

## Architecture

A new `/admin/settings` page with three tabs (Store Info, Security, Team) covers all admin self-service needs in one place. A new `/login/<slug>` route scopes employee authentication to a specific store, eliminating cross-store username collision risk. The main `/login` route is restricted to admin and superadmin roles only.

No schema changes are required — all needed fields already exist on `Store` and `User`.

---

## Routes

### New

| Method | Path | Handler | Auth |
|--------|------|---------|------|
| GET/POST | `/admin/settings` | `admin_settings` | `admin_required` |
| GET/POST | `/login/<slug>` | `login_store` | public |

### Modified

| Path | Change |
|------|--------|
| `/login` | After password check, reject users whose `role` is `"employee"` with message: *"Please use your store's login link."* |

---

## Settings Page — Tabs

### Tab 1: Store Info

Fields:
- **Store Name** (required, max 120 chars)
- **Contact Email** (required, valid email format, must not be taken by another store admin)
- **Phone** (optional)

On save:
1. Validate all fields
2. Update `Store.name`, `Store.email`, `Store.phone`
3. In the same transaction, update the current admin's `User.username` to the new email value
4. Flash success and redirect back to the Store Info tab

Error cases:
- Name blank → inline field error
- Email invalid format → inline field error
- Email already used by another store's admin → inline field error: *"That email is already registered to another account."*

### Tab 2: Security

Fields:
- **Current Password** (required)
- **New Password** (required, min 8 chars)
- **Confirm New Password** (required, must match)

On save:
1. Verify current password via `check_password_hash` — reject with *"Current password is incorrect."* if wrong
2. Validate new password length and confirmation match
3. Call `user.set_password(new_password)` and commit
4. Flash success and redirect back to Security tab

### Tab 3: Team

Displays:
- Employee login URL at the top: `<base_url>/login/<store_slug>` with a "Copy" button (JS clipboard)
- Table of all `User` records for this store (excluding the admin themselves), columns: Full Name, Username, Role, Active status, Reset Password button

Reset Password modal/inline form (per employee row):
- Fields: New Password, Confirm New Password (min 8 chars, must match)
- No current password required — admin authority
- On save: call `employee.set_password(new_password)`, commit, flash *"Password updated for [full_name]."*
- Scoped to `store_id = session["store_id"]` — admin cannot reset users from other stores

---

## Secure Employee Login (`/login/<slug>`)

1. Look up `Store.query.filter_by(slug=slug).first_or_404()`
2. On POST: query `User.query.filter_by(username=username, store_id=store.id).first()`
3. Check `user.is_active` and `user.check_password(password)`
4. On success: set `session["user_id"]`, `session["role"]`, `session["store_id"]` — redirect to dashboard
5. On failure: render login form with *"Invalid username or password."*

The store-scoped URL is the only login entry point for employees. It is displayed on the Team tab so admins can copy and share it.

---

## Main `/login` Restriction

After successful password verification, add a role check:

```python
if u.role == "employee":
    error = "Please use your store's login link."
    # do not set session
```

Admins and superadmins continue to use `/login` as before.

---

## UI Pattern

All settings tabs follow the same layout pattern for future consistency:
- Page title: "Settings"
- Horizontal tab bar below the page title: Store Info | Security | Team
- Active tab indicated by underline/highlight
- Each tab contains a single `<form>` with labeled fields and a primary action button
- Flash messages appear above the tab bar (existing base.html flash block)
- Tab state preserved on redirect via a `?tab=` query param (e.g., `?tab=security`)

---

## Testing

### `/login/<slug>`
- Valid employee credentials → logs in, redirects to dashboard
- Wrong password → stays on login, shows error
- Unknown slug → 404
- Employee trying main `/login` → blocked with message
- Admin can still use main `/login`

### Settings — Store Info
- Valid update → store fields updated, admin username updated, flash shown
- Duplicate email → inline error, no DB change
- Blank name → inline error

### Settings — Security
- Wrong current password → error, password unchanged
- New password too short → error
- Mismatched confirmation → error
- Valid update → password changed, can login with new password

### Settings — Team
- Reset password form → employee can login with new password
- Admin cannot reset a user from a different store (scoped query)
- Employee login URL is correct and copyable
