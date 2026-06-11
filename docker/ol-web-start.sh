#!/bin/bash

python --version

exec scripts/openlibrary-server "$OL_CONFIG" \
  $GUNICORN_OPTS \
  --bind :8080
