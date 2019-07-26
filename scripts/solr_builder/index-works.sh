#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

set -o xtrace  # Display each line before running it

WORKS_COUNT=$(time psql -c "SELECT count(*) FROM entity WHERE etype = CAST('/type/work' AS type_enum)") # ~20s
WORKS_COUNT=${WORKS_COUNT//$'\r'/}
WORKS_INSTANCES=5
WORKS_CHUNK_SIZE=$(pymath "ceil($WORKS_COUNT / $WORKS_INSTANCES)")

# Partitions the database (~35s)
WORKS_PARTITIONS=$(time psql -c "SELECT keyid FROM entity_get_partition_markers('/type/work', $WORKS_CHUNK_SIZE);")
for key in $WORKS_PARTITIONS; do
  key=${key//$'\r'/} # get rid of embedded returns
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder works --ol-config ../../conf/openlibrary-docker.yml --log-level DEBUG --start-at $key --limit $WORKS_CHUNK_SIZE -p progress/$RUN_SIG.txt -l logs/$RUN_SIG.txt
done;
