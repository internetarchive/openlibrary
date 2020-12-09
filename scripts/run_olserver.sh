#!/bin/bash
# This script git pulls master for openlibrary, infogami, and olsystem
# and then starts the Docker service specified by $SERVICE

cd /opt/olsystem
git pull origin master
cd /opt/openlibrary
git pull origin master
cd /opt/openlibrary/vendor/infogami
git pull origin master
if [[ -d "/opt/booklending_utils" ]] ; then
    cd /opt/booklending_utils
    git pull origin master
fi

export COMPOSE_FILE="docker-compose.yml:docker-compose.infogami-local.yml:docker-compose.production.yml"
# SERVICE can be: web, covers, infobase, home
SERVICE=${SERVICE:-web}
echo "Starting $SERVICE"
cd /opt/openlibrary
docker-compose build --pull $SERVICE
docker-compose down
# docker-compose up -d --no-deps memcached
HOSTNAME=$HOSTNAME PYENV_VERSION=3.8.6 docker-compose up -d --no-deps $SERVICE
# docker-compose logs -f --tail=10 $SERVICE
