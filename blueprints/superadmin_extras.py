"""Remaining superadmin mutation + export handlers.

Extracted from ``app.py`` as part of the D2 Blueprint split. Seven
routes covering impersonation, deliverability probe, the TV catalog
admin (logos + edit + new), and the audit-log CSV export:

  Session ops:
    GET   /superadmin/impersonate/<store_id>
    POST  /superadmin/stop-impersonation
    POST  /superadmin/send-test-email

  TV catalog admin:
    POST  /superadmin/tv-catalog/<type>/<slug>/logo
    POST  /superadmin/tv-catalog/<type>/<slug>/edit
    POST  /superadmin/tv-catalog/new

  Audit-log export:
    GET   /superadmin/controls/audit.csv

Helpers stay in app.py and are pulled in via late imports.

Endpoint-name churn:
  url_for("superadmin_impersonate")          → url_for("superadmin_extras.superadmin_impersonate")
  url_for("superadmin_stop_impersonation")   → url_for("superadmin_extras.superadmin_stop_impersonation")
  url_for("superadmin_send_test_email")      → url_for("superadmin_extras.superadmin_send_test_email")
  url_for("superadmin_tv_catalog_upload_logo") → url_for("superadmin_extras.superadmin_tv_catalog_upload_logo")
  url_for("superadmin_tv_catalog_edit")      → url_for("superadmin_extras.superadmin_tv_catalog_edit")
  url_for("superadmin_tv_catalog_new")       → url_for("superadmin_extras.superadmin_tv_catalog_new")
  url_for("superadmin_audit_export")         → url_for("superadmin_extras.superadmin_audit_export")
"""
from __future__ import annotations

import io
import os
from datetime import datetime

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, session,
    url_for,
)


bp = Blueprint("superadmin_extras", __name__)


# ── Session ops ──────────────────────────────────────────────

