#!/bin/bash

# Create certs for domains missing them
RUN_CERTBOT=0
CERTBOT_OPTIONS=""
for domain in $NGINX_DOMAIN; do
  CERTBOT_OPTIONS+=" -d $domain"
  if [ ! -d "/etc/letsencrypt/live/$domain" ]; then
    RUN_CERTBOT=1
  fi
done

if [ "$RUN_CERTBOT" -eq 1 ]; then
  certbot certonly --webroot --webroot-path /openlibrary/static $CERTBOT_OPTIONS
fi

if [ -n "$NGINX_STATS_BUCKET" ]; then
  watch -n 60 /openlibrary/scripts/nginx_http_status.sh "${NGINX_STATS_BUCKET}.http_status" &
  watch -n 60 /openlibrary/scripts/nginx_top_ips.sh "${NGINX_STATS_BUCKET}.top_ips" &
fi

# Run crontab if there are files
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
