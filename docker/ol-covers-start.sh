#!/bin/bash

python --version
source docker/ol-install-missing-deps.sh
exec scripts/coverstore-server "$COVERSTORE_CONFIG" \
    --gunicorn $GUNICORN_OPTS \
    --bind :7075
