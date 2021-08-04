## Solr reindex from OL dump

This goes through building a solr instance from a dump file. To build the reindex (only tested on the OJF environment):

1. Start Jenkins (altering the details as necessary):
```bash
docker run \
  -u root \
  -d \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins-data:/var/jenkins_home \
  -v /storage:/storage \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/lib/docker/volumes/jenkins-data:/var/lib/docker/volumes/jenkins-data \
  --restart always \
  --name jenkins \
  jenkinsci/blueocean
```
2. Follow the steps here to finish setting up Jenkins: https://jenkins.io/doc/book/installing/#setup-wizard
3. Follow these steps to create a new Pipeline Project using git: https://jenkins.io/doc/book/pipeline/getting-started/#defining-a-pipeline-in-scm
    - Be sure to set the script path to the `Jenkinsfile` in this directory
4. Run the pipeline!

Notes:
- Jenkins has a classic UI and a new, Blue Ocean UI. Each has its benefits.
- Logs are stored as artifacts after the jobs are finished, but you can also access the logs by clicking on "workspaces" in the classic UI and navigating to the logs directory (you can usually ignore the paths containing `@`).
- Although it _looks_ like we are starting a Jenkins docker image, which starts a building docker image, which starts the `solr_builder` docker images, because we are forwarding the docker socket, everything is actually happening with the host docker (this is best practice). This has some caveats:
    - You should not assume you have full control of what's running; if you're not careful you will stop other containers
    - You should not try to run multiple re-indexes at the same time. This might be possible, but the current pipeline makes assumptions which would cause this to error

### Editing the Jenkins Pipeline
- If you want to modify the pipeline, you can set the Jenkin's Project to use a local path. Note that you will have to restart Jenkins so that it mounts the path (i.e. `-v "$HOME:/home"`). Alternatively, you can also change the Git url to that of your fork, and specify a branch (e.g. `*/solr-builder--jenkins`) and push to the branch whenever you want to test your code. Jenkins will pull from the branch when you run the project.
- Use VS Code to write your Pipeline; it has a validation extension. See https://jenkins.io/doc/book/pipeline/development/ for other editors/tips
- Read https://jenkins.io/doc/book/pipeline/development/ for general development tips

## Final Sync

TODO. Something along the lines of: Add a solrupdater to docker-compose.production.yml that points to the new server, and set its offset to be the correct date.

## Deploy

Now that the solr is ready, we can dump its database and import it into the solr on production. Here is the command to do that from the solrbuilder server:

```sh
time docker run --rm \
    --volumes-from solr_builder_solr_1 \
    -v /tmp/solr:/backup \
    ubuntu:xenial \
    tar czf /backup/solrbuilder-$(date +%Y-%m-%d).tar.gz /var/solr/data
```

(Last run: 41min/14G with 2020-10 dump; OJF)

Then on the production server (ol-solr0) run:

```sh
cd /opt/openlibrary

# Copy file from solrbuilder server (4min; 2020-11-05 ol-solr0)
time scp YOU@SOLR_BUILDER_SERVER:/tmp/solr/solrbuilder-2020-03-02.tar.gz /tmp/solr/solrbuilder-2020-03-02.tar.gz

# Restore backup file (8min; 2020-11-05 ol-solr0)
time sudo docker-compose run --no-deps --rm -v /tmp/solr:/backup solr \
    bash -c "tar xf /backup/solrbuilder-2020-03-02.tar.gz"

# Start the services
COMPOSE_FILE="docker-compose.yml:docker-compose.production.yml" docker-compose --profile=ol-solr0 up -d
```

## Resetting

In order to be able to re-run the job, you need to stop/remove any of the old containers you don't intend to re-use:

```sh
# "new" solr containers/volumes
docker rm -f -v solr_builder_solr_1
docker volume rm solr_builder_solr-data

# DB containers/volumes
docker rm -f -v solr_builder_db_1 solr_builder_adminer_1
docker volume rm solr_builder_postgres-data
```
