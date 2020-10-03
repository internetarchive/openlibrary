#!/bin/bash

# CAUTION: To git clone infogami, environment variables must be set...
if [[ -z ${GITHUB_TOKEN} ]]; then
    echo "FATAL: Can not git clone olsystem" ;
    exit 1 ;
fi

# apt list --installed
sudo apt-get update
sudo apt-get install -y docker.io docker-compose haproxy
docker --version        # 19.03.8
docker-compose version  #  1.25.0
haproxy -v              #  2.0.13-2ubuntu0.1
sudo systemctl start docker
sudo systemctl enable docker

sudo groupadd --system openlibrary
sudo useradd --no-log-init --system --gid openlibrary --create-home openlibrary

cd /opt
ls -l  # nothing

sudo git clone https://github.com/internetarchive/openlibrary
sudo git clone https://${GITHUB_USERNAME:-$USER}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem
sudo chown openlibrary /opt/*
ls -l  # openlibrary, olsystem owned by openlibrary

cd /opt/openlibrary

git remote -v  # TEMPORARY UNTIL THIS PR LANDS...
sudo git remote add cclauss https://github.com/cclauss/openlibrary
sudo git fetch cclauss Setup-ol-web1
sudo git checkout Setup-ol-web1
git branch

sudo docker-compose down && \
    sudo docker-compose up --no-deps -d memcached && \
    sudo docker-compose -f docker-compose.yml -f docker-compose.infogami-local.yml -f docker-compose.production.yml up --no-deps -d web
