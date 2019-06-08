#!/usr/bin/env bash

# Convenience aliases/functions
shopt -s expand_aliases
source aliases.sh

set -o xtrace  # Display each line before running it

ORPHANS_COUNT=$(time psql -f sql/count-orphans.sql) # ~15min
RUN_SIG=orphans_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder orphans -p progress/$RUN_SIG.txt
