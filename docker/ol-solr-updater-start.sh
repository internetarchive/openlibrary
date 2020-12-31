#!/bin/bash

python --version
python scripts/new-solr-updater.py \
    -c $OL_CONFIG \
    --state-file /solr-updater-data/solr-update.offset \
    --ol-url http://web/
