#!/bin/bash

python --version
source docker/ol-install-missing-deps.sh

# Share Prometheus metrics across workers. The directory is scoped to this
# container and must be cleared before each Gunicorn master starts.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus-multiproc}"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
rm -f "$PROMETHEUS_MULTIPROC_DIR"/*.db

exec scripts/openlibrary-server "$OL_CONFIG" \
  --config docker/gunicorn_prometheus_conf.py \
  $GUNICORN_OPTS \
  --bind :8080
