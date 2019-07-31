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
for key in $PARTITION; do
  OLID=$(echo "${key}" | grep -oe 'OL[0-9]*[MWA]')
  RUN_SIG="${TYPE}s_${OLID}"
  docker_solr_builder "${TYPE}s" --start-at $key --limit $CHUNK_SIZE -p progress/$RUN_SIG.txt -l logs/$RUN_SIG.txt
  sleep 10
done;
