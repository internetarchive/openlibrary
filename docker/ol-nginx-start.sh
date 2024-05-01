#!/bin/bash

# Create certs for domains missing them
CERTBOT_OPTIONS=""
for domain in $NGINX_DOMAIN; do
  CERTBOT_OPTIONS+=" -d $domain"
done
certbot certonly \
  --noninteractive --agree-tos \
  -m openlibrary@archive.org \
  --webroot --webroot-path /openlibrary/static $CERTBOT_OPTIONS

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
