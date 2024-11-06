#!/bin/bash

crontab "$CRONTAB_FILE"
cron -f -L2
