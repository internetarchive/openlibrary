#!/usr/bin/env bash
# Fully resets the local OpenLibrary Docker environment.
#
# Been away for a while? Getting strange errors you weren't getting before?
# Sometimes changes are made to the docker configs which could cause your
# local environment to break. This script does a full reset so that you
# have the latest of everything.
#
# Usage (run from the root of the openlibrary repo):
#   ./scripts/fully_reset_environment.sh
#
# WARNING: This is destructive. All local volumes and databases will be wiped.
# See docker/README.md for more context.

set -euo pipefail

# Stop the site
docker compose down

# Build the latest oldev image, without cache, whilst also pulling the latest olbase image from docker hub.
# This can take from a few minutes to more than 20 on older hardware.
docker compose build --pull --no-cache

# Remove any old containers/images
# If you use docker for other things, and have containers/images you don't want to lose, be careful with this. But you likely don't :)
docker container prune --filter label="com.docker.compose.project=openlibrary" --force
docker image prune --filter label="com.docker.compose.project=openlibrary" --force

# Remove volumes that might have outdated dependencies/code
docker volume rm \
  openlibrary_ol-build \
  openlibrary_ol-nodemodules \
  openlibrary_ol-postgres \
  openlibrary_ol-vendor \
  openlibrary_solr-data \
  openlibrary_solr-updater-data

# Bring it back up again
docker compose up -d
