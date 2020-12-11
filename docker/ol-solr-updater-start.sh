#!/bin/bash

python --version
scripts/new-solr-updater.py
    --config $OL_CONFIG
    --state-file $SOLR_UPDATER_STATE_FILE
    --exclude-edits-containing $SOLR_UPDATER_EXCLUDE_EDITS_CONTAINING
    --socket-timeout $SOLR_UPDATER_SOCKET_TIMEOUT
