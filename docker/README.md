# Welcome to the new Docker based Open Library development environment!

These current Dockerfiles are designed to be an alternative to the previous Vagrant based development environment.
The setup process and scripts are designed to *NOT* conflict with exisiting Vagrant provisioning, so you should be able to
chose to develop using the exisiting Vagrant method, or try the new Docker approach if you prefer, using the same code branch.

## Build images

From the root directory run:
```
docker build -t olbase:latest -f docker/Dockerfile.olbase .

docker build -t oldev:latest -f docker/Dockerfile.oldev .
```
You must build `olbase` first before `oldev`. Currently (July 2018) the division is a bit arbitrary. More should be moved into `olbase` once we clarify
the production deployment requirements. Currently these docker images are only intented for development environments.

## Run container

Interactive, all services:

`docker run -it --rm -p8080:80 -p7000:7000 -p8983:8983 oldev`

Interactive bash (for checking the container):

`docker run -it --rm -p8080:80 -p7000:7000 -p8983:8983 oldev bash`

Background, detached, mode:

`docker run -d -p8080:80 -p7000:7000 -p8983:8983 oldev`


The commands above expose the main site on host port 8080:
http://localhost:8080

Infobase on port 7000, and solr on port 8983.

To access Solr admin:
http://localhost:8983/solr/admin/

You can customise the host ports by modifying the `-p` publish mapping in the `docker run` command to suit your development environment.

**TODO:** Add dev volume mount to `run` command, and provide instructions for refreshing the application.
