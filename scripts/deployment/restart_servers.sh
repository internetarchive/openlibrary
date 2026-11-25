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

HAPROXY_CHECK_FAILED=0
for SERVER in $SERVERS; do
    echo "$SERVER ..."
    PROFILE=$(echo $SERVER | cut -f1 -d '.')
    ssh $SERVER "
        set -e
        HOSTNAME=\$(host $SERVER | cut -d ' ' -f 1)
        cd /opt/openlibrary
        COMPOSE_FILE=$PRODUCTION HOSTNAME=\$HOSTNAME OLIMAGE=$OLIMAGE docker compose --profile $PROFILE $DOCKER_COMPOSE_COMMAND
    "
    # web_haproxy's image never changes, so the up above leaves it running with the haproxy.cfg and FastAPI route files
    # (conf/haproxy) it mounted when it started, which a deploy has since moved aside (see check_nginx_config in deploy.sh).
    # `run` checks the new files before the recreate. A failed check doesn't stop the restart of the other servers.
    if [[ "$PROFILE" == ol-www1 && "$DOCKER_COMPOSE_COMMAND" == up* ]]; then
        ssh $SERVER "
            set -e
            export COMPOSE_FILE=$PRODUCTION HOSTNAME=\$(host $SERVER | cut -d ' ' -f 1)
            cd /opt/openlibrary
            docker compose --profile ol-www1 run --rm --no-deps -T web_haproxy haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
            docker compose --profile ol-www1 up -d --no-deps --force-recreate web_haproxy
        " || HAPROXY_CHECK_FAILED=1
    fi
done

if [[ "$HAPROXY_CHECK_FAILED" == 1 ]]; then
    echo "web_haproxy's config check or recreate failed (see above), so it may still run the previous deploy's config and FastAPI routes." >&2
    exit 1
fi
