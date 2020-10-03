#!/bin/bash

python --version
ln --verbose --symbolic opt/olsystem/etc/nginx/nginx.conf      /etc/nginx/nginx.conf
ln --verbose --symbolic opt/olsystem/etc/nginx/sites-available /etc/nginx/sites-available
ln --verbose --symbolic opt/olsystem/etc/haproxy/haproxy.cfg   /etc/haproxy/haproxy.cfg
authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
