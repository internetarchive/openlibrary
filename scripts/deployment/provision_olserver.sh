#!/bin/bash
# This script is used to provision an ol-server node _before_ docker gets on it.
# It takes a few environment variables:
#
# DOCKER_USERS=""
# The users who will be able to use docker (space-separated)

echo "This script isn't complete and not ready to be run yet. Please run it line-by-line for now."
exit 1

wait_yn() {
    local prompt=$1

    while true; do
        read -p "$prompt (y/n) " yn
        case $yn in
            [Yy]* ) break;;
            [Nn]* ) exit 1;;
            * ) ;;
        esac
    done
}

# Which debian release are we running on?  Do not fail if /etc/os-release does not exist.
cat /etc/os-release | grep VERSION= || true  # VERSION="13 (trixie)"

# apt list --installed
sudo apt update

# Remove any old versions and install newer versions of Docker Engine and Docker Compose.
# See https://docs.docker.com/engine/install/debian/ for any possible changes.
docker_packages_to_remove=$(dpkg --get-selections docker.io docker-compose docker-doc podman-docker containerd runc | cut -f1)
if [ -n "$docker_packages_to_remove" ]; then
    sudo apt remove $docker_packages_to_remove
fi

sudo apt install \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key:
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://XXXXXX/repository/raw-oss-mirror/mirrored-objects/download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://XXXXXX/repository/apt-docker-debian-proxy/
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update

# apparmor is REQUIRED on Internet Archive servers
sudo apt install -y \
    apparmor \
    containerd.io \
    docker-ce \
    docker-ce-cli \
    docker-buildx-plugin \
    docker-compose-plugin

docker --version        # 29.x.x
docker compose version  # v5.x.x
sudo systemctl status docker

# See "Nexus Artifact Repository User Documentation" in google docs for what to put here
sudo vim /etc/docker/daemon.json
sudo systemctl restart docker

# Give certain users access to docker commands
DOCKER_USERS="nagios $DOCKER_USERS"
for user in $DOCKER_USERS; do
    sudo usermod -aG docker $user
done

sudo groupadd --system openlibrary
sudo useradd --no-log-init --system --gid openlibrary --create-home openlibrary

sudo git config --global init.defaultBranch master

# Here we need to run a deploy to get the commands
echo "Next, you will need to run the deploy script to get olsystem and openlibrary"
echo "onto the server."
echo ""
echo "For olsystem, run:"
echo "SERVERS=ol-web3 ./scripts/deployment/deploy.sh olsystem"
echo ""
echo "For openlibrary, you will need to choose the tag for the last deploy to"
echo "pass the olbase image check. Find that at https://github.com/internetarchive/openlibrary/releases ,"
echo "and then run:"
echo "SERVERS=ol-web3 GIT_BRANCH='deploy-2026-04-21-at-19-56' ./scripts/deployment/deploy.sh openlibrary"
wait_yn "Enter 'y' once you have run the deploy script and have olsystem and openlibrary on the server."

echo "Next, you will need to patch deploy the PR where you add ol-web3 to the compose files."
echo "Run:"
echo "SERVERS=ol-web3 PATCH_ON=host ./scripts/deployment/patchdeploy.sh 12433"
wait_yn "Enter 'y' once you have patch deployed the PR to add ol-web3 to the compose files."

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

echo "To start everything up, run:"
echo "SERVERS=ol-web3 ./scripts/deployment/deploy.sh images"
echo "SERVERS=ol-web3 ./scripts/deployment/restart_servers.sh"

# TODO: For ol-www0 and ol-home0, follow instructions in https://github.com/internetarchive/olsystem/wiki/Solr-Re%E2%80%90Indexing#setting-up-trending-nginx-log-access
