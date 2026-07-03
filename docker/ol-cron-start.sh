#!/bin/bash

# Expose `OL_CONFIG` to cron
printenv | grep "^OL_CONFIG=" >> /etc/environment

crontab /etc/cron.d/openlibrary.ol_home0
cron -f -L2
