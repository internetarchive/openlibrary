#!/bin/bash

python --version
authbind --deep \
  scripts/openlibrary-server conf/openlibrary.yml \
  --gunicorn \
  --reload \
  --workers 4 \
  --timeout 180 \
  --bind :80
