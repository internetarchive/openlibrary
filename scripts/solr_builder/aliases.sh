#!/usr/bin/env bash

alias psql='docker-compose exec -T -u postgres db psql postgres -X -t -A $1'
docker_solr_builder() { docker-compose run -d -T ol python solr_builder/solr_builder.py $@; }
# Use this to launch with live profiling at a random port; makes it SUPER easy to check progress/bottlenecks
# alias docker_solr_builder='docker-compose run -p4000 -d ol python -m cprofilev -a 0.0.0.0 solr_builder.py $1'
pymath () { python3 -c "from math import *; print($1)"; }
