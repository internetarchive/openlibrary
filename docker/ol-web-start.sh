#!/bin/bash

if [[ "$USE_NGINX" ]]; then
  sudo mkdir /etc/nginx || true
  sudo ln --verbose --symbolic olsystem/etc/nginx/nginx.conf      /etc/nginx/nginx.conf
  sudo ln --verbose --symbolic olsystem/etc/nginx/sites-available /etc/nginx/sites-available
  sudo systemctl start nginx
fi

python --version
authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
