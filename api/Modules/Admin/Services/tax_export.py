"""Tax-export Service.

Pure read-only helpers for the admin tax-export year picker. The
ZIP build itself stays in app.py — it streams a multi-MB file via
Flask's send_file path and depends on a swathe of legacy CSV
helpers (`_tax_pack_*_csv`) we don't need to ship through the SPA
yet.
"""
from datetime import date

from sqlalchemy import distinct, extract
from sqlalchemy.orm import Session


def list_year_choices(db: Session, store_id: int) -> list[int]:
    """Return every year that has at least one transfer or one
    daily report on this store, plus this year and last year so a
    brand-new store still sees something to click. Sorted
    newest-first.

    Pure SQL — no commit. Mirrors the legacy app._tax_pack_year_choices
    so a Flask reader and a SPA reader see the same options.
    """
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Transfers.Models import Transfer

    today = date.today()
    years: set[int] = {today.year, today.year - 1}
    for col, model in (
        (Transfer.send_date,    Transfer),
        (DailyReport.report_date, DailyReport),
    ):
        rows = (
            db.query(distinct(extract("year", col)))
              .filter(model.store_id == store_id)
              .all()
        )
        for (y,) in rows:
            if y is not None:
                years.add(int(y))
    return sorted(years, reverse=True)


def default_year(years: list[int]) -> int:
    """Default selection is last calendar year — that's almost
    always what an operator wants when running a tax pack. Fall
    back to the most-recent year on the list if for any reason
    last year isn't present (shouldn't happen because
    list_year_choices seeds it)."""
    today = date.today()
    if (today.year - 1) in years:
        return today.year - 1
    return years[0] if years else today.year - 1
