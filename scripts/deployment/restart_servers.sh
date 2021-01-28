#!/bin/bash

set -o xtrace

# Restart the Docker services on all specified hosts.
# If no host is specified, then the Docker services on this host are restarted.

# Example: restart_servers.sh ol-home0 ol-covers0 ol-web1
# Recognized servers: ol-covers0*, ol-dev*, ol-home0*, ol-web*

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

dockerDown(){
    echo "Rebooting Docker services on $SERVER with COMPOSE_FILE=$COMPOSE_FILE"
    # WARNING! A moment of downtime 😬
    ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE=$COMPOSE_FILE docker-compose down"
    ssh $SERVER "docker volume rm openlibrary_ol-vendor openlibrary_ol-build openlibrary_ol-nodemodules"
}

PRODUCTION="docker-compose.yml:docker-compose.production.yml"
STAGING="docker-compose.yml:docker-compose.staging.yml"

# If no args provided then restart the services on localhost
if [[ $@ == "" ]]; then
    SERVERS="${HOSTNAME:-$HOST}"
else
    SERVERS=$@
fi

for SERVER in $SERVERS; do
    if [[ $SERVER == ol-covers0* ]]; then
        COMPOSE_FILE=$PRODUCTION
        dockerDown $SERVER $COMPOSE_FILE
        ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE=$COMPOSE_FILE docker-compose up -d --scale covers=2 covers_nginx memcached"
    elif [[ $SERVER == ol-dev* ]]; then
        COMPOSE_FILE=$STAGING
        dockerDown $SERVER $COMPOSE_FILE
        ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE="$COMPOSE_FILE" HOSTNAME=${HOSTNAME:-$HOST} PYENV_VERSION=3.9.1 docker-compose up -d --no-deps memcached web"
    elif [[ $SERVER == ol-home0* ]]; then
        COMPOSE_FILE=$PRODUCTION
        dockerDown $SERVER $COMPOSE_FILE
        ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE=$COMPOSE_FILE docker-compose up -d --no-deps infobase infobase_nginx affiliate-server importbot solr-updater"  # cronjobs
    elif [[ $SERVER == ol-web* ]]; then
        COMPOSE_FILE=$PRODUCTION
        dockerDown $SERVER $COMPOSE_FILE
        ssh $SERVER "cd /opt/openlibrary; COMPOSE_HTTP_TIMEOUT=120 docker-compose run -uroot --rm home make i18n"
        ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE=$COMPOSE_FILE HOSTNAME=${HOSTNAME:-$HOST} docker-compose up --no-deps -d web"
    else
        echo "FATAL: $SERVER is not a known host"
        exit 1
    fi
done
