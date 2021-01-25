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
fi

# Add a git SHA tag to the Docker image to facilitate rapid rollback
echo "FROM oldev:latest" | docker build -t "oldev:$(git rev-parse HEAD)" -
docker image ls
