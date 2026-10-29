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

# Test the config before serving. Most of what nginx parses here comes from
# olsystem over a bind mount, so a bad rule lands in this container without ever
# having been through CI. Without this test `nginx -g` starts, hits [emerg], and
# exits -- and `restart: unless-stopped` turns that into a crash loop that reads
# as "nginx keeps dying" rather than "your config is broken on line N".
#
# This does not keep a bad config from taking the service down; it makes the
# failure immediate and legible instead of a loop. The deploy-time gate in
# scripts/deployment/deploy.sh (check_nginx_config) is what catches it early
# enough to still be fixable, but that only guards the deploy path -- a manual
# restart, a host reboot, or an unrelated `docker compose up` all arrive here.
nginx -t || exit 1

nginx -g "daemon off;"
