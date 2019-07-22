#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

set -o xtrace  # Display each line before running it

AUTHOR_COUNT=$(time psql -c "SELECT count(*) FROM entity WHERE etype = CAST('/type/author' AS type_enum)") # ~25s
AUTHOR_COUNT=${AUTHOR_COUNT//$'\r'/}
AUTHOR_INSTANCES=6
AUTHORS_CHUNK_SIZE=$(pymath "ceil($AUTHOR_COUNT / $AUTHOR_INSTANCES)")

# Partitions the database (~23s)
AUTHORS_PARTITIONS=$(time psql -c "SELECT keyid FROM entity_get_partition_markers('/type/author', $AUTHORS_CHUNK_SIZE)")
for key in $AUTHORS_PARTITIONS; do
  key=${key//$'\r'/} # get rid of embedded returns
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder authors --start-at $key --limit $AUTHORS_CHUNK_SIZE -p progress/$RUN_SIG.txt -l logs/$RUN_SIG.txt
  echo sleep 60 | tee /dev/tty | bash;
done;
