#!/bin/bash

crontab /etc/cron.d/openlibrary.ol_home0
cron -f -L2
