#!/bin/bash

python --version
scripts/coverstore-server "$COVERSTORE_CONFIG" \
    --gunicorn $GUNICORN_OPTS \
    --bind :7075
