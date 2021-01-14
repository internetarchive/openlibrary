#!/bin/bash

set -o xtrace

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

# This script must be run on ol-home0 to start a new deployment.

if [[ ${HOSTNAME:-$HOST} != ol-home0.* ]]; then
    echo "FATAL: Must only be run on ol-home0" ;
    exit 1 ;
fi

# `sudo git pull origin master` the core Open Library repos:
# 1. https://github.com/internetarchive/olsystem
# 2. https://git.archive.org/jake/booklending_utils
# 3. https://github.com/internetarchive/openlibrary
# 4. https://github.com/internetarchive/infogami

### Needed to log into BOOKLENDING_UTILS

REPO_DIRS="/opt/olsystem /opt/booklending_utils /opt/openlibrary /opt/openlibrary/vendor/infogami"
for REPO_DIR in $REPO_DIRS
do
    cd $REPO_DIR
    sudo git pull origin master
done

# These commands were run once and probably do not need to be repeated
sudo mkdir -p /opt/olimages
sudo chown root:staff /opt/olimages
sudo chmod g+w /opt/olimages
sudo chmod g+s /opt/olimages
docker image prune -f

# Build the oldev Docker production image
cd /opt/openlibrary
export COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml"
time docker-compose build --pull web
docker-compose run -uroot --rm home make i18n

# Add a timestamp tag to the Docker image to facilitate rapid rollback
# echo "FROM oldev:latest" | docker build -t "oldev:$(date +%Y-%m-%d_%H-%M)" -
echo "FROM oldev:latest" | docker build -t "oldev:$(git rev-parse HEAD)" -
docker image ls

# Compress the image in a .tar.gz file for transfer to other hosts
cd /opt/olimages
time docker save oldev:latest | gzip > oldev_latest.tar.gz

# Transfer the .tar.gz image to other hosts
REMOTE_HOSTS="ol-covers0 ol-web1 ol-web2"
for REMOTE_HOST in $REMOTE_HOSTS
do
    echo "Starting rsync of oldev_latest.tar.gz to $REMOTE_HOST..."
    time rsync -a --no-owner --group --verbose oldev_latest.tar.gz "$REMOTE_HOST:/opt/olimages/"
    echo -e "Finished rsync of oldev_latest.tar.gz to $REMOTE_HOST...\n"
done

echo "Please run continue_production_deploy.sh on ol-covers0, ol-home0, ol-web1, ol-web2"
