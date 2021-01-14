#!/bin/bash

set -o xtrace

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

# This script must be run on each Open Library host to continue a new deployment.


export HOSTNAME="${HOSTNAME:-$HOST}"
if [[ $HOSTNAME != ol-home0.* ]]; then
    # ~2 - 4 min
    time docker image prune -f
    # Decompress the .tar.gz image that was transfered from ol-home0
    cd /opt/olimages
    # ~4min
    time docker load < /opt/olimages/oldev_latest.tar.gz

    # `sudo git pull origin master` the core Open Library repos:
    # 1. https://github.com/internetarchive/olsystem
    # 2. https://git.archive.org/jake/booklending_utils -- ONLY ON WEB NODES!!!
    # 3. https://github.com/internetarchive/openlibrary
    # 4. https://github.com/internetarchive/infogami
    REPO_DIRS="/opt/olsystem /opt/booklending_utils /opt/openlibrary /opt/openlibrary/vendor/infogami"
    for REPO_DIR in $REPO_DIRS
    do
        cd $REPO_DIR
        sudo git pull origin master
    done
    cd /opt/openlibrary
    echo "FROM oldev:latest" | docker build -t "oldev:$(git rev-parse HEAD)" -
fi

cd /opt/openlibrary
export COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml"
# WARNING! Moment of downtime 😬 
docker-compose down
docker volume rm openlibrary_ol-vendor openlibrary_ol-build openlibrary_ol-nodemodules
if [[ $HOSTNAME == ol-covers0.* ]]; then
    docker-compose up -d --scale covers=2 covers_nginx memcached
elif [[ $HOSTNAME == ol-home0.* ]]; then
    docker-compose up -d --no-deps infobase infobase_nginx affiliate-server  # cronjobs importbot solr-updater
else  # start a web node
    docker-compose run -uroot --rm home make i18n
    docker-compose up --no-deps -d web
fi
