#!/bin/bash

if [ -d "/etc/letsencrypt/live/$NGINX_DOMAIN" ] ; then
    certbot certonly --webroot --webroot-path /openlibrary/static -d $NGINX_DOMAIN
fi

if [ -n "$CRONTAB_FILES" ] ; then
  cat $CRONTAB_FILES | crontab -
  service cron start
fi

# logrotate comes from olsystem which is volume mounted
# logrotate requires files to be 644 and owned by root??? (WHAT)
# expect conflicts writing to file
chmod 644 /etc/logrotate.d/nginx
chown root:root /etc/logrotate.d/nginx
logrotate --verbose /etc/logrotate.d/nginx

nginx -g "daemon off;"
