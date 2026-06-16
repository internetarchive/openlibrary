#!/bin/bash
#Currently, this script is used just for testing with a mock on local. If this makes it through with 'reset=True' and 'use_ia = False', something has gone wrong. 
python3 scripts/solr_updater/loan_availability_updater.py "$OL_CONFIG"\
    --state-file /solr-updater-data/"$STATE_FILE" 