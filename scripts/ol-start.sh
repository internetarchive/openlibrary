#!/bin/bash

# Used as /etc/init.d/ol-start for vagrant development boxes.
# Run on startup, and starts all the services needed to get
# a local copy of openlibrary running.

echo "Starting ol services. This might take ~20 seconds."

echo "Starting nginx"
sudo service nginx restart

cd /openlibrary/conf/init
for name in ol-*.service
do
	echo "Starting $name"
	systemctl start $name || systemctl restart $name
done
