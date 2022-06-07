#!/bin/bash

SERVERS="ol-home0 ol-covers0 ol-web1 ol-web2 ol-www0 ol-solr0"
REPO_DIRS="/opt/olsystem /opt/openlibrary /opt/openlibrary/vendor/infogami /opt/booklending_utils"

for REPO_DIR in $REPO_DIRS; do
    echo $REPO_DIR

    for SERVER in $SERVERS; do
	ssh $SERVER "cd $REPO_DIR; echo -ne $SERVER'\t'; sudo git rev-parse HEAD"
    done
    echo "---"
done

for SERVER in $SERVERS; do
    ssh $SERVER "hostname | docker image ls | grep olbase | grep latest"
done
