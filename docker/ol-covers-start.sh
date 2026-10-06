#!/bin/bash
set -euo pipefail

python --version
source docker/ol-install-missing-deps.sh

# In development, use uvicorn since gunicorn's auto-restart is unreliable with asgi
if [ "${LOCAL_DEV:-false}" = "true" ]; then
    exec scripts/coverstore-server "$COVERSTORE_CONFIG" \
        --uvicorn --reload --host 0.0.0.0 --port 7075
else
    # We use gunicorn on prod because it supports --max-requests, which we use to
    # help avoid memory leaks
    exec scripts/coverstore-server "$COVERSTORE_CONFIG" \
        --gunicorn $GUNICORN_OPTS \
        --bind :7075
fi
