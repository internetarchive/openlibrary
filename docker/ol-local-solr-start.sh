#!/bin/bash
set -euo pipefail

# Solr startup wrapper for local dev
# Check for config file changes that require a new solr data volume.
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

echo_reset_instructions() {
    echo "${PREFIX}"
    echo "${PREFIX} To fix this, delete the Solr data volume and restart:"
    echo "${PREFIX}     docker compose down"
    echo "${PREFIX}     docker volume rm openlibrary_solr-data openlibrary_solr-updater-data"
    echo "${PREFIX}     docker compose up -d"
    echo "${PREFIX}"
    echo "${PREFIX} Note this deletes your local Solr index. Safe in local dev;"
    echo "${PREFIX} the index will be rebuilt on next startup."
}

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
        echo "${PREFIX}"
        echo "${PREFIX} Diff:"
        diff "$OL_SCHEMA_FILE" "$SOLR_SCHEMA_FILE" 2>&1 | sed "s/^/${PREFIX} /" || true
        echo_reset_instructions
        exit 1
    fi
fi

# Check Solr version against the stamp written on first startup.
SOLR_VERSION=$(solr --version 2>/dev/null)
SOLR_VERSION_FILE="/var/solr/data/.ol_local_solr_version"

if [ -f "$SOLR_VERSION_FILE" ]; then
    STORED_VERSION=$(cat "$SOLR_VERSION_FILE")
    if [ "$STORED_VERSION" != "$SOLR_VERSION" ]; then
        echo "${PREFIX} ERROR: Solr data volume was created with Solr ${STORED_VERSION}, but the current image is Solr ${SOLR_VERSION}."
        echo_reset_instructions
        exit 1
    fi
else
    echo "$SOLR_VERSION" > "$SOLR_VERSION_FILE"
fi

# In all cases, exec into precreate
exec solr-precreate "$CORE_NAME" "$CONFIG_PATH"
