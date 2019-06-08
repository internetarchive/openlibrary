#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

set -o xtrace  # Display each line before running it

AUTHOR_COUNT=$(time psql -c "SELECT count(*) FROM test WHERE \"Type\" = '/type/author'") # ~25s
AUTHOR_INSTANCES=6
AUTHORS_CHUNK_SIZE=$(pymath "ceil($AUTHOR_COUNT / $AUTHOR_INSTANCES)")

# Partitions the database (~23s)
AUTHORS_PARTITIONS=$(time psql -c "SELECT \"Key\" FROM test_get_partition_markers('/type/author', $AUTHORS_CHUNK_SIZE)")
for key in $AUTHORS_PARTITIONS; do
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder authors --start-at $key --limit $AUTHORS_CHUNK_SIZE -p progress/$RUN_SIG.txt
  echo sleep 60 | tee /dev/tty | bash;
done;