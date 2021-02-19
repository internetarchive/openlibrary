#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

set -o xtrace  # Display each line before running it

LOG_DIR="$1"
ORPHANS_COUNT=$(time psql -f sql/count-orphans.sql) # ~15min
RUN_SIG=ol_run_orphans_1

mkdir -p {logs,progress}/$LOG_DIR
touch {logs,progress}/$LOG_DIR/$RUN_SIG.txt
DOCKER_IMAGE_NAME=$RUN_SIG docker_solr_builder orphans -p "progress/$LOG_DIR/$RUN_SIG.txt"
