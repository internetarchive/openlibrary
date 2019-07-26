#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

set -o xtrace  # Display each line before running it

#ORPHANS_COUNT=$(time psql -f sql/count-orphans.sql) # ~15min (~2 min on modern laptop - 3687292 for 2019-06-30)
RUN_SIG=orphans_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder orphans --ol-config ../../conf/openlibrary-docker.yml --log-level DEBUG -p progress/$RUN_SIG.txt -l logs/$RUN_SIG.txt
