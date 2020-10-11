#!/bin/bash

# CAUTION: To git clone olsystem, environment variables must be set...
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

sudo git clone https://github.com/internetarchive/openlibrary
sudo git clone https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem
sudo chown openlibrary /opt/*
ls -l  # openlibrary, olsystem owned by openlibrary

cd /opt/openlibrary
make git
cd infogami && sudo git pull origin master && cd ..

sudo docker-compose down
USE_NGINX=true sudo docker-compose -f docker-compose.yml -f docker-compose.infogami-local.yml -f docker-compose.production.yml up --no-deps -d web
