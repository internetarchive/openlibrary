FROM openlibrary/olbase:latest

USER root

# Install docker
RUN apt-get update && apt-get install -y docker.io

# Install requirements.txt
COPY --chown=openlibrary:openlibrary scripts/monitoring/requirements.txt scripts/monitoring/requirements.txt
RUN python -m pip install -r scripts/monitoring/requirements.txt
