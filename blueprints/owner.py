"""Multi-store owner umbrella routes.

Extracted from ``app.py`` as part of the D2 Blueprint split. The
routes here cover the legacy ``/owner/*`` URL space:

  GET  /owner/dashboard            redirect → /app/owner/dashboard
  GET  /owner/pl-rollup            redirect → /app/owner/pl-rollup
  GET  /owner/locations            redirect → /app/owner/locations
                                    (drops the legacy partial=1 marker)
  GET  /owner/store/<int:id>       redirect → /app/owner/store/<id>
  GET  /owner/connect              redirect → /app/owner/connect

  POST /owner/connect/generate     mint a fresh 7-day invite code
  POST /owner/connect/<id>/revoke  revoke an unredeemed code
  POST /owner/unlink/<id>          break a StoreOwnerLink

The redirects are pure compatibility shims for any in-product link
that still points at the legacy URLs (sidebar nav fragments, old
bookmarks, post-mutation `redirect(url_for("owner_dashboard"))`
calls in still-Jinja routes). The mutating POSTs ARE the live
write surface — the SPA submits to them today; they'll move to
``/api/v2/owner/*`` in a follow-up.

All app.py imports inside the routes are late so this module can
load before app.py finishes its own init (Blueprint registration
happens before models, helpers, and decorators are defined).
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta

from flask import (
    Blueprint, flash, redirect, request, url_for,
)


bp = Blueprint("owner", __name__)


# ── 301 → SPA redirects ─────────────────────────────────────────


@bp.route("/owner/dashboard")
def owner_dashboard():
    """301 → /app/owner/dashboard. SPA reads /api/v2/owner/dashboard
    and renders the KPI cards + multi-store rollup + charts."""
    from app import owner_required
    return owner_required(lambda: _redirect_with_qs("/app/owner/dashboard"))()


@bp.route("/owner/pl-rollup")
def owner_pl_rollup():
    """301 → /app/owner/pl-rollup. Preserves ?year=&month= so a
    deep link lands on the right month."""
    from app import owner_required
    return owner_required(lambda: _redirect_with_qs("/app/owner/pl-rollup"))()


@bp.route("/owner/locations")
def owner_locations():
    """301 → /app/owner/locations. Drops the legacy ?partial=1
    marker (AJAX swap pattern retired; the SPA does its own
    debounced fetching)."""
    from app import owner_required

    @owner_required
    def _h():
        qs = (
            request.query_string.decode("latin-1") if request.query_string else ""
        )
        if qs:
            qs = "&".join(p for p in qs.split("&") if p != "partial=1")
        target = "/app/owner/locations" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/owner/store/<int:store_id>")
def owner_store_detail(store_id: int):
    """301 → /app/owner/store/<id>. The StoreOwnerLink scope check
    runs on the SPA's API call so unrelated stores still 404 via
    /api/v2/owner/store/<id>."""
    from app import owner_required
    return owner_required(
        lambda: _redirect_with_qs(f"/app/owner/store/{store_id}")
    )()


@bp.route("/owner/connect", methods=["GET"])
def owner_connect():
    """301 → /app/owner/connect. The legacy POST handlers below
    stay alive so in-flight Jinja form submissions don't break
    mid-flow."""
    from app import owner_required
    return owner_required(lambda: redirect("/app/owner/connect", code=301))()


# ── POST mutations (still live write surface) ───────────────────


@bp.route("/owner/connect/generate", methods=["POST"])
def owner_connect_generate():
    """Mint a fresh 7-day invite code for the current owner. If an
    active code already exists, revoke it first — owners share a
    single live code at a time to keep the UI simple."""
    from app import OwnerConnectCode, current_user, db, owner_required

    @owner_required
    def _h():
        u = current_user()
        now = datetime.utcnow()
        OwnerConnectCode.query.filter(
            OwnerConnectCode.owner_id == u.id,
            OwnerConnectCode.used_at.is_(None),
            OwnerConnectCode.revoked_at.is_(None),
            OwnerConnectCode.expires_at > now,
        ).update({"revoked_at": now})
        db.session.flush()
        alphabet = string.ascii_uppercase + string.digits
        code = None
        for _ in range(10):
            candidate = "".join(secrets.choice(alphabet) for _ in range(8))
            if not OwnerConnectCode.query.filter_by(code=candidate).first():
                code = candidate
                break
        if code is None:
            flash(
                "Could not generate a unique code. Please try again.",
                "error",
            )
            return redirect(url_for("owner.owner_connect"))
        db.session.add(OwnerConnectCode(
            owner_id=u.id, code=code,
            expires_at=now + timedelta(days=7),
        ))
        db.session.commit()
        flash(
            "Invite code generated. Share it with the store admin.",
            "success",
        )
        return redirect(url_for("owner.owner_connect"))

    return _h()


@bp.route("/owner/connect/<int:code_id>/revoke", methods=["POST"])
def owner_connect_revoke(code_id: int):
    """Revoke an active code before it's redeemed (e.g. the owner
    sent it to the wrong person)."""
    from app import OwnerConnectCode, current_user, db, owner_required

    @owner_required
    def _h():
        u = current_user()
        c = OwnerConnectCode.query.filter_by(
            id=code_id, owner_id=u.id,
        ).first_or_404()
        if c.used_at is not None:
            flash(
                "Code has already been redeemed and can't be revoked.",
                "error",
            )
        elif c.revoked_at is not None:
            flash("Code is already revoked.", "info")
        else:
            c.revoked_at = datetime.utcnow()
            db.session.commit()
            flash("Code revoked.", "success")
        return redirect(url_for("owner.owner_connect"))

    return _h()


@bp.route("/owner/unlink/<int:store_id>", methods=["POST"])
def owner_unlink_store(store_id: int):
    """Disconnect an owner→store relationship. Owner-side only —
    the store admin sees a read-only "contact your owner" message
    in their settings. Does not affect store data itself."""
    from app import StoreOwnerLink, current_user, db, owner_required

    @owner_required
    def _h():
        u = current_user()
        link = StoreOwnerLink.query.filter_by(
            owner_id=u.id, store_id=store_id,
        ).first_or_404()
        db.session.delete(link)
        db.session.commit()
        flash("Store disconnected from your account.", "success")
        return redirect(url_for("owner.owner_dashboard"))

    return _h()


# ── helpers ─────────────────────────────────────────────────────


def _redirect_with_qs(target: str):
    """Build a 301 to ``target`` that preserves the inbound query
    string. Used by the SPA-cutover redirects so a deep link with
    a period / year / month filter lands on the right page."""
    qs = request.query_string.decode("latin-1") if request.query_string else ""
    return redirect(target + (f"?{qs}" if qs else ""), code=301)
