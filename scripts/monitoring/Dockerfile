FROM openlibrary/olbase:latest

ARG APT_MIRROR
ARG DOCKER_KEY_URL=https://download.docker.com/linux/debian/gpg
ARG DOCKER_REPOSITORY_URL=https://download.docker.com/linux/debian
ARG PIP_INDEX_URL
ARG UV_DEFAULT_INDEX=$PIP_INDEX_URL

USER root

# Install docker
RUN \
    # Not running update here, since everything should already be up-to-date during deploys,
    # and it causes issues with some of the various prod protections we have in place.
    # apt-get update && \
    # Add Docker's official GPG key:
    apt-get install ca-certificates curl --no-install-recommends && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL ${DOCKER_KEY_URL} -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    # Add the repository to Apt sources:
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] ${DOCKER_REPOSITORY_URL} bookworm stable" > /etc/apt/sources.list.d/docker.list
# Only apt-update the docker source list, to avoid checking the others which might not be accessible
RUN apt-get update -o Dir::Etc::sourcelist="sources.list.d/docker.list" -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0" && \
    # We just need the CLI since we're running in a container with socket access
    apt-get install --no-install-recommends -y docker-ce-cli


# Install netcat
RUN if [ -n "$APT_MIRROR" ]; \
    then \
        echo "deb $APT_MIRROR/debian bookworm main contrib non-free" > /etc/apt/sources.list && \
        echo "deb $APT_MIRROR/debian bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
        echo "deb $APT_MIRROR/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
        # Debian repositories with frequent updates e.g.,
        # ${distro}-security, ${distro}-updates, and ${distro}-backports
        # have a short (one week) Valid-Until expiry
        # which conflicts with our practice of a local apt-mirror updating weekly
        echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99no-check-valid-until && \
        apt-get update -o Dir::Etc::sourcelist="sources.list" -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0"; \
    else \
        apt-get update; \
  fi && \
    apt-get install --no-install-recommends -y netcat-traditional

# Install requirements.txt
COPY --chown=openlibrary:openlibrary scripts/monitoring/requirements.txt scripts/monitoring/requirements.txt
RUN uv pip install -r scripts/monitoring/requirements.txt
