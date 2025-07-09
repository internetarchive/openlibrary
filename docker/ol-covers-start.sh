#!/bin/bash

python --version
exec scripts/coverstore-server "$COVERSTORE_CONFIG" \
    --gunicorn $GUNICORN_OPTS \
    --bind :7075
