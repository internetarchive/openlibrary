#!/bin/bash
# This script git pulls master for openlibrary, infogami, and olsystem
# and then starts the Docker service specified by $SERVICE

cd /opt/olsystem
sudo git pull origin master
cd /opt/openlibrary
sudo git pull origin master
cd /opt/openlibrary/vendor/infogami
sudo git pull origin master
cd /opt/openlibrary

export SERVICE=${SERVICE:-"web"}  # options: web, covers, infobase, home
echo "Starting $SERVICE"
cd /opt/openlibrary
sudo docker-compose build --pull $SERVICE
sudo docker-compose down
sudo docker-compose up -d --no-deps memcached
HOSTNAME=$HOSTNAME sudo docker-compose \
    -f docker-compose.yml \
    -f docker-compose.infogami-local.yml \
    -f docker-compose.production.yml \
    up -d --no-deps $SERVICE
# sudo docker-compose logs -f --tail=10 $SERVICE
