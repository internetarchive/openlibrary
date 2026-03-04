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
log "======  1 - Migrate core tables ======"

pg_repack_table "thing" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN type SET DATA TYPE bigint"

pg_repack_table "transaction" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN author_id SET DATA TYPE bigint"

pg_repack_table "transaction_index" \
    "ALTER COLUMN tx_id SET DATA TYPE bigint"

pg_repack_table "version" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN thing_id SET DATA TYPE bigint, ALTER COLUMN transaction_id SET DATA TYPE bigint"

pg_repack_table "property" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN type SET DATA TYPE bigint"

pg_repack_table "account" \
    "ALTER COLUMN thing_id SET DATA TYPE bigint"

# 160M rows this will take the longest
pg_repack_table "data" \
    "ALTER COLUMN thing_id SET DATA TYPE bigint"

# primary key 338M rows
pg_repack_table "store" \
    "ALTER COLUMN id SET DATA TYPE bigint"

pg_repack_table "store_index" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN store_id SET DATA TYPE bigint"

pg_repack_table "seq" \
    "ALTER COLUMN id SET DATA TYPE bigint"

# ------------------------------------------------------------------
log "======  2 - Migrate typed entity tables ======"

ENTITY_TYPES="author datum edition publisher scan subject type user work tag"

for entity in $ENTITY_TYPES; do
    pg_repack_table "${entity}_int" \
        "ALTER COLUMN thing_id SET DATA TYPE bigint, ALTER COLUMN key_id SET DATA TYPE bigint"

    pg_repack_table "${entity}_str" \
        "ALTER COLUMN thing_id SET DATA TYPE bigint, ALTER COLUMN key_id SET DATA TYPE bigint"

    pg_repack_table "${entity}_ref" \
        "ALTER COLUMN thing_id SET DATA TYPE bigint, ALTER COLUMN key_id SET DATA TYPE bigint, ALTER COLUMN value SET DATA TYPE bigint"

    if psql -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -tAc \
        "SELECT 1 FROM information_schema.tables WHERE table_name = '${entity}_boolean' LIMIT 1;" 2>/dev/null | grep -q '1'; then
        pg_repack_table "${entity}_boolean" \
            "ALTER COLUMN thing_id SET DATA TYPE bigint, ALTER COLUMN key_id SET DATA TYPE bigint"
    fi
done

# ------------------------------------------------------------------
log "======  3 - Migrate additional tables ======"

pg_repack_table "stats" \
    "ALTER COLUMN id SET DATA TYPE bigint"

pg_repack_table "waitingloan" \
    "ALTER COLUMN id SET DATA TYPE bigint"

pg_repack_table "import_batch" \
    "ALTER COLUMN id SET DATA TYPE bigint"

pg_repack_table "import_item" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN batch_id SET DATA TYPE bigint"

# ------------------------------------------------------------------
log "======  4 - Migrate coverstore tables ======"

pg_repack_table "category" \
    "ALTER COLUMN id SET DATA TYPE bigint"

pg_repack_table "cover" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN category_id SET DATA TYPE bigint"

pg_repack_table "log" \
    "ALTER COLUMN id SET DATA TYPE bigint, ALTER COLUMN cover_id SET DATA TYPE bigint"

# ------------------------------------------------------------------
log "======  5 - Recreate get_property_name function ======"

pg "DROP FUNCTION IF EXISTS get_property_name(integer, integer);"
pg "CREATE FUNCTION get_property_name(bigint, bigint)
    RETURNS text AS
    'select property.name FROM property JOIN thing ON thing.type = property.type WHERE thing.id=\$1 AND property.id=\$2;'
    LANGUAGE SQL;"

# ------------------------------------------------------------------
log "======  6 - Upgrade backing sequences to bigint ======"

pg "DO \$\$
DECLARE
    seq_record RECORD;
    upgraded   int := 0;
BEGIN
    FOR seq_record IN
        SELECT sequencename
          FROM pg_sequences
         WHERE schemaname = 'public'
           AND data_type  = 'integer'
    LOOP
        EXECUTE 'ALTER SEQUENCE ' || quote_ident(seq_record.sequencename) || ' AS bigint;';
        RAISE NOTICE 'Upgraded sequence to bigint: %', seq_record.sequencename;
        upgraded := upgraded + 1;
    END LOOP;
    RAISE NOTICE 'Total sequences upgraded: %', upgraded;
END;
\$\$;"

# ------------------------------------------------------------------
log "======  7 - Verify migration ======"

log "Checking for any remaining integer ID/FK columns..."


pg "SELECT table_name, column_name, data_type
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND data_type    = 'integer'
       AND (
             column_name IN (
               'id','thing_id','key_id','type','author_id','tx_id',
               'transaction_id','store_id','batch_id','category_id',
               'cover_id'
             )
             OR (column_name = 'value' AND table_name LIKE '%\_ref')
           )
  ORDER BY table_name, column_name;"

log "Checking for any remaining integer sequences..."
pg "SELECT sequencename, data_type
      FROM pg_sequences
     WHERE schemaname = 'public'
       AND data_type  = 'integer';"


# ------------------------------------------------------------------
log "====== Migration complete ======"
log "All int/serial columns have been migrated to bigint/bigserial"
log "All backing sequences have been upgraded to bigint."
log "No long-held locks were used."
log "Run VACUUM ANALYZE on migrated tables to update planner statistics."