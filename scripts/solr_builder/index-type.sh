#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

# Display each line before running it
set -o xtrace

# One of 'work' or 'author'
TYPE="$1"
INSTANCES="$2"
LOG_DIR="$3"
DB_TYPE="/type/${TYPE}"
COUNT=21957112
CHUNK_SIZE=$(pymath "ceil($COUNT / $INSTANCES)")

# Partitions the database (~35s)
PARTITION='/works/OL10000000W /works/OL17982239W /works/OL336052W'
ITER=1
for key in $PARTITION; do
  RUN_SIG="ol_run_${TYPE}s_${ITER}"
  # Create log files so they're acceissble sync for querying
  mkdir -p {logs,progress}/$LOG_DIR
  touch {logs,progress}/$LOG_DIR/$RUN_SIG.txt
  DOCKER_IMAGE_NAME=$RUN_SIG docker_solr_builder "${TYPE}s" --start-at "/$key" --limit $CHUNK_SIZE -p "progress/$LOG_DIR/$RUN_SIG.txt"
  ((ITER++))
  sleep 5
done;
