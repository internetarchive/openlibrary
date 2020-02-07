#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

# Display each line before running it
set -o xtrace

# One of 'work' or 'author'
TYPE="$1"
INSTANCES="$2"
DB_TYPE="/type/${TYPE}"
COUNT=$(psql -c "SELECT count(*) FROM test WHERE \"Type\" = '${DB_TYPE}'")
CHUNK_SIZE=$(pymath "ceil($COUNT / $INSTANCES)")

# Partitions the database (~35s)
PARTITION=$(time psql -c "SELECT \"Key\" FROM test_get_partition_markers('${DB_TYPE}', $CHUNK_SIZE);")
ITER=1
for key in $PARTITION; do
  RUN_SIG="${TYPE}s_${ITER}"
  # Create log files so they're acceissble sync for querying
  touch {progress,logs}/$RUN_SIG.txt
  docker_solr_builder "${TYPE}s" --start-at $key --limit $CHUNK_SIZE -p progress/$RUN_SIG.txt -l logs/$RUN_SIG.txt
  ((ITER++))
  sleep 60
done;
