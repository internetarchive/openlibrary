#!/bin/bash

python --version
python scripts/new-solr-updater.py \
    --config $OL_CONFIG \
    --state-file /solr-updater-data/solr-update.offset \
    --ol-url "$OL_URL" \
    --exclude-edits-containing 'Bot' \
    --socket-timeout 1800
