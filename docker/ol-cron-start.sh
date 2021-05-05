#!/bin/bash

crontab /etc/cron.d/openlibrary
cron -f -L2
