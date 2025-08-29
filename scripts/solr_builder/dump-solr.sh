#!/bin/bash

set -e
source ./scripts/solr_builder/utils.sh

OL_HOME="ol-home0.us.archive.org"
SOLR_SERVER=$1
SOLR_HOST="$(ol_server $SOLR_SERVER)"
DUMP_FILE="${SOLR_SERVER}_dump.tar.gz"
DUMP_OFFSET_FILE="${SOLR_SERVER}_dump.offset"

if [ "$SOLR_SERVER" == "ol-solr0" ]; then
    solr_container="openlibrary-solr-1"
    solr_updater_container="openlibrary-solr-updater-1"
    offset_file="solr-update.offset"
elif [ "$SOLR_SERVER" == "ol-solr1" ]; then
    solr_container="solr_builder-solr_prod-1"
    solr_updater_container="openlibrary-solr-next-updater-1"
    offset_file="solr-next-update.offset"
else
    echo "Invalid SOLR_SERVER: $SOLR_SERVER"
    exit 1
fi

# Make sure it has ubuntu xenial and openlibrary/olbase:latest
echo "Pulling down images on $SOLR_SERVER ... "
ssh -t $SOLR_SERVER "
    set -e
    docker pull ubuntu:xenial
    docker pull openlibrary/olbase:latest
"

echo "Check if either solr-dump container is running"
echo -n "  solr-dump ... "
solr_dump_running=$(ssh $SOLR_SERVER "docker ps --quiet --filter name=solr-dump")
if [ -n "$solr_dump_running" ]; then
    echo "âœ— ERROR: $SOLR_SERVER has a solr-dump container running"
    exit 1
else
    echo "âœ“"
fi
echo -n "  solr-dump-upload ... "
solr_dump_upload_running=$(ssh $SOLR_SERVER "docker ps --quiet --filter name=solr-dump-upload")
if [ -n "$solr_dump_upload_running" ]; then
    echo "âœ— ERROR: $SOLR_SERVER has a solr-dump-upload container running"
    exit 1
else
    echo "âœ“"
fi


# Clean up old dumps
echo "Cleaning up old dumps on $SOLR_SERVER ... "
ssh $SOLR_SERVER "
    set -e
    rm -f /tmp/solr/$DUMP_FILE || true
    rm -f /tmp/solr/$DUMP_OFFSET_FILE || true
"


# Check if enough disk space
echo -n "Checking disk space on $SOLR_SERVER ... "
var_solr_size=$(ssh $SOLR_SERVER "
    set -e
    docker run --rm \
        --volumes-from $solr_container \
        ubuntu:xenial \
        du -s /var/solr | awk '{print \$1}'
")
empty_space=$(ssh $SOLR_SERVER "
    set -e
    df /tmp | tail -n 1 | awk '{print \$4}'
")
var_solr_size_str=$(numfmt --to=iec --suffix=B $((var_solr_size * 1000)))
empty_space_str=$(numfmt --to=iec --suffix=B $((empty_space * 1000)))

if [ $var_solr_size -gt $empty_space ]; then
    echo "âœ— ERROR: Not enough space on $SOLR_SERVER"
    echo "(/var/solr is $var_solr_size_str, $SOLR_SERVER has $empty_space_str free)"
    # exit 1
fi
echo "âœ“"
echo "(/var/solr is $var_solr_size_str, $SOLR_SERVER has $empty_space_str free)"

echo "Check if $solr_updater_container is running"
solr_updater_running=$(ssh $OL_HOME "docker ps --quiet --filter name=$solr_updater_container")

# If running, stop it
if [ -n "$solr_updater_running" ]; then
    echo -n "Stopping $solr_updater_container ..."
    ssh $OL_HOME "
        set -e
        docker stop $solr_updater_container
    " > /dev/null
    echo "âœ“"
else
    echo "$solr_updater_container not running"
fi

# Note the offset
offset=$(ssh $OL_HOME "
    set -e
    docker run --rm \
        --volumes-from $solr_updater_container \
        ubuntu:xenial \
        cat solr-updater-data/$offset_file
")
echo "solr-updater offset: $offset"
# Save the offset to /tmp/solr/ol_solr_dump_$(date +%Y-%m-%d).offset
ssh $SOLR_SERVER "
    set -e
    mkdir -p /tmp/solr
    echo '$offset' > /tmp/solr/$DUMP_OFFSET_FILE
"

echo "Committing any transient changes into solr before dumping... (takes ~30s)"
time ssh $SOLR_SERVER "
    set -e
    curl -s 'http://localhost:8984/solr/openlibrary/update?commit=true'
    sleep 15  # Just in case
"

echo "Pause solr"
ssh $SOLR_SERVER "docker pause $solr_container"

echo "Beginning dump (took 1h30 minutes 2024-08)"
echo "Dumping solr data to $SOLR_SERVER:/tmp/solr/$DUMP_FILE"
# Run detached so it persists if the ssh connection is lost
time ssh -t $SOLR_SERVER "
    set -e
    mkdir -p /tmp/solr
    docker run --rm -d \
        --name solr-dump \
        --volumes-from $solr_container \
        -v /tmp/solr:/tmp/solr \
        ubuntu:xenial \
        tar czf /tmp/solr/$DUMP_FILE /var/solr
    docker logs -f solr-dump
"

# Unpause solr
ssh $SOLR_SERVER "docker unpause $solr_container"

# Should be ~39G
ssh $SOLR_SERVER "du -sh /tmp/solr/$DUMP_FILE"

# Restart solr_updater_container if it was running
if [ -n "$solr_updater_running" ]; then
    echo -n "Starting $solr_updater_container ... "
    ssh $OL_HOME "
        set -e
        docker start $solr_updater_container
    " > /dev/null
    echo "âœ“"
fi

echo "Uploading dump to IA"
time ssh -t $SOLR_SERVER "
    set -e
    docker run --rm -d \
        --name solr-dump-upload \
        -v /tmp/solr:/tmp/solr \
        -v /opt/olsystem/etc/ia.ini:/olsystem/etc/ia.ini:ro \
        openlibrary/olbase:latest \
        bash -c '
            ia \
            --config-file=/olsystem/etc/ia.ini \
            upload ol_solr_dump \
            --retries 300 \
            -H x-archive-keep-old-version:0 \
            /tmp/solr/$DUMP_FILE \
            /tmp/solr/$DUMP_OFFSET_FILE \
            --metadata 'collection:ol_exports' \
            --metadata 'year:$(date +%Y)' \
            --metadata 'format:Data'
        '
    docker logs -f solr-dump-upload
"

echo "Dump complete!"
