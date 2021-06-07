#!/bin/bash

crontab /etc/cron.d/archive-webserver-logs
service cron start
nginx -g "daemon off;"
