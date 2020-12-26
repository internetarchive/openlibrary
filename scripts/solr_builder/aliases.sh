#!/usr/bin/env bash

psql() { docker-compose exec -T -u postgres db psql postgres -X -t -A "$@"; }
docker_solr_builder() { docker-compose run --name $DOCKER_IMAGE_NAME -d -T ol python solr_builder/solr_builder.py "$@"; }
# Use this to launch with live profiling at a random port; makes it SUPER easy to check progress/bottlenecks
pymath() { python3 -c "from math import *; print($1)"; }
