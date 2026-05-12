"""Admin settings tabbed-form page handler.

Extracted from ``app.py`` as part of the D2 Blueprint split — the last
@app.route handler doing real form-POST work in app.py. Owns the
single multi-tab admin settings surface:

  GET   /admin/settings  → 301 redirect to /app/settings (or
                            account.account_security for the security
                            tab)
  POST  /admin/settings  → form mutation:
                              _tab=store      → store info update
                              _tab=security   → password change
                              _tab=companies  → MT companies CSV
                            falls through to ``admin_settings.html``
                            on validation failure so the operator
                            sees error context inline.

Sub-route mutations (roster/add, roster/<id>/{toggle,rename},
team/<uid>, owner/redeem) live in blueprints/admin_settings_mutations.py
(D2 phase 24). The two files together make up the full admin-settings
surface.

Helpers stay in app.py and are pulled in via late imports.

Endpoint-name churn:
  url_for("admin_settings", tab="store|companies|team|roster|owner")
    → url_for("admin_settings_form.view", tab="...")
  request.endpoint == "admin_settings"
    → request.endpoint == "admin_settings_form.view"
"""
from __future__ import annotations

import re

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for,
)


bp = Blueprint("admin_settings_form", __name__)


@bp.route("/admin/settings", methods=["GET", "POST"])
def view():
    """Tabbed admin settings (store info / security / team / owner /
    companies). The GET 301s to /app/settings (Settings.tsx covers
    store info + team + change password + passkeys + subscription
    redirect). The POST handler stays live for the legacy
    `_tab=store|companies` form-submit paths used by
    /admin/settings/roster/* and /admin/settings/owner/redeem so a
    direct POST still mutates state.

    Companies-tab and owner-access-tab UI haven't been ported to
    Settings.tsx yet — the mutation endpoints
    (/admin/settings POST with _tab=companies, plus
    /admin/settings/owner/redeem and /admin/settings/owner/...
    routes) remain reachable for direct callers; SPA cards land
    in a follow-up PR.
    """
    from app import (
        KNOWN_MT_COMPANIES, StoreEmployee, StoreOwnerLink, User,
        _update_user_password, admin_required, current_store,
        current_user, db, store_mt_companies,
    )

    @admin_required
    def _h():
        if request.method == "GET":
            active_tab = request.args.get("tab", "store")
            if active_tab == "security":
                return redirect(
                    url_for("account.account_security"), code=301,
                )
            return redirect("/app/settings", code=301)

        user = current_user()
        store = current_store()
        active_tab = request.args.get("tab", "store")
        errors = {}

        form_tab = request.form.get("_tab", "store")
        active_tab = form_tab

        if form_tab == "store":
            name = request.form.get("store_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            rate_raw = (
                request.form.get("federal_tax_rate") or ""
            ).strip()
            rate_decimal = store.federal_tax_rate or 0.01
            if rate_raw:
                try:
                    rate_pct = float(rate_raw)
                    if rate_pct < 0 or rate_pct > 100:
                        errors["federal_tax_rate"] = (
                            "Enter a percent between 0 and 100."
                        )
                    else:
                        rate_decimal = round(rate_pct / 100.0, 6)
                except ValueError:
                    errors["federal_tax_rate"] = (
                        "Enter a number (e.g. 1 for 1%)."
                    )

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
                    User.store_id != store.id,
                ).first()
                if taken:
                    errors["email"] = (
                        "That email is already registered to another "
                        "account."
                    )

            if not errors:
                store.name = name
                store.email = email
                store.phone = phone
                store.federal_tax_rate = rate_decimal
                user.username = email
                db.session.commit()
                flash("Store info updated.", "success")
                return redirect(url_for(
                    "admin_settings_form.view", tab="store",
                ))

        elif form_tab == "security":
            errors = _update_user_password(
                user,
                request.form.get("current_password", ""),
                request.form.get("new_password", ""),
                request.form.get("confirm_password", ""),
            )
            if not errors:
                db.session.commit()
                flash("Password updated.", "success")
                return redirect(url_for(
                    "account.account_security",
                ))

        elif form_tab == "companies":
            picked = request.form.getlist("company_known")
            extras_raw = request.form.get("company_extras", "")
            extras = [
                line.strip() for line in extras_raw.splitlines()
                if line.strip()
            ]
            seen, out = set(), []
            for name in list(picked) + extras:
                if name not in seen:
                    seen.add(name)
                    out.append(name)
            csv = ",".join(out)[:500]
            store.companies = csv
            db.session.commit()
            flash("Money transfer companies updated.", "success")
            return redirect(url_for(
                "admin_settings_form.view", tab="companies",
            ))

        employees = User.query.filter(
            User.store_id == store.id,
            User.id != user.id,
        ).order_by(User.full_name).all()

        owner_link = StoreOwnerLink.query.filter_by(
            store_id=store.id,
        ).first()
        owner_user = (
            db.session.get(User, owner_link.owner_id)
            if owner_link else None
        )

        current_companies = store_mt_companies(store)
        current_set = set(current_companies)
        custom_companies = [
            c for c in current_companies
            if c not in KNOWN_MT_COMPANIES
        ]

        roster = StoreEmployee.query.filter_by(
            store_id=store.id,
        ).order_by(
            StoreEmployee.is_active.desc(),
            StoreEmployee.name.asc(),
        ).all()

        return render_template(
            "admin_settings.html",
            user=user, store=store,
            active_tab=active_tab, errors=errors,
            employees=employees,
            owner_link=owner_link,
            owner_user=owner_user,
            known_companies=KNOWN_MT_COMPANIES,
            current_company_set=current_set,
            custom_companies=custom_companies,
            roster=roster,
        )

    return _h()
