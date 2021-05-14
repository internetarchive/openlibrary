#!/bin/bash

set -o xtrace

# Restart the Docker services on all specified hosts.
# If no host is specified, then the Docker services on this host are restarted.

# Example: restart_servers.sh ol-home0 ol-covers0 ol-web1
# Recognized servers: ol-covers0*, ol-dev*, ol-home0*, ol-web*

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

PRODUCTION="docker-compose.yml:docker-compose.production.yml"
# zsh uses HOST (although we're in a bash context, so maybe not needed?)
HOSTNAME="${HOSTNAME:-$HOST}"
OLIMAGE="${OLIMAGE:-}"

# If no args provided then restart the services on localhost
if [[ $@ == "" ]]; then
    SERVERS="${HOSTNAME}"
else
    SERVERS=$@
fi

for SERVER in $SERVERS; do
    HOSTNAME=$(host $SERVER | cut -d " " -f 1)
    EXTRA_OPTS=""
    if [[ $SERVER == ol-covers0* ]]; then
        EXTRA_OPTS="--scale covers=2"
    fi

    ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE=$PRODUCTION HOSTNAME=$HOSTNAME OLIMAGE=$OLIMAGE docker-compose --profile $(echo $SERVER | cut -f1 -d '.') up --no-deps -d $EXTRA_OPTS"
done
