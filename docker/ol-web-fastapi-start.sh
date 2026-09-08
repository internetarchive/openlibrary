#!/bin/bash
set -euo pipefail

python --version
source docker/ol-install-missing-deps.sh

# Ensure default OL_CONFIG path matches compose env
export OL_CONFIG="${OL_CONFIG:-/openlibrary/conf/openlibrary.yml}"

# In development, use uvicorn since gunicorn's auto-restart is unreliable with asgi
if [ "${LOCAL_DEV:-false}" = "true" ]; then
  # --factory avoids importing openlibrary into the uvicorn reloader parent process (https://uvicorn.dev/#application-factories), which saves ~100 MB of RAM
  exec uvicorn \
    --factory \
    --reload \
    --host 0.0.0.0 \
    --port 8080 \
    openlibrary.asgi_app:create_app
else
  # Run ASGI app via gunicorn with uvicorn workers
  # Note: GUNICORN_OPTS may be provided via environment (compose.yaml)
  # Note: We use gunicorn on prod because it supports --max-requests param
  # which we use to help avoid memory leaks
  exec gunicorn \
    -k uvicorn.workers.UvicornWorker \
    ${GUNICORN_OPTS:- --reload --workers 4 --timeout 180} \
    --bind :8080 \
    "openlibrary.asgi_app:create_app()"
fi
