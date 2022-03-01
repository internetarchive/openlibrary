#!/bin/bash
# This script is used to provision an ol-server node _before_ docker gets on it.
# It takes a few environment variables:
#
# DOCKER_USERS=""
# The users who will be able to use docker (space-separted)

# Which Ubuntu release are we running on?  Do not fail if /etc/os-release does not exist.
cat /etc/os-release | grep VERSION= || true  # VERSION="20.04.1 LTS (Focal Fossa)"

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

# Give certain users access to docker commands
DOCKER_USERS="nagios $DOCKER_USERS"
for user in $DOCKER_USERS; do
    sudo usermod -aG docker $user
done

sudo groupadd --system openlibrary
sudo useradd --no-log-init --system --gid openlibrary --create-home openlibrary

cd /opt
ls -Fla  # nothing

sudo git clone https://${GITHUB_USERNAME:-$USER}:${GITHUB_TOKEN}@github.com/internetarchive/olsystem
sudo git clone https://github.com/internetarchive/openlibrary
cd /opt/openlibrary
sudo make git
cd /opt/openlibrary/vendor/infogami
sudo git pull origin master
cd /opt/openlibrary

# Set permissions so we do not have to sudo in /scripts/run_olserver.sh
sudo chown root:staff -R /opt/openlibrary /opt/olsystem
sudo chmod g+w -R /opt/openlibrary /opt/olsystem
sudo find /opt/openlibrary -type d -exec chmod g+s {} \;
sudo find /opt/olsystem -type d -exec chmod g+s {} \;

# Setup docker ferm rules for internal-only servers
# Note: This is a bit of an anti-pattern ; we should be using docker, not ferm to manage
# container network access. That would let us use expose/ports from our docker-compose
# to determine what's public. But we'd need a cross-cluster network managed by swarm to
# do that.
PUBLIC_FACING=${PUBLIC_FACING:-'false'}
if [[ $PUBLIC_FACING != 'true' ]]; then
    echo "*** Setting up ferm rules for internal-only servers. ***"
    echo "*** This server will not be accessible from the internet. ***"
    sudo mkdir -p /etc/ferm/docker-user/
    sudo cp /opt/olsystem/etc/ferm/docker-user/ferm.rules /etc/ferm/docker-user/ferm.rules
    sudo service ferm restart
    sudo service docker restart
fi

ls -Fla  # containerd, olsystem, openlibrary owned by openlibrary
