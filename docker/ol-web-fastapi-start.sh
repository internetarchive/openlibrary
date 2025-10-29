#!/bin/bash
set -euo pipefail

python --version

# Optional pre-start hook
if [ -n "${BEFORE_START:-}" ] ; then
  eval "$BEFORE_START"
fi

# Ensure default OL_CONFIG path matches compose env
export OL_CONFIG="${OL_CONFIG:-/openlibrary/conf/openlibrary.yml}"

# Run ASGI app via gunicorn with uvicorn workers
# Note: GUNICORN_OPTS may be provided via environment (compose.yaml)
exec gunicorn \
  -k uvicorn.workers.UvicornWorker \
  ${GUNICORN_OPTS:- --reload --workers 4 --timeout 180} \
  --bind :8080 \
  openlibrary.asgi_app:app

