"""Flask Blueprints — incremental decomposition of ``app.py``.

The monolith (``app.py``) is being split into Blueprints by the
``# ── HEADER ──`` markers it already uses (per BACKLOG D2 + the
``api/Modules/`` migration ADR). The end state is roughly:

    blueprints/
      pwa.py           service worker + offline page
      errors.py        @app.errorhandler registrations
      auth.py          /login, /logout, password reset, /forgot
      admin.py         /admin/settings/*, /admin/users/*, …
      superadmin.py    /superadmin/*, /superadmin/controls, …
      transfers.py     /transfers, /transfers/new, /transfers/:id/edit
      daily.py         /daily, /daily/edit, daily-line-item routes
      monthly.py       /monthly, /monthly/edit, tax export
      bank.py          /bank, /bank/rules, Stripe FC routes
      owner.py         /owner/*, locations, P&L rollup
      tv.py            /tv/*, kiosk display, pair codes
      billing.py       /subscribe, /admin/subscription, Stripe webhook
      reports.py       /reports/*, /superadmin/reports/*
      api_v1.py        legacy JSON /api/* endpoints (not /api/v2)

Each Blueprint module exports either:
  - ``bp``: a ``flask.Blueprint`` instance the caller registers via
    ``app.register_blueprint(bp)``; OR
  - ``register(app)``: a function that attaches non-route concerns
    (error handlers, context processors, before-request hooks) to
    the live Flask app.

The split is mechanical — **no behavior change per PR**. Tests must
pass unchanged. The first PR ships the scaffolding and two of the
smallest, fully-isolated sections (PWA + error handlers) to
validate the pattern before chewing through the larger groupings.

Models stay in ``app.py`` for now. Splitting them is its own
project — every ``api/Modules/*/Models/__init__.py`` re-exports
``from app import ...`` and would need to learn a new home.
"""
