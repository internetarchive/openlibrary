#!/bin/bash

python --version
source docker/ol-install-missing-deps.sh

# The Open Syllabus Project counts only fill the osp_count search field, so they are opt-in:
# production sets OSP_DUMP=1, local dev skips the download and starts right away.
OSP_ARGS=()
if [ -n "$OSP_DUMP" ]; then
    OSP_DUMP_LOCATION="/solr-updater-data/osp_totals.db"
    # Keep link in sync with Makefile and Jenkinsfile
    curl -L --output $OSP_DUMP_LOCATION \
        --progress-bar --continue-at - \
        https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db
    OSP_ARGS=(--osp-dump "$OSP_DUMP_LOCATION")
fi

ls -la /solr-updater-data/

# Run in background
echo "Starting trending updater"
python scripts/solr_updater/trending_updater.py \
    "$OL_CONFIG" \
    --trending-offset-file /solr-updater-data/$TRENDING_OFFSET_FILE &

EXTRA_ARGS=()
if [ -n "$EXCLUDE_EDITS_CONTAINING" ]; then
    EXTRA_ARGS+=(--exclude-edits-containing "$EXCLUDE_EDITS_CONTAINING")
fi

echo "Starting Solr updater"
python scripts/solr_updater/solr_updater.py "$OL_CONFIG" \
    --state-file /solr-updater-data/$STATE_FILE \
    --ol-url "$OL_URL" \
    "${OSP_ARGS[@]}" \
    --socket-timeout 1800 \
    "${EXTRA_ARGS[@]}"
