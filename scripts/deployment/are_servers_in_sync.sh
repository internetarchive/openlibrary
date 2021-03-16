#!/bin/bash

REPO_DIRS="/opt/olsystem /opt/openlibrary /opt/openlibrary/vendor/infogami /opt/booklending_utils"
for REPO_DIR in $REPO_DIRS; do
    echo $REPO_DIR
    SERVERS="ol-home0 ol-covers0 ol-web1 ol-web2"
    for SERVER in $SERVERS; do
	#ssh $SERVER "cd $REPO_DIR; hostname ; sudo git checkout master ; sudo git pull ; git rev-parse HEAD"
	ssh $SERVER "cd $REPO_DIR; hostname ; git rev-parse HEAD"
    done
    echo "---"
done

for SERVER in $SERVERS; do
    ssh $SERVER "hostname | docker image ls | grep oldev | grep latest"
done
