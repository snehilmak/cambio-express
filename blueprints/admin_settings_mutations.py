"""Admin-settings mutation POST handlers (roster + team + owner-redeem).

Extracted from ``app.py`` as part of the D2 Blueprint split. Five
POST handlers that mutate per-store state from the admin Settings
tabs:

  POST /admin/settings/roster/add               Add a roster name
                                                 (case-insensitive
                                                 dedupe; re-activates
                                                 a deactivated row if
                                                 the name matches)
  POST /admin/settings/roster/<int:eid>/toggle  Reactivate / deactivate
                                                 a roster entry
  POST /admin/settings/roster/<int:eid>/rename  Rename a roster entry
                                                 (historical transfers
                                                 keep their snapshot)
  POST /admin/settings/team/<int:uid>           Reset an employee's
                                                 password
  POST /admin/settings/owner/redeem             Store admin enters an
                                                 owner code to link
                                                 this store to that
                                                 owner's umbrella

Every handler redirects back to ``url_for("admin_settings_form.view",
tab=<...>")`` so the operator lands on the same tab they started
from. ``admin_settings`` itself stays in app.py — it's the
GET-redirect + multi-tab form-POST handler that hasn't moved yet.

Helpers stay in app.py (pulled via late imports):
  admin_required, current_store, current_user,
  StoreEmployee, User, OwnerConnectCode, StoreOwnerLink, db,
  admin_set_password (from api.Modules.Auth.Services).

Endpoint-name churn:
  url_for("admin_roster_add")              → url_for("admin_settings_mutations.admin_roster_add")
  url_for("admin_roster_toggle")           → url_for("admin_settings_mutations.admin_roster_toggle")
  url_for("admin_roster_rename")           → url_for("admin_settings_mutations.admin_roster_rename")
  url_for("admin_reset_employee_password") → url_for("admin_settings_mutations.admin_reset_employee_password")
  url_for("admin_redeem_owner_code")       → url_for("admin_settings_mutations.admin_redeem_owner_code")
"""
from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint, flash, redirect, request, session, url_for,
)


bp = Blueprint("admin_settings_mutations", __name__)


@bp.route("/admin/settings/roster/add", methods=["POST"])
def admin_roster_add():
    """Add a roster name. Case-insensitive dedupe — if a
    deactivated entry matches, re-activate it rather than create a
    second row so audit history stays intact."""
    from app import (
        StoreEmployee, admin_required, current_store, db,
    )

    @admin_required
    def _h():
        store = current_store()
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("admin_settings_form.view", tab="roster"))
        existing = StoreEmployee.query.filter(
            StoreEmployee.store_id == store.id,
            db.func.lower(StoreEmployee.name) == name.lower(),
        ).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                db.session.commit()
                flash(f"Reactivated {existing.name}.", "success")
            else:
                flash(
                    f"{existing.name} is already on the roster.",
                    "error",
                )
            return redirect(url_for("admin_settings_form.view", tab="roster"))
        db.session.add(StoreEmployee(store_id=store.id, name=name))
        db.session.commit()
        flash(f"Added {name}.", "success")
        return redirect(url_for("admin_settings_form.view", tab="roster"))

    return _h()


@bp.route("/admin/settings/roster/<int:eid>/toggle", methods=["POST"])
def admin_roster_toggle(eid: int):
    """Reactivate / deactivate a roster entry."""
    from app import StoreEmployee, admin_required, db

    @admin_required
    def _h():
        sid = session["store_id"]
        emp = StoreEmployee.query.filter_by(
            id=eid, store_id=sid,
        ).first_or_404()
        emp.is_active = not emp.is_active
        db.session.commit()
        flash(
            f"{emp.name} "
            f"{'reactivated' if emp.is_active else 'deactivated'}.",
            "success",
        )
        return redirect(url_for("admin_settings_form.view", tab="roster"))

    return _h()


