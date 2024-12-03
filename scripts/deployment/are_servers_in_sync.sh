#!/bin/bash

SERVER_SUFFIX=${SERVER_SUFFIX:-""}
SERVER_NAMES=${SERVERS:-"ol-home0 ol-covers0 ol-web0 ol-web1 ol-web2 ol-www0"}
SERVERS=$(echo $SERVER_NAMES | sed "s/ /$SERVER_SUFFIX /g")$SERVER_SUFFIX

POLICY_SERVER_NAMES="ol-home0 ol-web0 ol-web1 ol-web2"
POLICY_SERVERS=$(echo $POLICY_SERVER_NAMES | sed "s/ /$SERVER_SUFFIX /g")$SERVER_SUFFIX

REPO_DIRS="/opt/olsystem"

for REPO_DIR in $REPO_DIRS; do
    echo $REPO_DIR

    for SERVER in $SERVERS; do
        echo -ne $(printf "%-10s" $(echo $SERVER | cut -f1 -d '.'))"\t"
        ssh $SERVER "cd $REPO_DIR; sudo git rev-parse HEAD"
    done
    echo "---"
done

echo "/opt/booklending_utils"
for SERVER in $POLICY_SERVERS; do
    echo -ne $(printf "%-10s" $(echo $SERVER | cut -f1 -d '.'))"\t"
    ssh $SERVER "cd /opt/booklending_utils; sudo git rev-parse HEAD"
done
echo "---"

for SERVER in $SERVERS; do
    echo -ne $(printf "%-10s" $(echo $SERVER | cut -f1 -d '.'))"\t"
    ssh $SERVER 'docker image ls | grep olbase | grep latest'
done
