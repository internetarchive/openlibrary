#!/bin/bash

set -o xtrace

# Restart the Docker services on all specified hosts.
# If no host is specified, then restart all servers.

# Example: restart_servers.sh ol-home0 ol-covers0 ol-web1
# Recognized servers: ol-covers0*, ol-dev*, ol-home0*, ol-web*

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

PRODUCTION="compose.yaml:compose.production.yaml"
# zsh uses HOST (although we're in a bash context, so maybe not needed?)
HOSTNAME="${HOSTNAME:-$HOST}"
OLIMAGE="${OLIMAGE:-}"

SERVER_SUFFIX=${SERVER_SUFFIX:-""}
SERVER_NAMES=${SERVERS:-"ol-home0 ol-covers0 ol-web0 ol-web1 ol-web2 ol-www0"}
SERVERS=$(echo $SERVER_NAMES | sed "s/ /$SERVER_SUFFIX /g")$SERVER_SUFFIX

for SERVER in $SERVERS; do
    HOSTNAME=$(host $SERVER | cut -d " " -f 1)
    ssh $SERVER "cd /opt/openlibrary; COMPOSE_FILE=$PRODUCTION HOSTNAME=$HOSTNAME OLIMAGE=$OLIMAGE docker compose --profile $(echo $SERVER | cut -f1 -d '.') up --build --no-deps -d"
done
