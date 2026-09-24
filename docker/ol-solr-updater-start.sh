#!/bin/bash

python --version
source docker/ol-install-missing-deps.sh
OSP_DUMP_LOCATION="/solr-updater-data/osp_totals.db"
# If the osp dump file does not exist, download it. Takes ~30s
# Keep link in sync with Makefile and Jenkinsfile
curl -L --output $OSP_DUMP_LOCATION \
    --progress-bar --continue-at - \
    https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db

ls -la /solr-updater-data/

# Run in background
echo "Starting trending updater"
python scripts/solr_updater/trending_updater.py \
    "$OL_CONFIG" \
    --trending-offset-file /solr-updater-data/$TRENDING_OFFSET_FILE &

# Supervised, unlike its neighbours. This one can exit deliberately -- it
# refuses to start when it cannot establish ground truth, rather than following
# events against an index where nothing is marked. Backgrounded with `&` behind
# the foreground solr_updater, an exit would otherwise be permanent and
# invisible: the container stays healthy, `restart: unless-stopped` never fires,
# and the field silently freezes. The loop turns every fatal path into a retry.
echo "Starting loan availability updater"
(
  while true; do
    python scripts/solr_updater/loan_availability_updater.py \
        "$OL_CONFIG" \
        --state-file /solr-updater-data/$LOAN_STATE_FILE
    echo "loan availability updater exited ($?); restarting in 60s"
    sleep 60
  done
) &

echo "Starting Solr updater"
python scripts/solr_updater/solr_updater.py "$OL_CONFIG" \
    --state-file /solr-updater-data/$STATE_FILE \
    --ol-url "$OL_URL" \
    --osp-dump "$OSP_DUMP_LOCATION" \
    --socket-timeout 1800
