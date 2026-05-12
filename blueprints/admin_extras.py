"""Remaining admin (store-side) mutation handlers.

Extracted from ``app.py`` as part of the D2 Blueprint split. Two
routes that didn't fit the other admin/bookkeeping/bank groupings:

  GET   /admin/tax-export.zip            → year-end packet stream
  GET/POST /tv-display/countries/<id>    → TV display country editor
                                            (GET 301s to /app/*; POST
                                            stays live as the canonical
                                            mutation surface)

Helpers stay in app.py and are pulled in via late imports.

Endpoint-name churn:
  url_for("admin_tax_export_zip")       → url_for("admin_extras.admin_tax_export_zip")
  url_for("tv_display_country_edit")    → url_for("admin_extras.tv_display_country_edit")
"""
from __future__ import annotations

from datetime import date, datetime

from flask import (
    Blueprint, Response, flash, redirect, request, url_for,
)


bp = Blueprint("admin_extras", __name__)


@bp.route("/admin/tax-export.zip")
def admin_tax_export_zip():
    """Year-end tax pack download. Builds a single ZIP holding every
    CSV/PDF the operator's accountant needs to file. Year defaults to
    the prior calendar year."""
    from app import (
        _build_tax_pack_zip, admin_required, current_store,
    )

    @admin_required
    def _h():
        store = current_store()
        try:
            year = int(
                request.args.get("year", date.today().year - 1),
            )
        except ValueError:
            year = date.today().year - 1
        payload = _build_tax_pack_zip(store, year)
        fname = (
            f"dinerobook_tax_pack_{store.slug}_{year}.zip"
        )
        return Response(
            payload, mimetype="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{fname}"'
                ),
            },
        )

    return _h()


@bp.route(
    "/tv-display/countries/<int:country_id>", methods=["GET", "POST"],
)
def tv_display_country_edit(country_id: int):
    """Per-country TV display editor. GET 301s to /app/tv-display/*;
    POST stays live as the canonical mutation surface (banks + rate
    matrix + country header). The SPA reads /api/v2/tv-display/* and
    submits the same form back to this URL."""
    from app import (
        TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
        _csv_split, _ensure_tv_display, _tv_required, db,
        login_required,
    )

    @login_required
    def _h():
        guard = _tv_required()
        if not isinstance(guard, tuple):
            return guard
        _, store = guard
        display = _ensure_tv_display(store)
        country = TVDisplayCountry.query.filter_by(
            id=country_id, display_id=display.id,
        ).first_or_404()

        if request.method == "GET":
            return redirect(
                f"/app/tv-display/countries/{country_id}", code=301,
            )

        country.country_name = (
            request.form.get("country_name") or country.country_name
        ).strip()[:80]
        country.country_code = (
            request.form.get("country_code") or ""
        ).strip().upper()[:4]
        new_companies = (
            request.form.get("mt_companies") or ""
        ).strip()[:500]
        country.mt_companies = new_companies
        companies = _csv_split(new_companies)

        for b in TVDisplayPayoutBank.query.filter_by(
            country_id=country.id,
        ).all():
            if request.form.get(f"bank-{b.id}-delete"):
                TVDisplayRate.query.filter_by(bank_id=b.id).delete(
                    synchronize_session=False,
                )
                db.session.delete(b)
                continue
            new_name = (
                request.form.get(f"bank-{b.id}-name") or ""
            ).strip()[:120]
            if new_name:
                b.bank_name = new_name
            try:
                b.sort_order = int(
                    request.form.get(f"bank-{b.id}-sort") or 0,
                )
            except ValueError:
                pass
        new_bank_names = [
            (n or "").strip()[:120]
            for n in request.form.getlist("new_bank_name")
            if (n or "").strip()
        ]
        if new_bank_names:
            last = (
                db.session.query(
                    db.func.max(TVDisplayPayoutBank.sort_order),
                ).filter_by(country_id=country.id).scalar() or 0
            )
            for offset, name in enumerate(new_bank_names, start=1):
                db.session.add(TVDisplayPayoutBank(
                    country_id=country.id, bank_name=name,
                    sort_order=last + 10 * offset,
                ))
        db.session.commit()

        banks = (
            TVDisplayPayoutBank.query
            .filter_by(country_id=country.id)
            .order_by(
                TVDisplayPayoutBank.sort_order,
                TVDisplayPayoutBank.id,
            ).all()
        )
        for b in banks:
            for idx, company in enumerate(companies):
                key = f"rate-{b.id}-{idx}"
                raw = (request.form.get(key) or "").strip()
                existing = TVDisplayRate.query.filter_by(
                    bank_id=b.id, mt_company=company,
                ).first()
                if not raw:
                    if existing:
                        db.session.delete(existing)
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                if existing:
                    existing.rate = val
                else:
                    db.session.add(TVDisplayRate(
                        bank_id=b.id, mt_company=company, rate=val,
                    ))
        bank_ids_subq = db.session.query(
            TVDisplayPayoutBank.id,
        ).filter_by(country_id=country.id)
        if companies:
            (
                TVDisplayRate.query
                .filter(
                    TVDisplayRate.bank_id.in_(bank_ids_subq),
                    ~TVDisplayRate.mt_company.in_(companies),
                )
                .delete(synchronize_session=False)
            )
        else:
            TVDisplayRate.query.filter(
                TVDisplayRate.bank_id.in_(bank_ids_subq),
            ).delete(synchronize_session=False)
        display.last_updated_at = datetime.utcnow()
        db.session.commit()
        flash("Saved.", "success")
        return redirect(url_for(
            "admin_extras.tv_display_country_edit",
            country_id=country.id,
        ))

    return _h()
