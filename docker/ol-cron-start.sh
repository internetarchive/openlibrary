#!/bin/bash

# Expose environment variables to cron
touch /etc/environment
env >> /etc/environment

crontab /etc/cron.d/openlibrary.ol_home0
cron -f -L2
