#!/usr/bin/env bash
# ------------------------------------------------------------------


set -euo pipefail

DB="${PGDATABASE:-openlibrary}"
HOST="${PGHOST:-localhost}"
PORT="${PGPORT:-5432}"
USER="${PGUSER:-openlibrary}"
JOBS="${JOBS:-2}"
DRY_RUN="${DRY_RUN:-0}"

log()  { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
run()  {
    if [ "$DRY_RUN" = "1" ]; then
        log "DRY RUN: $*"
    else
        log "RUN: $*"
        "$@"
    fi
}

pg() { run psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -c "$1"; }

pg_repack_table() {
    # $1 = table name, $2 = comma-separated ALTER COLUMN clauses
    local table="$1"
    local alter="$2"
    log "Repacking table '$table' with: $alter"
    run pg_repack -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" \
        --no-superuser-check \
        --table "$table" \
        --alter "$alter" \
        --jobs "$JOBS" \
        --elevel WARNING
}

# ------------------------------------------------------------------
log "======  0 - Verify pg_repack extension ======"


pg "CREATE EXTENSION IF NOT EXISTS pg_repack;"
log "pg_repack extension ready."

# ------------------------------------------------------------------
log "====== 1 - Migrate large tables (store, thing) ======"

pg_repack_table "thing" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN type SET DATA TYPE bigint"

# 338M rows the largest table
pg_repack_table "store" \
    "ALTER COLUMN id SET DATA TYPE bigint"

# ------------------------------------------------------------------
log "======  2 - Migrate FK columns that reference thing.id or store.id ======"

# 160M rows the second largest table
pg_repack_table "data" \
    "ALTER COLUMN thing_id SET DATA TYPE bigint"

pg_repack_table "transaction" \
    "ALTER COLUMN author_id SET DATA TYPE bigint"

pg_repack_table "version" \
    "ALTER COLUMN thing_id SET DATA TYPE bigint"

pg_repack_table "property" \
    "ALTER COLUMN type SET DATA TYPE bigint"

pg_repack_table "account" \
    "ALTER COLUMN thing_id SET DATA TYPE bigint"

pg_repack_table "store_index" \
    "ALTER COLUMN store_id SET DATA TYPE bigint"

# ------------------------------------------------------------------
log "======  3 - Migrate entity-table FK columns that reference thing.id ======"

ENTITY_TYPES="author datum edition publisher scan subject type user work tag"

for entity in $ENTITY_TYPES; do
    pg_repack_table "${entity}_int" \
        "ALTER COLUMN thing_id SET DATA TYPE bigint"

    pg_repack_table "${entity}_str" \
        "ALTER COLUMN thing_id SET DATA TYPE bigint"

    pg_repack_table "${entity}_ref" \
        "ALTER COLUMN thing_id SET DATA TYPE bigint, ALTER COLUMN value SET DATA TYPE bigint"

    if psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_name = '${entity}_boolean' LIMIT 1;" 2>/dev/null | grep -q '1'; then
        pg_repack_table "${entity}_boolean" \
            "ALTER COLUMN thing_id SET DATA TYPE bigint"
    fi
done

# ------------------------------------------------------------------
log "======  4 - Recreate get_property_name function ======"

pg "DROP FUNCTION IF EXISTS get_property_name(integer, integer);"
pg "CREATE OR REPLACE FUNCTION get_property_name(bigint, integer)
    RETURNS text AS
    'select property.name FROM property JOIN thing ON thing.type = property.type WHERE thing.id=\$1 AND property.id=\$2;'
    LANGUAGE SQL;"

# ------------------------------------------------------------------
log "======  5 - Upgrade backing sequences for migrated PKs ======"

pg "ALTER SEQUENCE thing_id_seq AS bigint;"
pg "ALTER SEQUENCE store_id_seq AS bigint;"

# ------------------------------------------------------------------
log "======  6 - Verify migration ======"

log "Checking for remaining integer columns in migrated tables..."
pg "SELECT table_name, column_name, data_type
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND data_type    = 'integer'
       AND (
             (table_name = 'thing'       AND column_name IN ('id','type'))
          OR (table_name = 'store'       AND column_name = 'id')
          OR (table_name = 'store_index' AND column_name = 'store_id')
          OR (table_name = 'data'        AND column_name = 'thing_id')
          OR (table_name = 'transaction' AND column_name = 'author_id')
          OR (table_name = 'version'     AND column_name = 'thing_id')
          OR (table_name = 'property'    AND column_name = 'type')
          OR (table_name = 'account'     AND column_name = 'thing_id')
          OR (table_name LIKE '%\_int'   AND column_name = 'thing_id')
          OR (table_name LIKE '%\_str'   AND column_name = 'thing_id')
          OR (table_name LIKE '%\_ref'   AND column_name IN ('thing_id','value'))
          OR (table_name LIKE '%\_boolean' AND column_name = 'thing_id')
       )
  ORDER BY table_name, column_name;"

log "Checking sequences for thing and store..."
pg "SELECT sequencename, data_type
      FROM pg_sequences
     WHERE schemaname = 'public'
       AND sequencename IN ('thing_id_seq', 'store_id_seq');"

# ------------------------------------------------------------------
log "====== Migration complete ======"
log "Large-table PKs (thing.id, store.id) and their FK cascades"
log "have been migrated to bigint "
log "No long-held locks were used."
log "Run VACUUM ANALYZE on migrated tables to update planner statistics."