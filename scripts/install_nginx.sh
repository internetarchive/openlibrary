#! /bin/bash

apt-get update

# log rotation service for ol-nginx
# rsync service for pulling monthly sitemaps from ol-home0 to ol-www0
apt-get install -y --no-install-recommends curl \
    logrotate \
    rsync \
    lsb-release

# Add the NGINX signing key + Repo
curl -fsSL https://nginx.org/keys/nginx_signing.key | tee /usr/share/keyrings/nginx-keyring.asc
echo "deb [signed-by=/usr/share/keyrings/nginx-keyring.asc] http://nginx.org/packages/debian $(lsb_release -cs) nginx" \
    > /etc/apt/sources.list.d/nginx.list

# Install nginx and the NJS module
apt-get update
apt-get install -y --no-install-recommends nginx nginx-module-njs letsencrypt
