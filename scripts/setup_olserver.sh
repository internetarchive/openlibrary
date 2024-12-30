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

# Remove any old versions and install newer versions of Docker Engine and Docker Compose.
# See https://docs.docker.com/engine/install/ubuntu/ for any possible changes.
sudo apt-get remove docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc

sudo apt-get install \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key:
sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

# apparmor is REQUIRED on Internet Archive servers
sudo apt-get install -y \
    apparmor \
    containerd.io \
    docker-ce \
    docker-ce-cli \
    docker-buildx-plugin \
    docker-compose-plugin

docker --version        # 26.0.0, build 2ae903e
docker compose version  # v2.25.0
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

sudo git clone git@github.com:internetarchive/olsystem.git
sudo git clone git@github.com:internetarchive/openlibrary.git
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
# container network access. That would let us use expose/ports from our docker compose file
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
