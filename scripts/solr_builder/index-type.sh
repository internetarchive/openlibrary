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
CHUNK_SIZE=10000

done="false"
next_start="//"

runner_id=0

while [ $done != "true" ]; do
  runners=$(docker container ls -q -f "name=ol_run" | wc -l)
  while [ $((runners < INSTANCES)) = "1" ] && [ $done != "true" ]; do
    # Actually start the job
    RUN_SIG="ol_run_${TYPE}s_${runner_id}"
    ((runner_id++))
    mkdir -p {logs,progress}/$LOG_DIR
    touch {logs,progress}/$LOG_DIR/$RUN_SIG.txt
    DOCKER_IMAGE_NAME=$RUN_SIG docker_solr_builder index "${TYPE}s" \
      --start-at "/$next_start" \
      --limit $CHUNK_SIZE \
      -p "progress/$LOG_DIR/$RUN_SIG.txt"

    next_start=$(docker-compose run --rm ol python solr_builder/solr_builder.py fetch-end "${TYPE}s" --start-at "/$next_start" --limit $CHUNK_SIZE)
    if [ "$next_start" = "" ]; then done="true"; fi

    # Stagger starting of the runners so they don't all request a lot of
    # memory/resources at the same time
    if [ $done != "true" ]; then sleep $((3 * 60)); fi

    runners=$(docker container ls -q -f "name=ol_run" | wc -l)
  done;

  if [ $done != "true" ]; then sleep $((5 * 60)); fi
done
