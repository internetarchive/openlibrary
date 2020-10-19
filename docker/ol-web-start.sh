#!/bin/bash

if [[ "$USE_NGINX" ]]; then
  mkdir /etc/nginx || true
  rm -f /etc/nginx/nginx.conf || true
  ln -sfv /olsystem/etc/nginx/nginx.conf      /etc/nginx/nginx.conf
  ln -sfv /olsystem/etc/nginx/sites-available /etc/nginx/sites-available
  systemctl start nginx
fi

python --version
authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
