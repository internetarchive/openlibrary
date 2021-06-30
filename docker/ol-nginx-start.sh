#!/bin/bash

crontab /etc/cron.d/archive-webserver-logs
service cron start

# logrotate comes from olsystem which is volume mounted
# logrotate requires files to be 644
# expect conflicts writing to file
chmod 644 /etc/logrotate.d/nginx
logrotate --verbose /etc/logrotate.d/nginx

nginx -g "daemon off;"
