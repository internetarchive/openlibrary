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
    # Share Prometheus metrics across workers. The directory is scoped to this
    # container and must be cleared before each Gunicorn master starts.
    export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus-multiproc}"
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    rm -f "$PROMETHEUS_MULTIPROC_DIR"/*.db

    exec scripts/coverstore-server "$COVERSTORE_CONFIG" \
        --gunicorn $GUNICORN_OPTS \
        --config docker/gunicorn_prometheus_conf.py \
        --bind :7075
fi
