#!/bin/bash

set -o xtrace

# See https://github.com/internetarchive/openlibrary/wiki/Deployment-Scratchpad
SERVERS="ol-home0 ol-covers0 ol-web1 ol-web2 ol-www0 ol-solr0"
COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml"

# This script must be run on ol-home0 to start a new deployment.
HOSTNAME="${HOSTNAME:-$HOST}"
if [[ $HOSTNAME != ol-home0.* ]]; then
    echo "FATAL: Must only be run on ol-home0" ;
    exit 1 ;
fi

# Install GNU parallel if not there
# Check is GNU-specific because some hosts had something else called parallel installed
[[ $(parallel --version 2>/dev/null) = GNU* ]] || sudo apt-get -y --no-install-recommends install parallel

echo "Starting production deployment at $(date)"

# `sudo git pull origin master` the core Open Library repos:
parallel --quote ssh {1} "echo -e '\n\n{}'; cd {2} && sudo git pull origin master" ::: $SERVERS ::: /opt/olsystem /opt/openlibrary

# Rebuild & upload docker image for olbase
cd /opt/openlibrary
sudo make git
docker build -t openlibrary/olbase:latest -f docker/Dockerfile.olbase .
docker login
docker push openlibrary/olbase:latest

# Clone booklending utils
parallel --quote ssh {1} "echo -e '\n\n{}'; if [ -d /opt/booklending_utils ]; then cd {2} && sudo git pull git@git.archive.org:jake/booklending_utils.git master; fi" ::: $SERVERS ::: /opt/booklending_utils

# Prune old images now ; this should remove any unused images
parallel --quote ssh {} "echo -e '\n\n{}'; docker image prune -f" ::: $SERVERS

# Pull the latest docker images
parallel --quote ssh {} "echo -e '\n\n{}'; cd /opt/openlibrary && COMPOSE_FILE=\"$COMPOSE_FILE\" docker-compose --profile {} pull --quiet" ::: $SERVERS

# Add a git SHA tag to the Docker image to facilitate rapid rollback
cd /opt/openlibrary
CUR_SHA=$(git rev-parse HEAD | head -c7)
parallel --quote ssh {} "echo -e '\n\n{}'; echo 'FROM openlibrary/olbase:latest' | docker build -t 'openlibrary/olbase:$CUR_SHA' -" ::: $SERVERS

# And tag the deploy!
DEPLOY_TAG="deploy-$(date +%Y-%m-%d)"
sudo git tag $DEPLOY_TAG
sudo git push git@github.com:internetarchive/openlibrary.git $DEPLOY_TAG

echo "Finished production deployment at $(date)"
echo "To reboot the servers, please run scripts/deployments/restart_all_servers.sh"
