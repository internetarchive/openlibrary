#!/bin/bash

set -o xtrace

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

# This script is run to restart the Docker services on ALL Open Library production servers.

export HOSTNAME="${HOSTNAME:-$HOST}"
SERVERS="ol-home0 ol-covers0 ol-web1"
# Restart Docker services on all hosts EXCEPT ol-web2
for SERVER in $SERVERS
do
    if [[ $SERVER == $HOSTNAME.* ]]; then
        bash /opt/openlibrary/scripts/deployment/restart_this_server.sh
    else
        ssh $SERVER /opt/openlibrary/scripts/deployment/restart_this_server.sh
done

SERVER="ol-web2"
echo "Press return to restart the Docker services on $SERVER ..."
read

# Restart Docker services only on ol-web2
if [[ $SERVER == $HOSTNAME.* ]]; then
    bash /opt/openlibrary/scripts/deployment/restart_this_server.sh
else
    ssh $SERVER /opt/openlibrary/scripts/deployment/restart_this_server.sh
