#!/bin/bash

python --version

# Provide a hook for us to specify pre-start tasks
if [ -n "$BEFORE_START" ] ; then
  $BEFORE_START
fi

authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
