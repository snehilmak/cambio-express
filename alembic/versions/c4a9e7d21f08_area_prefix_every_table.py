"""area prefix on every application table (S-1)

Every table is renamed so its name starts with the area that owns
it — ``tenancy_``, ``auth_``, ``billing_``, ``platform_``,
``support_``, ``audit_``, ``bank_``, ``hr_``, ``msb_``, ``retail_`` —
so a developer reading the schema can tell what a table is part of,
which module folder owns it, and which INVARIANTS.md to read before
touching it. The convention and the module → prefix map live in
``api/Core/Schema.py``; ``docs/SCHEMA.md`` is generated from it.

The pairs below are spelled out literally, never derived from the
models — a migration is immutable history (CLAUDE.md "Migrations").
``tests/Core/test_table_prefixes.py`` asserts this list and the
models agree, which is how we get both safety and immutability.

What moves with each table:

* **Indexes named** ``ix_<old>_*`` become ``ix_<new>_*`` so the
  names SQLAlchemy derives for ``index=True`` columns keep matching
  the database and autogenerate stays quiet. Postgres renames in
  place; SQLite has no ALTER INDEX, so there the index is dropped
  and re-created on the renamed table (metadata-only for the
  handful of rows a dev DB holds). Indexes whose name does not
  embed the table name (``ix_pos_txn_*``, ``ix_sde_*``,
  ``ix_time_clock_employee_open``) are left alone: they were never
  wrong.
* **Postgres only:** auto-named constraints (``<old>_pkey``,
  ``<old>_<col>_fkey``, ``<old>_<col>_key``) and the identity
  sequence ``<old>_id_seq`` are renamed too, so ``\\d msb_transfer``
  reads coherently instead of showing ``transfer_pkey``. A sequence
  stays owned by its column whatever it is called, so this is
  cosmetic and safe.

Nothing is copied. A rename is a catalog update on both engines
and takes well under a second per table; the only operational
risk is Render's deploy overlap, where the old instance briefly
serves against renamed tables. Deploy off-hours, snapshot first.

``downgrade()`` is the same list backwards.

Revision ID: c4a9e7d21f08
Revises: b8f4c2e19d53
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa


revision = "c4a9e7d21f08"
down_revision = "b8f4c2e19d53"
branch_labels = None
depends_on = None


# (old, new). Order matters only for readability — every rename is
# independent of the others.
RENAMES: list[tuple[str, str]] = [
    # tenancy_
    ("store", "tenancy_store"),
    ("user", "tenancy_user"),
    ("store_employee", "tenancy_store_employee"),
    ("store_owner_link", "tenancy_store_owner_link"),
    ("owner_connect_code", "tenancy_owner_connect_code"),
    ("store_role", "tenancy_store_role"),
    ("store_role_permission", "tenancy_store_role_permission"),
    # auth_
    ("passkey", "auth_passkey"),
    ("refresh_token", "auth_refresh_token"),
    ("recovery_code", "auth_recovery_code"),
    ("password_reset_token", "auth_password_reset_token"),
    ("login_event", "auth_login_event"),
    # billing_
    ("feature_flag", "billing_feature_flag"),
    ("store_feature_override", "billing_store_feature_override"),
    ("discount_code", "billing_discount_code"),
    ("referral_code", "billing_referral_code"),
    ("referral_redemption", "billing_referral_redemption"),
    # platform_  (platform_setting already carries the prefix)
    ("webhook_event", "platform_webhook_event"),
    ("email_event", "platform_email_event"),
    ("announcement", "platform_announcement"),
    ("announcement_store", "platform_announcement_store"),
    ("push_subscription", "platform_push_subscription"),
    # support_  — support_ticket / support_message already carry it
    # audit_  (the repeated "audit" is dropped from the body)
    ("operator_audit_log", "audit_operator_log"),
    ("owner_audit_log", "audit_owner_log"),
    ("superadmin_audit_log", "audit_superadmin_log"),
    ("transfer_audit", "audit_transfer"),
    # bank_  (bank_transaction / bank_rule already carry it)
    ("stripe_bank_account", "bank_stripe_account"),
    # hr_
    ("time_clock_entry", "hr_time_clock_entry"),
    ("time_clock_shift", "hr_time_clock_shift"),
    ("store_employee_passkey", "hr_store_employee_passkey"),
    # msb_
    ("transfer", "msb_transfer"),
    ("customer", "msb_customer"),
    ("ach_batch", "msb_ach_batch"),
    ("daily_report", "msb_daily_report"),
    ("daily_line_item", "msb_daily_line_item"),
    ("daily_drop", "msb_daily_drop"),
    ("check_deposit", "msb_check_deposit"),
    ("mt_summary", "msb_mt_summary"),
    ("monthly_financial", "msb_monthly_financial"),
    ("return_check", "msb_return_check"),
    ("return_check_payment", "msb_return_check_payment"),
    ("tv_display", "msb_tv_display"),
    ("tv_display_country", "msb_tv_display_country"),
    ("tv_display_payout_bank", "msb_tv_display_payout_bank"),
    ("tv_display_rate", "msb_tv_display_rate"),
    ("tv_pairing", "msb_tv_pairing"),
    ("tv_pending_pair", "msb_tv_pending_pair"),
    ("tv_bank_catalog", "msb_tv_bank_catalog"),
    ("tv_catalog_logo", "msb_tv_catalog_logo"),
    ("tv_company_catalog", "msb_tv_company_catalog"),
    # retail_
    ("department", "retail_department"),
    ("department_sale", "retail_department_sale"),
    ("hourly_sale", "retail_hourly_sale"),
    ("register_close", "retail_register_close"),
    ("store_daily_entry", "retail_store_daily_entry"),
    ("store_daily_entry_original", "retail_store_daily_entry_original"),
    ("lottery_game", "retail_lottery_game"),
    ("lottery_pack", "retail_lottery_pack"),
    ("lottery_day_count", "retail_lottery_day_count"),
    ("pos_agent_credential", "retail_pos_agent_credential"),
    ("pos_journal_file", "retail_pos_journal_file"),
    ("pos_item_day_sale", "retail_pos_item_day_sale"),
    ("pos_merchandise_map", "retail_pos_merchandise_map"),
    ("pos_transaction", "retail_pos_transaction"),
    ("pos_transaction_line", "retail_pos_transaction_line"),
    ("pos_transaction_tender", "retail_pos_transaction_tender"),
    ("price_book_item", "retail_price_book_item"),
    ("vendor", "retail_vendor"),
    ("purchase_invoice", "retail_purchase_invoice"),
    ("purchase_invoice_line", "retail_purchase_invoice_line"),
]


def _q(ident: str) -> str:
    """Double-quote an identifier. ``user`` is a Postgres reserved
    word; quoting everything is simpler than remembering which."""
    return '"' + ident.replace('"', '""') + '"'


def _rename_pg_extras(bind: sa.engine.Connection, old: str, new: str) -> None:
    """Postgres: bring auto-named constraints and the id sequence
    along. Both are pure catalog renames."""
    names = bind.execute(
        sa.text(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
            "WHERE rel.relname = :t AND ns.nspname = current_schema()"
        ),
        {"t": new},
    ).scalars().all()
    for name in names:
        if name.startswith(old + "_"):
            op.execute(
                f"ALTER TABLE {_q(new)} RENAME CONSTRAINT {_q(name)} "
                f"TO {_q(new + name[len(old):])}"
            )
    seq_old, seq_new = f"{old}_id_seq", f"{new}_id_seq"
    have_seq = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace ns "
            "ON ns.oid = c.relnamespace WHERE c.relkind = 'S' "
            "AND c.relname = :s AND ns.nspname = current_schema()"
        ),
        {"s": seq_old},
    ).first()
    if have_seq:
        op.execute(f"ALTER SEQUENCE {_q(seq_old)} RENAME TO {_q(seq_new)}")


def _rename(old: str, new: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(old):
        if insp.has_table(new):
            # Already renamed — a re-run after a partial failure, or a
            # database that was built with the new names. Nothing to do.
            return
        raise RuntimeError(
            f"table {old!r} is missing and {new!r} does not exist; "
            "refusing to continue with an unknown schema"
        )
    if insp.has_table(new):
        raise RuntimeError(
            f"both {old!r} and {new!r} exist; resolve by hand before "
            "re-running"
        )

    old_prefix, new_prefix = f"ix_{old}_", f"ix_{new}_"
    indexes = [
        ix for ix in insp.get_indexes(old)
        if ix.get("name") and str(ix["name"]).startswith(old_prefix)
    ]

    op.rename_table(old, new)

    dialect = bind.dialect.name
    for ix in indexes:
        name = str(ix["name"])
        new_name = new_prefix + name[len(old_prefix):]
        if dialect == "postgresql":
            op.execute(f"ALTER INDEX {_q(name)} RENAME TO {_q(new_name)}")
        else:
            op.drop_index(name, table_name=new)
            op.create_index(
                new_name, new, list(ix["column_names"]),
                unique=bool(ix.get("unique")),
            )

    if dialect == "postgresql":
        _rename_pg_extras(bind, old, new)


def upgrade() -> None:
    for old, new in RENAMES:
        _rename(old, new)


def downgrade() -> None:
    for old, new in reversed(RENAMES):
        _rename(new, old)
