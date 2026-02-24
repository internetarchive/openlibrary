#!/bin/bash
set -euo pipefail

# Solr startup wrapper for local dev
# Compares OL schema file to Solr's core schema file, deletes core if different
# Then runs solr-precreate which creates new core or uses existing
# Only runs in dev mode (LOCAL_DEV=true)

PREFIX="[ol-solr-start]"

# This directory is volume mounted in and contains the latest/greatest
CONFIG_PATH="/opt/solr/server/solr/configsets/olconfig"
OL_SCHEMA_FILE="${CONFIG_PATH}/conf/managed-schema.xml"

# This is where solr configs/data are stored in the container ; copied from the
# volume mount by precreate if core doesn't exist
CORE_NAME="openlibrary"
SOLR_SCHEMA_FILE="/var/solr/data/${CORE_NAME}/conf/managed-schema.xml"

echo "${PREFIX} Running"

# If local-dev and schema files exist in solr + ol
if [ "$LOCAL_DEV" = "true" ] && [ -f "$OL_SCHEMA_FILE" ] && [ -f "$SOLR_SCHEMA_FILE" ]; then

    # If the schema files differ
    if ! diff -q "$OL_SCHEMA_FILE" "$SOLR_SCHEMA_FILE" >/dev/null 2>&1; then
        echo "${PREFIX} Schema files has been updated. Attempting to resolve by deleting and recreating Solr core..."

        # Start Solr in background (on tmp port 8989)
        TMP_SOLR_PORT=8989
        solr start -p $TMP_SOLR_PORT
        # Wait for solr core to be ready for searching
        until curl -s -o /dev/null -w "%{http_code}" "http://localhost:${TMP_SOLR_PORT}/solr/${CORE_NAME}/select?q=*:*&rows=0&wt=json" | grep -q "200"; do
            sleep 5;
        done

        TOTAL_SOLR_DOCS=$(curl -s "http://localhost:${TMP_SOLR_PORT}/solr/${CORE_NAME}/select?q=*:*&rows=0&wt=json" | grep -oE '"numFound":[0-9]+' | grep -oE '[0-9]+')
        echo "${PREFIX} Current Solr core has $TOTAL_SOLR_DOCS documents"

        # If there are more than 10000 documents, error and exit instead of deleting core
        if [ "$TOTAL_SOLR_DOCS" -gt 10000 ]; then
            echo "${PREFIX} ERROR: Solr core has more than 10000 documents. Refusing to delete core to prevent data loss."
            solr stop -p $TMP_SOLR_PORT
            exit 1
        fi

        solr delete -c "$CORE_NAME" --solr-url "http://localhost:$TMP_SOLR_PORT"
        solr stop -p $TMP_SOLR_PORT
    fi
fi

# In all cases, exec into precreate
exec solr-precreate "$CORE_NAME" "$CONFIG_PATH"
