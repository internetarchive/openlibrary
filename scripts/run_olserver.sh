#!/bin/bash
# This script git pulls master for openlibrary, infogami, and olsystem
# and then starts the Docker service specified by $SERVICE

cd /opt/olsystem
git pull origin master
cd /opt/openlibrary
git pull origin master
cd /opt/openlibrary/vendor/infogami
git pull origin master
cd /opt/openlibrary

export SERVICE=${SERVICE:-"web"}  # options: web, covers, infobase, home
echo "Starting $SERVICE"
cd /opt/openlibrary
docker-compose build --pull $SERVICE
docker-compose down
docker-compose up -d --no-deps memcached
HOSTNAME=$HOSTNAME docker-compose \
    -f docker-compose.yml \
    -f docker-compose.infogami-local.yml \
    -f docker-compose.production.yml \
    up -d --no-deps $SERVICE
# docker-compose logs -f --tail=10 $SERVICE
