#!/bin/bash
set -euo pipefail

# Solr startup wrapper for local dev
# Compares OL schema file to Solr's core schema file; exits with a clear error
# message if they differ (Solr 10 does not support automatic core migration).
# Then runs solr-precreate which creates new core or uses existing.
# Only runs in dev mode (LOCAL_DEV=true)

PREFIX="[ol-local-solr-start]"

# This directory is volume mounted in and contains the latest/greatest
CONFIG_PATH="/opt/solr/server/solr/configsets/olconfig"
OL_SCHEMA_FILE="${CONFIG_PATH}/conf/managed-schema.xml"

# This is where solr configs/data are stored in the container ; copied from the
# volume mount by precreate if core doesn't exist
CORE_NAME="openlibrary"
SOLR_SCHEMA_FILE="/var/solr/data/${CORE_NAME}/conf/managed-schema.xml"

echo "${PREFIX} Running"

if [ "$LOCAL_DEV" != "true" ]; then
    echo "${PREFIX} Not in local dev mode; this script should not be running. Exiting with error."
    exit 1
fi

# If local-dev and schema files exist in solr + ol
if [ -f "$OL_SCHEMA_FILE" ] && [ -f "$SOLR_SCHEMA_FILE" ]; then
    # If the schema files differ
    if ! diff -q "$OL_SCHEMA_FILE" "$SOLR_SCHEMA_FILE" >/dev/null 2>&1; then
        echo "${PREFIX} ERROR: managed-schema.xml has changed since the Solr core was created."
        echo "${PREFIX} Solr 10 does not support automatic core migration."
        echo "${PREFIX} To apply the new schema, delete the Solr data volume and restart:"
        echo "${PREFIX}   docker compose down -v && docker compose up -d"
        echo "${PREFIX} WARNING: this deletes your local Solr index. Safe in local dev;"
        echo "${PREFIX} the index will be rebuilt on next startup via 'make reindex-solr'."
        exit 1
    fi
fi

# In all cases, exec into precreate
exec solr-precreate "$CORE_NAME" "$CONFIG_PATH"
