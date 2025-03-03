FROM openlibrary/olbase:latest

ARG DOCKER_KEY_URL=https://download.docker.com/linux/debian/gpg
ARG DOCKER_REPOSITORY_URL=https://download.docker.com/linux/debian
ARG PIP_INDEX_URL

USER root

# Install docker
RUN \
    # Not running update here, since everything should already be up-to-date during deploys,
    # and it causes issues with some of the various prod protections we have in place.
    # apt-get update && \
    # Add Docker's official GPG key:
    apt-get install ca-certificates curl && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL ${DOCKER_KEY_URL} -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    # Add the repository to Apt sources:
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] ${DOCKER_REPOSITORY_URL} bookworm stable" > /etc/apt/sources.list.d/docker.list
# Only apt-update the docker source list, to avoid checking the others which might not be accessible
RUN apt-get update -o Dir::Etc::sourcelist="sources.list.d/docker.list" -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0" && \
    # We just need the CLI since we're running in a container with socket access
    apt-get install -y docker-ce-cli

# Install requirements.txt
COPY --chown=openlibrary:openlibrary scripts/monitoring/requirements.txt scripts/monitoring/requirements.txt
RUN python -m pip install -r scripts/monitoring/requirements.txt
