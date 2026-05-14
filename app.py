import logging, os, sys

import stripe
from flask import Flask

# When run via `python app.py` the module is __main__; submodules
# that ``from app import …`` would re-execute it as a fresh `app`
# module. Aliasing prevents the circular re-entry.
if __name__ == "__main__" and "app" not in sys.modules:
    sys.modules["app"] = sys.modules[__name__]

logging.basicConfig(level=logging.INFO)

# Observability + Flask app
from api.Core.Observability import (  # noqa: E402
    init_logging, init_sentry, install_request_id,
)
init_logging()
init_sentry()

app = Flask(__name__)
install_request_id(app)

from api.Flask.Config import (  # noqa: E402
    install_secret_key as _install_secret_key,
    warn_default_seed_passwords as _warn_seed_pw,
)
_install_secret_key(app)
_warn_seed_pw(app)

from api.Flask.Templating import (  # noqa: E402
    country_flag_html, install as _install_templating,
)
STATIC_VERSION = _install_templating(app)

from api.Flask.Database import install as _install_db  # noqa: E402
db = _install_db(app)


stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


# ── Models live in api/Modules/<domain>/Models ──────────────────
# Re-exported here so legacy ``from app import Store, User, …``
# call sites keep working. New code imports from the per-domain
# Models package directly.
from api.Flask.Models import *  # noqa: E402, F401, F403


# Billing helpers re-exported for tests.
from api.Modules.Billing.Services import (  # noqa: E402
    data_retention_days_left,
    store_addon_keys,
    store_has_paid_plan,
)


# Self-service signup gate.
SIGNUP_CLOSED = os.environ.get("SIGNUP_CLOSED", "0") == "1"

def purge_expired_stores():
    """Daily cron entrypoint (CLAUDE.md invariant #4 = 180 days)."""
    from api.Modules.Billing.Services import purge_expired_stores as _svc
    from api.Core.Database import SessionLocal
    with SessionLocal() as s:
        return _svc(s)


def find_or_upsert_customer(store_id, full_name, phone_country, phone_number,
                             address="", dob=None, customer_id=None):
    """Find-or-create a Customer row scoped to the owner umbrella
    (CLAUDE.md invariant #5). Last write wins on PII fields."""
    from api.Modules.Customers.Services import upsert as _customers_upsert
    return _customers_upsert(
        db.session, store_id, full_name, phone_country, phone_number,
        address=address, dob=dob, customer_id=customer_id,
    )


# Wire the rest of the app: CLI commands, schema init, FastAPI
# mount. SPA-cutover redirects + 404/500 error handlers moved to
# the ASGI layer in PR #548 (Flask-removal-3); they run before the
# Flask fallback in asgi.py. The conftest mirrors them onto the
# Flask test_client for the (now-shrinking) tests that still hit
# Flask directly.
from api.Flask.Cli import register as _register_cli_commands  # noqa: E402
_register_cli_commands(app, db)

from api.Flask.Init import init_db as _init_db, mount_fastapi as _mount_fastapi  # noqa: E402


def init_db():
    """Boot-time DB init. Idempotent on every boot."""
    _init_db(app, db)


# DINEROBOOK_SKIP_INIT_DB is set by alembic/env.py (imports app
# only to harvest db.metadata).
if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
    init_db()

# Mount /api/v2 + /app onto Flask's wsgi_app for test_client.
# Production routes via asgi.py and bypasses this entirely.
_mount_fastapi(app)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 DineroBook → http://0.0.0.0:{port}  (uvicorn/ASGI)")
    uvicorn.run(
        "asgi:asgi_app",
        host="0.0.0.0",
        port=port,
        reload=bool(os.environ.get("DEV_RELOAD")),
        log_level="info",
    )
