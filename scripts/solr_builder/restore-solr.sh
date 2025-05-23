#!/bin/bash
# E.g. `./restore-solr.sh ol-solr0 ol-solr1` will restore the ol-solr1 dump on ol-solr0

set -e
source ./scripts/solr_builder/utils.sh

# Only tested from ol-solr0
SOLR_NAME="$1"
SOLR_DUMP="$2"
SOLR_HOST="$(ol_server $SOLR_NAME)"
DUMP_FILE="${SOLR_DUMP}_dump.tar.gz"
OFFSET_FILE="${SOLR_DUMP}_dump.offset"
SOLR_DUMP_LINK="https://archive.org/download/ol_solr_dump/${DUMP_FILE}"
SOLR_OFFSET_LINK="https://archive.org/download/ol_solr_dump/${OFFSET_FILE}"
OL_HOME="ol-home0.us.archive.org"

if [ "$SOLR_NAME" != "ol-solr0" ]; then
    echo "ERROR: This script is only tested for ol-solr0"
    exit 1
fi

echo "Downloading the solr dump (~10min 2025-04-02)"
date
ssh -t $SOLR_HOST "
    set -e
    mkdir -p /tmp/solr
    cd /tmp/solr
    time wget $SOLR_DUMP_LINK -O ${DUMP_FILE}
"

echo "Stopping solr-updater"
ssh $OL_HOME 'docker stop openlibrary-solr-updater-1 || true'

# Clean up any data
# Remove containers/volumes/images
echo -n "Stopping solr ..."
ssh $SOLR_HOST "
    cd /opt/openlibrary
    export COMPOSE_FILE='compose.yaml:compose.production.yaml'
    docker compose --profile ol-solr0 down
"
echo "✓"

# Prune everything! This deletes the actual solr data volumes
echo "Pruning everything docker ... "
ssh $SOLR_HOST "
    docker system prune -f --all --volumes
    docker volume rm openlibrary_solr-data || true
"

echo "Load solr dump into prod server (took 20 minutes on 2024-08)"
date
time ssh $SOLR_HOST "
    docker run \
        -v openlibrary_solr-data:/var/solr \
        -v /tmp/solr:/tmp/solr \
        ubuntu:bionic \
        tar xzf /tmp/solr/$DUMP_FILE
"

# note using single quotes so variable expansion doesn't happen here, but
# on the other server (so HOSTNAME is correct)
echo "Bringing it up up up!"
ssh -t $SOLR_HOST '
    set -e

    cd /opt/openlibrary
    # For solr restart, pull separately to handle nexus HTTPS bug
    docker pull node:22
    source /opt/olsystem/bin/build_env.sh

    export COMPOSE_FILE="compose.yaml:compose.production.yaml"
    HOSTNAME="$HOSTNAME" docker compose --profile ol-solr0 up --build -d
'

# Wait a bit for it to warm up
sleep 15

# Download the offset file
ssh $OL_HOME "
    set -e
    mkdir -p /tmp/solr
    wget $SOLR_OFFSET_LINK -O /tmp/solr/${OFFSET_FILE}
    docker run --rm \
        -v /tmp/solr:/tmp/solr \
        --volumes-from openlibrary-solr-updater-1 \
        ubuntu:bionic \
        cp /tmp/solr/${OFFSET_FILE} /solr-updater-data/solr-update.offset
"

# Switch the compose.production.yaml file to replace --no-solr-next with --solr-next
# This will make the solr-updater use the new solr logic
ssh $OL_HOME '
    set -e
    sed -i 's/--no-solr-next/--solr-next/' /opt/openlibrary/compose.production.yaml

    cd /opt/openlibrary
    export COMPOSE_FILE="compose.yaml:compose.production.yaml"
    HOSTNAME="$HOSTNAME" docker compose up -d --no-deps solr-updater
'

echo "Solr restore complete!"
