#!/bin/bash

# quick method to start all ol services from one script
# inside an container, bypass all upstart/services

echo "Starting ol services."

# TODO: why does nginx appear not necessary?
#echo "Starting nginx"
#service nginx restart

# postgres
su postgres -c "/etc/init.d/postgresql start"

# solr Reports FAIL (port already in use) even though it starts solr
service tomcat7 start

# memcached
service memcached start

# infobase
su openlibrary -c "scripts/infobase-server conf/infobase.yml 7000" &

# wait unit postgres is ready, then reindex solr
su openlibrary -c "until pg_isready; do sleep 5; done && make reindex-solr" &

# solr updater
su openlibrary -c "python scripts/new-solr-updater.py \
  -c conf/openlibrary.yml \
  --state-file solr-update.offset \
  --ol-url http://localhost/" &

# ol server, running in the foreground to avoid exiting container
su openlibrary -c "authbind --deep scripts/openlibrary-server conf/openlibrary.yml startserver 80"
#su openlibrary -c "authbind --deep scripts/openlibrary-server conf/openlibrary.yml --gunicorn -w4 -t180 -b:80"