@bp.route("/superadmin/impersonate/<int:store_id>")
def superadmin_impersonate(store_id: int):
    """Swap the current session into the target store's admin user.

    Used by the superadmin to debug a customer's view. The *real*
    superadmin identity is stashed in `session["impersonator_user_id"]`
    so `/superadmin/stop-impersonation` can restore it — before this,
    the only way back was a full re-login. Every start AND end of an
    impersonation is written to the audit log.
    """
    from app import (
        Store, User, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        store = db.session.get(Store, store_id) or abort(404)
        admin = User.query.filter_by(
            store_id=store_id, role="admin",
        ).first()
        if not admin:
            flash("No admin for this store.", "error")
            return redirect("/app/superadmin/stores")
        record_audit(
            "impersonate_start", target_type="store",
            target_id=store.id, details=f"as {admin.username}",
        )
        session["impersonator_user_id"] = session["user_id"]
        session["user_id"] = admin.id
        session["role"] = admin.role
        session["store_id"] = store_id
        db.session.commit()
        flash(
            f"Viewing as {store.name}. Use 'Exit impersonation' "
            "to return.",
            "success",
        )
        return redirect("/app/dashboard")

    return _h()


@bp.route("/superadmin/stop-impersonation", methods=["POST"])
def superadmin_stop_impersonation():
    """Return to the real superadmin identity after impersonation.

    Intentionally NOT guarded by @superadmin_required — while
    impersonating, session['role'] is 'admin', so the decorator
    would reject the superadmin trying to exit. Instead we verify
    the stashed impersonator_user_id still resolves to an active
    superadmin before restoring. If anything looks off, clear the
    session entirely rather than elevate the current identity.
    """
    from app import User, db, record_audit

    imp_id = session.get("impersonator_user_id")
    if not imp_id:
        flash("Not currently impersonating.", "error")
        return redirect("/app/dashboard")
    imp = db.session.get(User, imp_id)
    if not imp or imp.role != "superadmin" or not imp.is_active:
        session.clear()
        flash("Session invalid. Please sign in again.", "error")
        return redirect(url_for("auth.login"))
    record_audit(
        "impersonate_end", target_type="user", target_id=imp.id,
        details=f"returning to {imp.username}",
    )
    session["user_id"] = imp.id
    session["role"] = "superadmin"
    session["store_id"] = None
    session.pop("impersonator_user_id", None)
    db.session.commit()
    flash("Returned to superadmin.", "success")
    return redirect("/app/dashboard")


@bp.route("/superadmin/send-test-email", methods=["POST"])
def superadmin_send_test_email():
    """One-click deliverability probe. Sends a plain email to the
    superadmin's own User.email (they populate it from
    /account/profile) so they can verify the SMTP env vars are
    wired correctly without waiting for a real trigger like
    password reset.

    No dedup, no rate limit — superadmin-only, and the worst case is
    they spam their own inbox. The response is a flash + redirect
    back to the Overview so the SMTP health card updates with the
    new _last_smtp_attempt state on the next render."""
    from app import (
        _send_email, current_user, db, record_audit,
        superadmin_required,
    )

    @superadmin_required
    def _h():
        user = current_user()
        to_addr = (user.email or "").strip()
        if not to_addr:
            flash(
                "Set your email on /account/profile first — "
                "nowhere to send a test to.",
                "warning",
            )
            return redirect("/app/superadmin/controls?tab=overview")
        subject = "DineroBook test email"
        sent_at = datetime.utcnow().isoformat(timespec="seconds")
        body = (
            "This is a deliverability test from DineroBook.\n\n"
            f"Sent to: {to_addr}\n"
            f"Sent at: {sent_at}Z\n\n"
            "If you're reading this, SMTP is configured correctly "
            "and transactional email (password reset, trial "
            "reminders) will reach your users.\n"
        )
        html = render_template(
            "emails/test.html",
            preheader=(
                "Deliverability test from your DineroBook "
                "superadmin panel."
            ),
            to_addr=to_addr, sent_at=sent_at + "Z",
            sender=os.environ.get(
                "SMTP_FROM", "no-reply@dinerobook.com",
            ),
            year=datetime.utcnow().year,
            base_url=os.environ.get(
                "APP_BASE_URL", "https://dinerobook.com",
            ),
        )
        ok = _send_email(to_addr, subject, body, html=html)
        if ok:
            flash(
                f"Test email sent to {to_addr}. Check your inbox "
                "in a minute.",
                "success",
            )
        else:
            flash(
                "Test email failed. See the Email service card for "
                "the error.",
                "warning",
            )
        record_audit(
            "send_test_email", "superadmin", None,
            f"to={to_addr} ok={ok}",
        )
        db.session.commit()
        return redirect("/app/superadmin/controls?tab=overview")

    return _h()


# ── TV catalog admin ─────────────────────────────────────────

@bp.route(
    "/superadmin/tv-catalog/<catalog_type>/<slug>/logo",
    methods=["POST"],
)
def superadmin_tv_catalog_upload_logo(catalog_type: str, slug: str):
    """Upload (or replace) the logo for a catalog entry."""
    from app import (
        TVCatalogLogo, _TV_LOGO_ALLOWED_MIMES, _TV_LOGO_MAX_BYTES,
        _normalize_logo_blob, _resolve_catalog_row, db, record_audit,
        superadmin_required,
    )

    @superadmin_required
    def _h():
        if catalog_type not in ("company", "bank"):
            abort(404)
        row = _resolve_catalog_row(catalog_type, slug)
        if row is None:
            flash("Unknown catalog entry.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        f = request.files.get("logo")
        if not f or not f.filename:
            flash("Pick a file to upload.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        mime = (f.mimetype or "").lower()
        if mime not in _TV_LOGO_ALLOWED_MIMES:
            flash("File must be PNG, JPEG, WebP, or SVG.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        raw_blob = f.read()
        if len(raw_blob) == 0:
            flash("Uploaded file is empty.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")
        if len(raw_blob) > _TV_LOGO_MAX_BYTES:
            flash(
                f"Logo too large — max {_TV_LOGO_MAX_BYTES // 1024} KB.",
                "error",
            )
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        blob, mime = _normalize_logo_blob(raw_blob, mime)

        existing = TVCatalogLogo.query.filter_by(
            catalog_type=catalog_type, slug=slug,
        ).first()
        if existing is None:
            existing = TVCatalogLogo(
                catalog_type=catalog_type, slug=slug,
            )
            db.session.add(existing)
        existing.mime_type = mime
        existing.blob = blob
        existing.file_size = len(blob)
        existing.updated_at = datetime.utcnow()

        row.logo_url = url_for(
            "tv.tv_catalog_logo",
            catalog_type=catalog_type, slug=slug,
        )

        record_audit(
            "tv_logo_upload", target_type=catalog_type,
            target_id=row.id,
            details=f"{slug} ({len(blob)} bytes, {mime})",
        )
        db.session.commit()
        flash(f"Uploaded logo for {row.display_name}.", "success")
        return redirect("/app/superadmin/controls?tab=tv-catalog")

    return _h()


@bp.route(
    "/superadmin/tv-catalog/<catalog_type>/<slug>/edit",
    methods=["POST"],
)
def superadmin_tv_catalog_edit(catalog_type: str, slug: str):
    """Rename, re-sort, change country code (banks only), or toggle
    is_active. Slug is intentionally NOT mutable — references on
    TVDisplayCountry / TVDisplayPayoutBank would silently break."""
    from app import (
        _resolve_catalog_row, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        if catalog_type not in ("company", "bank"):
            abort(404)
        row = _resolve_catalog_row(catalog_type, slug)
        if row is None:
            flash("Unknown catalog entry.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        new_name = (
            request.form.get("display_name") or ""
        ).strip()[:80]
        if new_name:
            row.display_name = new_name
        try:
            row.sort_order = int(
                request.form.get("sort_order", row.sort_order),
            )
        except (TypeError, ValueError):
            pass
        if catalog_type == "bank":
            new_cc = (
                request.form.get("country_code") or ""
            ).strip().upper()[:4]
            if new_cc:
                row.country_code = new_cc
        row.is_active = bool(request.form.get("is_active"))

        record_audit(
            "tv_catalog_edit", target_type=catalog_type,
            target_id=row.id, details=slug,
        )
        db.session.commit()
        flash(f"Saved {row.display_name}.", "success")
        return redirect("/app/superadmin/controls?tab=tv-catalog")

    return _h()


@bp.route("/superadmin/tv-catalog/new", methods=["POST"])
def superadmin_tv_catalog_new():
    """Add a fresh catalog entry. Slug is auto-generated from the
    display_name (and country_code for banks); dedup'd with a
    numeric suffix on collision. The operator never types a slug."""
    from app import (
        TVBankCatalog, TVCompanyCatalog, _next_unique_slug,
        _slugify_bank_name, _slugify_catalog_name, db, record_audit,
        superadmin_required,
    )

    @superadmin_required
    def _h():
        catalog_type = (
            request.form.get("catalog_type") or ""
        ).strip()
        if catalog_type not in ("company", "bank"):
            flash("Pick company or bank.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")
        display_name = (
            request.form.get("display_name") or ""
        ).strip()[:80]
        if not display_name:
            flash("Display name is required.", "error")
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        cc = ""
        if catalog_type == "company":
            base_slug = _slugify_catalog_name(display_name)
        else:
            cc = (
                request.form.get("country_code") or ""
            ).strip().upper()[:4]
            if not cc:
                flash(
                    "Banks need a country code (ISO-2).", "error",
                )
                return redirect("/app/superadmin/controls?tab=tv-catalog")
            base_slug = _slugify_bank_name(display_name, cc)

        if not base_slug:
            flash(
                "Couldn't derive a slug from that name. Try a "
                "different one.",
                "error",
            )
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        slug = _next_unique_slug(catalog_type, base_slug)
        if not slug:
            flash(
                "Too many entries with similar names — slug exhausted.",
                "error",
            )
            return redirect("/app/superadmin/controls?tab=tv-catalog")

        if catalog_type == "company":
            last = (
                db.session.query(
                    db.func.max(TVCompanyCatalog.sort_order),
                ).scalar() or 0
            )
            db.session.add(TVCompanyCatalog(
                slug=slug, display_name=display_name,
                sort_order=last + 10, is_active=True,
            ))
        else:
            last = (
                db.session.query(
                    db.func.max(TVBankCatalog.sort_order),
                ).filter_by(country_code=cc).scalar() or 0
            )
            db.session.add(TVBankCatalog(
                slug=slug, display_name=display_name,
                country_code=cc,
                sort_order=last + 10, is_active=True,
            ))
        record_audit(
            "tv_catalog_create", target_type=catalog_type,
            target_id=0, details=slug,
        )
        db.session.commit()
        flash(f"Added {display_name}.", "success")
        return redirect("/app/superadmin/controls?tab=tv-catalog")

    return _h()


# ── Audit-log CSV export ─────────────────────────────────────

@bp.route("/superadmin/controls/audit.csv")
def superadmin_audit_export():
    """Stream the full audit log as CSV for spreadsheet review."""
    from app import (
        SuperadminAuditLog, db, record_audit, superadmin_required,
    )

    @superadmin_required
    def _h():
        import csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "timestamp_utc", "admin_id", "admin_name", "action",
            "target_type", "target_id", "details",
        ])
        rows = SuperadminAuditLog.query.order_by(
            SuperadminAuditLog.created_at.desc(),
        ).all()
        for r in rows:
            w.writerow([
                (
                    r.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if r.created_at else ""
                ),
                r.admin_id or "", r.admin_name or "",
                r.action or "", r.target_type or "", r.target_id or "",
                (r.details or "").replace("\n", " "),
            ])
        record_audit(
            "export_audit_csv", target_type="audit",
            details=f"rows={len(rows)}",
        )
        db.session.commit()
        filename = (
            f"audit-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
        )
        return buf.getvalue(), 200, {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
        }

    return _h()
