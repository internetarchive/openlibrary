#!/bin/bash

set -e
# set -o xtrace

# Restart the Docker services on all specified hosts.
# If no host is specified, then restart all servers.

# Example: SERVERS="ol-home0 ol-covers1 ol-web2" restart_servers.sh
# Recognized servers: ol-covers1*, ol-dev*, ol-home0*, ol-web*

# https://docs.openlibrary.org/advanced/deployment-scratchpad.html

PRODUCTION="compose.yaml:compose.production.yaml"
OLIMAGE="${OLIMAGE:-}"
DOCKER_COMPOSE_COMMAND=${DOCKER_COMPOSE_COMMAND:-"up --no-deps -d"}

SERVER_SUFFIX=${SERVER_SUFFIX:-""}
# Note the order matters; we generally want ol-www1 done before the web heads,
# since the web heads use a cache buster in the URL for JS/CSS, and the JS/CSS
# lives on ol-www1. By doing ol-www1 first, we avoid some users accidentally
# getting stuck with old JS/CSS.
SERVER_NAMES=${SERVERS:-"ol-home0 ol-www1 ol-web0 ol-web2 ol-web3 ol-covers1"}
SERVERS=$(echo $SERVER_NAMES | sed "s/ /$SERVER_SUFFIX /g")$SERVER_SUFFIX

for SERVER in $SERVERS; do
    echo "$SERVER ..."
    ssh $SERVER "
        set -e
        HOSTNAME=\$(host $SERVER | cut -d ' ' -f 1)
        cd /opt/openlibrary
        COMPOSE_FILE=$PRODUCTION HOSTNAME=\$HOSTNAME OLIMAGE=$OLIMAGE docker compose --profile $(echo $SERVER | cut -f1 -d '.') $DOCKER_COMPOSE_COMMAND
    "
done

# web_haproxy's image never changes, so the up above leaves it running with the haproxy.cfg and FastAPI route files
# (conf/haproxy) it mounted when it started, which a deploy has since moved aside (see check_nginx_config in deploy.sh).
# Recreate it after the web heads, so it sends a route to FastAPI only once they serve it. `run` checks the new files.
if [[ " $SERVER_NAMES " == *" ol-www1 "* && "$DOCKER_COMPOSE_COMMAND" == up* ]]; then
    SERVER="ol-www1$SERVER_SUFFIX"
    echo "$SERVER web_haproxy ..."
    ssh $SERVER "
        set -e
        export COMPOSE_FILE=$PRODUCTION HOSTNAME=\$(host $SERVER | cut -d ' ' -f 1)
        cd /opt/openlibrary
        if ! docker compose --profile ol-www1 run --rm --no-deps -T web_haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg; then
            echo 'web_haproxy config check failed, so web_haproxy still runs the config and FastAPI routes of the previous deploy.' >&2
            exit 1
        fi
        docker compose --profile ol-www1 up -d --no-deps --force-recreate web_haproxy
    "
fi
