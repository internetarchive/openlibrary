# Pinned Jenkins controller for solr_builder rebuilds.
# Bump procedure: change the FROM tag + versions in plugins.txt and the two ARGs
# below, then `docker compose --profile jenkins build jenkins`.
FROM jenkins/jenkins:2.568.2-lts

# Docker CLI + compose plugin so the Jenkinsfile can drive the *host* docker
# daemon through the mounted socket (docker-in-docker-by-mount).
ARG DOCKER_CLI_VERSION=29.7.2
ARG DOCKER_COMPOSE_VERSION=v5.5.0

USER root
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" \
        | tar xz --strip-components=1 -C /usr/local/bin docker/docker \
    && curl -fsSL "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-linux-x86_64" \
        -o /tmp/docker-compose \
    && install -D -m 0755 /tmp/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose \
    && rm /tmp/docker-compose \
    && docker --version \
    && docker compose version
USER jenkins

# Pin plugins (and their transitive dependencies, resolved at build time)
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli -f /usr/share/jenkins/ref/plugins.txt

# Skip the first-run setup wizard; everything is configured via JCasC + seed job
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
ENV CASC_JENKINS_CONFIG="/var/jenkins_config/jenkins.yaml"
COPY jenkins.yaml /var/jenkins_config/jenkins.yaml
COPY init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/