@bp.route("/admin/settings/roster/<int:eid>/rename", methods=["POST"])
def admin_roster_rename(eid: int):
    """Rename a roster entry. Historical transfers keep their
    snapshotted employee_name — a rename only affects future
    dropdown picks. That's the intended audit-preserving
    behaviour."""
    from app import StoreEmployee, admin_required, db

    @admin_required
    def _h():
        sid = session["store_id"]
        emp = StoreEmployee.query.filter_by(
            id=eid, store_id=sid,
        ).first_or_404()
        new_name = (request.form.get("name") or "").strip()
        if not new_name:
            flash("Name cannot be empty.", "error")
        else:
            emp.name = new_name
            db.session.commit()
            flash(f"Renamed to {new_name}.", "success")
        return redirect(url_for("admin_settings_form.view", tab="roster"))

    return _h()


@bp.route("/admin/settings/team/<int:uid>", methods=["POST"])
def admin_reset_employee_password(uid: int):
    """Admin-side employee password reset. Validation + apply
    delegate to ``api.Modules.Auth.Services.admin_set_password``;
    this Flask route handles the cross-store scope check and the
    inline flash messages."""
    from app import User, admin_required, db
    from api.Modules.Auth.Services import admin_set_password

    @admin_required
    def _h():
        sid = session["store_id"]
        emp = User.query.filter_by(
            id=uid, store_id=sid,
        ).first_or_404()
        errors = admin_set_password(
            db.session, emp,
            request.form.get("password", ""),
            request.form.get("confirm_password", ""),
        )
        if errors:
            # Surface the first error as a flash (matches the
            # legacy behaviour — only one message per round-trip).
            flash(next(iter(errors.values())), "error")
        else:
            db.session.commit()
            flash(
                f"Password updated for "
                f"{emp.full_name or emp.username}.",
                "success",
            )
        return redirect(url_for("admin_settings_form.view", tab="team"))

    return _h()


@bp.route("/admin/settings/owner/redeem", methods=["POST"])
def admin_redeem_owner_code():
    """Store admin enters an owner-supplied code to link this
    store to that owner's umbrella. Replaces the old
    store-admin-generates / owner-redeems flow.

    Validation chain: code exists, not used, not revoked, not
    expired, no existing link to that owner. Disconnect after this
    point is owner-side only (``/owner/unlink``)."""
    from app import (
        OwnerConnectCode, StoreOwnerLink, User, admin_required,
        current_store, current_user, db,
    )

    @admin_required
    def _h():
        store = current_store()
        code_str = request.form.get("code", "").strip().upper()
        if not code_str:
            flash("Enter the code your owner gave you.", "error")
            return redirect(url_for("admin_settings_form.view", tab="owner"))
        now = datetime.utcnow()
        # NOTE: TOCTOU window between lookup and commit — safe
        # under SQLite (serialised writes); a Postgres migration
        # should add SELECT FOR UPDATE here.
        code = OwnerConnectCode.query.filter(
            OwnerConnectCode.code == code_str,
            OwnerConnectCode.used_at.is_(None),
            OwnerConnectCode.revoked_at.is_(None),
            OwnerConnectCode.expires_at > now,
        ).first()
        if not code:
            flash("Invalid, expired, or already-used code.", "error")
            return redirect(url_for("admin_settings_form.view", tab="owner"))
        owner = db.session.get(User, code.owner_id)
        if not owner or owner.role != "owner":
            flash(
                "That code's owner account is no longer valid.",
                "error",
            )
            return redirect(url_for("admin_settings_form.view", tab="owner"))
        already = StoreOwnerLink.query.filter_by(
            owner_id=owner.id, store_id=store.id,
        ).first()
        if already:
            flash(
                "This store is already connected to that owner.",
                "info",
            )
            return redirect(url_for("admin_settings_form.view", tab="owner"))
        link = StoreOwnerLink(owner_id=owner.id, store_id=store.id)
        code.used_at = now
        code.used_by_user_id = current_user().id
        code.used_by_store_id = store.id
        db.session.add(link)
        db.session.commit()
        flash(
            f"Store connected to "
            f"{owner.full_name or owner.username}.",
            "success",
        )
        return redirect(url_for("admin_settings_form.view", tab="owner"))

    return _h()
