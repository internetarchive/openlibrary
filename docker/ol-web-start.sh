#!/bin/bash

if [[ "$USE_NGINX" ]]; then
  mkdir /etc/nginx || true
  ln --verbose --symbolic /opt/olsystem/etc/nginx/nginx.conf      /etc/nginx/nginx.conf
  ln --verbose --symbolic /opt/olsystem/etc/nginx/sites-available /etc/nginx/sites-available
  systemctl start nginx
fi

python --version
authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
