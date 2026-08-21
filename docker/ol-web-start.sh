#!/bin/bash

python --version
source docker/ol-install-missing-deps.sh

exec scripts/openlibrary-server "$OL_CONFIG" \
  $GUNICORN_OPTS \
  --bind :8080
