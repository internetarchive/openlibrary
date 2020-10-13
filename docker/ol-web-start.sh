#!/bin/bash

echo "USE_NGINX is ${USE_NGINX:false}"
echo "pwd" ; pwd

if [[ "$USE_NGINX" ]]; then
  sudo mkdir /etc/nginx || true
  sudo ln --verbose --symbolic olsystem/etc/nginx/nginx.conf      /etc/nginx/nginx.conf
  sudo ln --verbose --symbolic olsystem/etc/nginx/sites-available /etc/nginx/sites-available
  sudo systemctl start nginx
fi

python --version
echo "pwd" ; pwd
echo "ls -l" ; ls -l /
echo "ls -l /olsystem" ; ls -l /olsystem || true
echo "ls -l /opt/openlibrary/olsystem" ; ls -l /opt/openlibrary/olsystem || true
authbind --deep \
  scripts/openlibrary-server "$OL_CONFIG" \
  --gunicorn \
  $GUNICORN_OPTS \
  --bind :80
