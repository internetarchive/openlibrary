#!/bin/bash

python --version
OSP_DUMP_LOCATION="/solr-updater-data/osp_totals.db"
# If the osp dump file does not exist, download it. Takes ~30s
# Keep link in sync with Makefile and Jenkinsfile
curl -L --output $OSP_DUMP_LOCATION \
    --progress-bar --continue-at - \
    https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db

ls -la /solr-updater-data/
PYTHONPATH=. python scripts/solr_updater/solr_updater.py $OL_CONFIG \
    --state-file /solr-updater-data/$STATE_FILE \
    --ol-url "$OL_URL" \
    --osp-dump "$OSP_DUMP_LOCATION" \
    --socket-timeout 1800 \
    $EXTRA_OPTS
