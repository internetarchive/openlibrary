#!/bin/bash

set -o xtrace

# https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad

# This script must be run on ol-home0 to start a new deployment.

echo "Starting production deployment at $(date)"
export HOSTNAME="${HOSTNAME:-$HOST}"
if [[ $HOSTNAME != ol-home0.* ]]; then
    echo "FATAL: Must only be run on ol-home0" ;
    exit 1 ;
fi

# `sudo git pull origin master` the core Open Library repos:
### Needed to log into BOOKLENDING_UTILS
REPO_DIRS="/opt/olsystem /opt/openlibrary"
for SERVER in ol-home0 ol-covers0 ol-web1 ol-web2; do
    if [[ $SERVER == ol-web* || $SERVER == ol-home* ]]; then
        REPO_DIRS="$REPO_DIRS /opt/booklending_utils"
    fi
    for REPO_DIR in $REPO_DIRS; do
        ssh $SERVER "cd $REPO_DIR && git pull origin master"
    done
done

# These commands were run once and probably do not need to be repeated
sudo mkdir -p /opt/olimages
sudo chown root:staff /opt/olimages
sudo chmod g+w /opt/olimages
sudo chmod g+s /opt/olimages
docker image prune -f

# Build the oldev Docker production image
cd /opt/openlibrary
d=`date +%Y-%m-%d`
sudo git tag deploy-$d
sudo git push origin deploy-$d
export COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml"
# ~4 min
time docker-compose build --pull web

# Add a git SHA tag to the Docker image to facilitate rapid rollback
echo "FROM oldev:latest" | docker build -t "oldev:$(git rev-parse HEAD)" -
docker image ls

# Compress the image in a .tar.gz file for transfer to other hosts
cd /opt/olimages
# ~4 min
time docker save oldev:latest | gzip > oldev_latest.tar.gz

# Transfer the .tar.gz image and four repo dirs to other hosts
for SERVER in ol-covers0 ol-web1 ol-web2; do
    # ~4 min
    time rsync -a --no-owner --group --verbose oldev_latest.tar.gz "$SERVER:/opt/olimages/"

    # ~2 - 4 min
    time ssh $SERVER docker image prune -f
    # Decompress the .tar.gz image that was transfered from ol-home0
    # ~4 min
    time ssh $SERVER 'docker load < /opt/olimages/oldev_latest.tar.gz'

    # Add a git SHA tag to the Docker image to facilitate rapid rollback
    # Watch the quotes... Three strings concatinated
    ssh $SERVER 'cd /opt/openlibrary && echo "FROM oldev:latest" | docker build -t "oldev:'$(git rev-parse HEAD)'" -'
    ssh $SERVER docker image ls
done

echo "Finished production deployment at $(date)"
echo "To reboot the servers, please run scripts/deployments/restart_all_servers.sh"
