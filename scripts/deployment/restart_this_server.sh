#!/bin/bash

set -o xtrace

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

# This script is run on an Open Library host to restart its Docker services.
# Recognized servers: ol-covers0.*, ol-dev*, ol-home0.*, ol-web*

cd /opt/openlibrary
export HOSTNAME="${HOSTNAME:-$HOST}"
echo "Rebooting Docker services on $HOSTNAME from branch $(git branch --show-current) with SHA $(git rev-parse HEAD)"
export COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml"
# WARNING! A moment of downtime 😬 
docker-compose down
docker volume rm openlibrary_ol-vendor openlibrary_ol-build openlibrary_ol-nodemodules
if [[ $HOSTNAME == ol-covers0.* ]]; then
    docker-compose up -d --scale covers=2 covers_nginx memcached
elif [[ $HOSTNAME == ol-dev* ]]; then
    export COMPOSE_FILE="docker-compose.yml:docker-compose.staging.yml"
    PYENV_VERSION=3.9.1 docker-compose up -d --no-deps memcached web
    docker-compose logs -f --tail=10
elif [[ $HOSTNAME == ol-home0.* ]]; then
    docker-compose up -d --no-deps infobase infobase_nginx affiliate-server importbot solr-updater  # cronjobs 
elif [[ $HOSTNAME == ol-web* ]]; then
    docker-compose run -uroot --rm home make i18n
    docker-compose up --no-deps -d web
else
    echo "FATAL: $HOSTNAME is not a known host" ;
    exit 1 ;
fi
