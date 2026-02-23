#!/bin/bash

# Solr startup wrapper for local dev
# Handles schema changes by detecting and recreating the core
# Only runs in dev mode (LOCAL_DEV=true)

set -e

CORE_NAME="openlibrary"
CONFIG_PATH="/opt/solr/server/solr/configsets/olconfig"
SCHEMA_FILE="${CONFIG_PATH}/conf/managed-schema.xml"

wait_for_solr() {
    local max_attempts=30
    local attempt=1
    echo "Waiting for Solr to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s "http://localhost:8983/solr/admin/info/system" > /dev/null 2>&1; then
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

create_core() {
    echo "Creating Solr core '$CORE_NAME' with config from $CONFIG_PATH"
    solr create_core -c "$CORE_NAME" -d "$CONFIG_PATH"
}

delete_core() {
    echo "Deleting Solr core '$CORE_NAME'"
    solr delete -c "$CORE_NAME" 2>/dev/null || true
}

if [ "$LOCAL_DEV" = "true" ]; then
    echo "LOCAL_DEV mode - starting Solr with schema migration support..."

    # Check if schema file exists
    if [ ! -f "$SCHEMA_FILE" ]; then
        echo "ERROR: Schema file not found at $SCHEMA_FILE"
        exit 1
    fi

    # Start solr in foreground
    solr -c &
    SOLR_PID=$!

    # Wait for solr to be ready
    if ! wait_for_solr; then
        kill $SOLR_PID 2>/dev/null || true
        exit 1
    fi

    # Check if core exists
    CORE_EXISTS=$(curl -s "http://localhost:8983/solr/${CORE_NAME}/admin/ping" > /dev/null 2>&1 && echo "yes" || echo "no")

    if [ "$CORE_EXISTS" = "yes" ]; then
        echo "Core '$CORE_NAME' exists - checking for schema changes..."

        # Get schema from Solr and compare to our schema file
        SOLR_SCHEMA=$(curl -s "http://localhost:8983/solr/${CORE_NAME}/schema/managed-schema" 2>/dev/null || echo "")
        LOCAL_SCHEMA=$(cat "$SCHEMA_FILE")

        if [ "$SOLR_SCHEMA" != "$LOCAL_SCHEMA" ]; then
            echo "Schema has changed - rebuilding core..."
            delete_core
            sleep 2
            create_core
            echo "Core rebuilt with new schema."
            echo "IMPORTANT: DB has records but Solr is empty - run reindex from home container:"
            echo "  docker compose run --rm home make reindex-solr"
        else
            echo "Schema unchanged, using existing core"
        fi
    else
        echo "Core '$CORE_NAME' does not exist - creating new core..."
        create_core
        echo "New core created."
        echo "IMPORTANT: Run reindex to populate Solr:"
        echo "  docker compose run --rm home make reindex-solr"
    fi

    echo "Solr is ready at http://localhost:8983/solr/${CORE_NAME}"

    # Wait for solr process
    wait $SOLR_PID
else
    # Non-dev mode: use standard solr-precreate
    echo "Production mode - using solr-precreate"
    exec solr-precreate "$CORE_NAME" "$CONFIG_PATH"
fi
