#!/bin/bash

set -o xtrace

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

# This script must be run on each Open Library host to finish a new deployment.

cd /opt/openlibrary
export HOSTNAME="${HOSTNAME:-$HOST}"
export COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml"
# WARNING! Moment of downtime 😬 
docker-compose down
docker volume rm openlibrary_ol-vendor openlibrary_ol-build openlibrary_ol-nodemodules
if [[ $HOSTNAME == ol-covers0.* ]]; then
    docker-compose up -d --scale covers=2 covers_nginx memcached
elif [[ $HOSTNAME == ol-home0.* ]]; then
    docker-compose up -d --no-deps infobase infobase_nginx affiliate-server  # cronjobs importbot solr-updater
else  # start a web node
    docker-compose run -uroot --rm home make i18n
    docker-compose up --no-deps -d web
fi
