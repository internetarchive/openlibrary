#!/bin/bash

python --version
OSP_DUMP_LOCATION="/solr-updater-data/osp_totals.db"
# if the osp dump file does not exist, download it. Takes ~30s
# When we update the python image we can use the --no-clobber option to avoid downloading the file again
# https://github.com/internetarchive/openlibrary/pull/8790
if [ ! -f "$OSP_DUMP_LOCATION" ]; then
    # Keep link in sync with Makefile and Jenkinsfile
    curl -L "https://archive.org/download/2023_openlibrary_osp_counts/osp_totals.db" --output "$OSP_DUMP_LOCATION"
fi
ls -la /solr-updater-data/
python scripts/solr_updater.py $OL_CONFIG \
    --state-file /solr-updater-data/$STATE_FILE \
    --ol-url "$OL_URL" \
    --osp-dump "$OSP_DUMP_LOCATION" \
    --socket-timeout 1800 \
    $EXTRA_OPTS
