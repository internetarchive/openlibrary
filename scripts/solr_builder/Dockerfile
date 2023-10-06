## This image is where we should execute the Jenkins commands

FROM ubuntu:jammy
ARG DOCKER_VERSION=5:20.10.23~3-0~ubuntu-jammy

# Docker dependencies
RUN apt-get -qq update && apt-get install --no-install-recommends -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    # Script dependencies \
    moreutils \
    wget \
    xmlstarlet \
    && rm -rf /var/lib/apt/lists/*

# Install Docker and Docker Compose
RUN mkdir -m 0755 -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

RUN apt-get -qq update && apt-get install -y --no-install-recommends \
    docker-ce=$DOCKER_VERSION \
    docker-ce-cli=$DOCKER_VERSION \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/* \
    # Default to bash, not dash! \
    && ln -sf /bin/bash /bin/sh
