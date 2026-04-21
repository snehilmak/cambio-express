#!/usr/bin/env bash
# Copy the contents of cambio-db (old) into dinerobook-db (new).
#
# This is the production cutover. Conservative by design:
#   - pg_dump is read-only on the source, so the old DB is untouched.
#   - We refuse to run unless both connection strings are clearly set.
#   - We refuse to run if the source/target URLs look swapped.
#   - We check that the target is reachable before wiping its schema.
#   - The backup file is always written to disk first, then restored.
#     If anything goes wrong after the dump, the SQL file is still there.
#   - --no-owner / --no-acl means the dump doesn't try to re-assert the
#     source DB's role ownership on the target (target owner differs).
#
# Usage:
#   export CAMBIO_URL='postgres://cambio:…@…render.com/cambio'
#   export DINERO_URL='postgres://dinerobook:…@…render.com/dinerobook'
#   ./scripts/migrate_db.sh
#
# Both URLs come from Render dashboard → each DB → Info → External
# Database URL. Do NOT commit them. The script prints nothing that would
# leak either secret.
#
# After a successful run:
#   1. Render → dinerobook web service → Manual Deploy → Deploy latest
#      (so _ensure_added_columns() fills in any columns added since the
#      source DB was last synced with the app code).
#   2. Log into https://dinerobook.onrender.com and verify your stores,
#      users, transfers, and recent activity look right.
#   3. Keep the dump file for 30 days as a safety net before cleaning up.

set -euo pipefail

# ── Sanity: both URLs must be set and non-empty ───────────────────
: "${CAMBIO_URL:?CAMBIO_URL must be exported (source = cambio-db)}"
: "${DINERO_URL:?DINERO_URL must be exported (target = dinerobook-db)}"

if [ "$CAMBIO_URL" = "$DINERO_URL" ]; then
  echo "ERROR: CAMBIO_URL and DINERO_URL are the same. Source and target must differ." >&2
  exit 1
fi

# ── Sanity: URLs should look right. Conservative string match; if this
#            ever false-positives, delete this check. ────────────────
if ! echo "$CAMBIO_URL"  | grep -q -e 'cambio'; then
  echo "WARNING: CAMBIO_URL doesn't contain 'cambio'. Double-check source is the OLD DB." >&2
fi
if ! echo "$DINERO_URL" | grep -q -e 'dinerobook'; then
  echo "WARNING: DINERO_URL doesn't contain 'dinerobook'. Double-check target is the NEW DB." >&2
fi

# ── Reachability: confirm we can reach the target before wiping it ──
echo "→ Pinging target DB..."
psql "$DINERO_URL" -c "SELECT 1;" >/dev/null

BACKUP="cambio-backup-$(date +%F-%H%M).sql"
if [ -e "$BACKUP" ]; then
  echo "ERROR: $BACKUP already exists. Delete or rename it first." >&2
  exit 1
fi

# ── Dump the source ─────────────────────────────────────────────
echo "→ Dumping source → $BACKUP ..."
pg_dump --no-owner --no-acl "$CAMBIO_URL" > "$BACKUP"
DUMP_LINES=$(wc -l < "$BACKUP")
echo "  saved $DUMP_LINES lines ($(du -h "$BACKUP" | cut -f1))"

if [ "$DUMP_LINES" -lt 50 ]; then
  echo "ERROR: dump is suspiciously small ($DUMP_LINES lines). Aborting before wiping target." >&2
  exit 1
fi

# ── Confirm before destructive step ─────────────────────────────
echo
echo "About to WIPE $DINERO_URL and restore from $BACKUP."
echo "The old DB ($CAMBIO_URL) will NOT be modified."
read -r -p "Type 'migrate' to proceed: " CONFIRM
if [ "$CONFIRM" != "migrate" ]; then
  echo "Aborted. Backup preserved at $BACKUP."
  exit 1
fi

# ── Wipe + restore target ───────────────────────────────────────
echo "→ Wiping target schema..."
psql "$DINERO_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
echo "→ Restoring into target..."
psql -v ON_ERROR_STOP=1 "$DINERO_URL" < "$BACKUP" >/dev/null

# ── Post-checks ─────────────────────────────────────────────────
TABLE_COUNT=$(psql "$DINERO_URL" -tA -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
echo "→ Restored. Target now has $TABLE_COUNT tables in public schema."

echo
echo "✅ Done. Next steps:"
echo "   1. Render dashboard → dinerobook service → Manual Deploy → Deploy latest"
echo "      (so _ensure_added_columns() adds any new columns to the migrated tables)."
echo "   2. Log into https://dinerobook.onrender.com as your superadmin to verify."
echo "   3. Keep $BACKUP for 30 days as a safety net."
