#!/bin/bash

SERVERS="ol-home0 ol-covers0 ol-web0 ol-web1 ol-web2 ol-www0 ol-solr0"
POLICY_SERVERS="ol-home0 ol-web0 ol-web1 ol-web2"
REPO_DIRS="/opt/olsystem /opt/openlibrary /opt/openlibrary/vendor/infogami"

for REPO_DIR in $REPO_DIRS; do
    echo $REPO_DIR

    for SERVER in $SERVERS; do
        ssh $SERVER "cd $REPO_DIR; echo -ne $SERVER'\t' ; sudo git rev-parse HEAD"
    done
    echo "---"
done

echo "/opt/booklending_utils"
for SERVER in $POLICY_SERVERS; do
    ssh $SERVER "cd /opt/booklending_utils; echo -ne $SERVER'\t' ; sudo git rev-parse HEAD"
done
echo "---"

for SERVER in $SERVERS; do
    echo "$SERVER: $(ssh $SERVER 'hostname | docker image ls | grep olbase | grep latest')"
done
