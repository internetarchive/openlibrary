#!/bin/bash
# This script is used to provision an ol-webX node _before_ docker gets on it.
# Assumption: nginx is up-and-running on the platform
sudo systemctl start nginx

# CAUTION: To git clone olsystem, environment variables must be set...
# Set $GITHUB_USERNAME or $USER will be used.
# Set $GITHUB_TOKEN or this script will halt.
if [[ -z ${GITHUB_TOKEN} ]]; then
    echo "FATAL: Can not git clone olsystem" ;
    exit 1 ;
fi

# apt list --installed
sudo apt-get update
sudo apt-get install -y docker.io docker-compose nginx
docker --version        # 19.03.8
docker-compose version  #  1.25.0
sudo systemctl start docker
sudo systemctl enable docker

sudo groupadd --system openlibrary
sudo useradd --no-log-init --system --gid openlibrary --create-home openlibrary

cd /opt
ls -Fla  # nothing

sudo git clone https://${GITHUB_USERNAME:-$USER}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem
# sudo git pull https://${GITHUB_USERNAME:-$USER}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem.git master
# sudo mkdir /etc/nginx
# sudo ln -sfv /opt/olsystem /olsystem
# sudo ln -sfv /opt/olsystem/etc/nginx/nginx.conf /etc/nginx/nginx.conf
# sudo ln -sfv /opt/olsystem/etc/nginx/sites-available /etc/nginx/sites-available
# ls -Fla /etc/nginx  # symlinks in place
# sudo systemctl start nginx
# sudo systemctl enable nginx

OL_DOMAIN=${OL_DOMAIN:-internetarchive}
sudo git clone https://github.com/$OL_DOMAIN/openlibrary
ls -Fla  # containerd, olsystem, openlibrary owned by openlibrary

cd /opt/openlibrary
OL_BRANCH=${OL_BRANCH:-master}
sudo git checkout $OL_BRANCH
sudo make git
cd /opt/openlibrary/vendor/infogami && sudo git pull origin master

cd /opt/openlibrary
sudo docker-compose down
sleep 2
export DOCKER_CLIENT_TIMEOUT=500
export COMPOSE_HTTP_TIMEOUT=500
sudo docker-compose -f docker-compose.yml -f docker-compose.infogami-local.yml -f docker-compose.production.yml up --no-deps -d web
sudo docker-compose logs --tail=100 -f web
