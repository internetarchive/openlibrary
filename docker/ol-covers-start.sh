#!/bin/bash

python --version
scripts/coverstore-server conf/coverstore.yml \
    --gunicorn \
    --workers 1 \
    --max-requests 250 \
    --bind :8081
