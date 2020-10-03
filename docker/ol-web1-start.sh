#!/bin/bash

python --version

sudo rm -f /etc/haproxy/haproxy.cfg
sudo ln --verbose --symbolic opt/olsystem/etc/haproxy/haproxy.cfg   /etc/haproxy/haproxy.cfg

sudo mkdir /etc/nginx || true
sudo ln --verbose --symbolic opt/olsystem/etc/nginx/nginx.conf      /etc/nginx/nginx.conf
sudo ln --verbose --symbolic opt/olsystem/etc/nginx/sites-available /etc/nginx/sites-available

ls -l /etc/haproxy /etc/nginx

authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
