#!/bin/bash

python --version

# Provide a hook for us to specify pre-start tasks
if [ -n "$BEFORE_START" ] ; then
  $BEFORE_START
fi

PYTHONPATH=. exec scripts/openlibrary-server "$OL_CONFIG" \
  $GUNICORN_OPTS \
  --bind :8080
