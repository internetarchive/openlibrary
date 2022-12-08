#!/bin/bash

python --version
git checkout openlibrary/coverstore/archive.py
scripts/coverstore-server "$COVERSTORE_CONFIG" \
    --gunicorn $GUNICORN_OPTS \
    --bind :7075
