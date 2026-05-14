"""Add-ons catalog. Each entry has a stable key used in the
``Store.addons`` CSV column. Adding an add-on requires an active
paid subscription (basic or pro). ``status="coming_soon"`` disables
activation in the UI and on the server until the underlying
integration ships."""
from __future__ import annotations


ADDONS_CATALOG = {
    "tv_display": {
        "name": "TV Display & Live Rates",
        "price_cents": 500,
        "price_label": "$5 / month",
        "tagline": "Show your money transfer rates on the TV behind your counter.",
        "description": (
            "A live rate board for your shop — manage country sections, payout "
            "banks, and the MT companies you offer in one place; the TV refreshes "
            "automatically when you change a rate. Each store gets a tokenized "
            "URL you point any TV browser, Chromecast, smart-TV, or our upcoming "
            "Google TV / Fire TV apps at."
        ),
        "status": "active",
    },
}
