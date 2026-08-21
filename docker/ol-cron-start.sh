#!/bin/bash

# Expose `OL_CONFIG` to cron
if [ -n "${OL_CONFIG:-}" ]; then
  touch /etc/environment
  grep -q '^OL_CONFIG=' /etc/environment || echo "OL_CONFIG=$OL_CONFIG" >> /etc/environment
fi
crontab /etc/cron.d/openlibrary.ol_home0
cron -f -L2
