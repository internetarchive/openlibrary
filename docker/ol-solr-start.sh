#!/bin/bash

# Solr startup wrapper for local dev
# Compares OL schema file to Solr's core schema file, deletes core if different
# Then runs solr-precreate which creates new core or uses existing
# Only runs in dev mode (LOCAL_DEV=true)

CORE_NAME="openlibrary"
CONFIG_PATH="/opt/solr/server/solr/configsets/olconfig"
OL_SCHEMA_FILE="${CONFIG_PATH}/conf/managed-schema.xml"
SOLR_DATA="/var/solr/data"
SOLR_SCHEMA_FILE="${SOLR_DATA}/${CORE_NAME}/conf/managed-schema.xml"

wait_for_solr() {
    local port="${1:-8983}"
    local max_attempts=30
    local attempt=1
    echo "Waiting for Solr to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:${port}/solr/admin/info/system" > /dev/null 2>&1; then
            echo "Solr is ready"
            return 0
        fi
        echo "Attempt $attempt/$max_attempts - waiting..."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo "ERROR: Solr did not become ready in time"
    return 1
}

echo "Running ol-solr-start.sh"

# If local-dev and schema files exist in solr + ol
if [ "$LOCAL_DEV" = "true" ] && [ -f "$OL_SCHEMA_FILE" ] && [ -f "$SOLR_SCHEMA_FILE" ]; then

    # If the schema files differ
    if ! diff -q "$OL_SCHEMA_FILE" "$SOLR_SCHEMA_FILE" >/dev/null 2>&1; then
        # Start Solr in background (on tmp port 8989)
        TMP_SOLR_PORT=8989
        solr start -p $TMP_SOLR_PORT || {
            echo "ERROR: failed to start Solr on port $TMP_SOLR_PORT"
            exit 1
        }

	if ! wait_for_solr $TMP_SOLR_PORT; then
            echo "ERROR: Solr did not become ready on port $TMP_SOLR_PORT"
            solr stop -p $TMP_SOLR_PORT >/dev/null 2>&1 || true
            exit 1
        fi

        echo "Schema missing or differs — deleting core..."
	solr delete -c "$CORE_NAME" --solr-url http://localhost:"$TMP_SOLR_PORT" || echo "WARNING: core deletion failed"

        # Proper shutdown
        solr stop -p $TMP_SOLR_PORT || true
    fi
fi

# In all cases, exec into precreate
exec solr-precreate "$CORE_NAME" "$CONFIG_PATH"
