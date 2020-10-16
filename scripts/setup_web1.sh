#!/bin/bash

# CAUTION: To git clone olsystem, environment variables must be set...
# Set $GITHUB_USERNAME or $USER will be used.
# Set $GITHUB_TOKEN or this script will halt.
if [[ -z ${GITHUB_TOKEN} ]]; then
    echo "FATAL: Can not git clone olsystem" ;
    exit 1 ;
fi

# apt list --installed
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
docker --version        # 19.03.8
docker-compose version  #  1.25.0
sudo systemctl start docker
sudo systemctl enable docker

sudo groupadd --system openlibrary
sudo useradd --no-log-init --system --gid openlibrary --create-home openlibrary

cd /opt
ls -l  # nothing

# sudo git clone https://github.com/internetarchive/openlibrary
sudo git clone https://github.com/cclauss/openlibrary
sudo git clone https://${GITHUB_USERNAME:-$USER}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem
# sudo git pull https://${GITHUB_USERNAME:-$USER}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem.git master
sudo chown openlibrary /opt/*
ls -l  # containerd, olsystem, openlibrary owned by openlibrary

cd /opt/openlibrary
sudo git checkout Setup-ol-web1-again
sudo make git
cd /opt/openlibrary/vendor/infogami && sudo git pull origin master

cd /opt/openlibrary
sudo docker-compose down
export DOCKER_CLIENT_TIMEOUT=500
export COMPOSE_HTTP_TIMEOUT=500
sudo docker-compose -f docker-compose.yml -f docker-compose.infogami-local.yml -f docker-compose.production.yml up --no-deps -d web ; sudo docker-compose logs --tail=100 -f web