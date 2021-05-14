#!/bin/bash

python --version
python scripts/new-solr-updater.py $OL_CONFIG \
    --state-file /solr-updater-data/$STATE_FILE \
    --ol-url "$OL_URL" \
    --exclude-edits-containing 'Bot' \
    --socket-timeout 1800 \
    $EXTRA_OPTS
