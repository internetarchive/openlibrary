
## Solr reindex from OL dump

This goes through building a solr instance from a dump file. To build the reindex (only tested on the OJF environment):

### Steps
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
    - Be sure to set the script path to the `Jenkinsfile` in this directory (e.g. `scripts/solr_builder/Jenkinsfile`)
4. Run the pipeline!

Notes:
- Jenkins has a classic UI and a new, Blue Ocean UI. Each has its benefits.
- Logs are stored as artifacts after the jobs are finished, but you can also access the logs by clicking on "workspaces" in the classic UI and navigating to the logs directory (you can usually ignore the paths containing `@`).
- Although it _looks_ like we are starting a Jenkins docker image, which starts a building docker image, which starts the `solr_builder` docker images, because we are forwarding the docker socket, everything is actually happening with the host docker (this is best practice). This has some caveats:
    - You should not assume you have full control of what's running; if you're not careful you will stop other containers
    - You should not try to run multiple re-indexes at the same time. This might be possible, but the current pipeline makes assumptions which would cause this to error

### Possible Issues
#### The SCM field is blank / has no options
Per the "Defining A Pipeline in SCM" page above, the "Definition" section of the Pipeline should be "Pipeline script from SCM". The next step is to choose the source control system by clicking on the "SCM" field, but it might be blank.

Solution: update and restart Jenkins, which can probably be done at the top of the page in the alerts section.

#### Building the pipeline fails almost immediately (various errors)

Check the console output and look for the errors listed below.

##### WorkflowScript: 3: Invalid agent type "dockerfile" specified #####
```
org.codehaus.groovy.control.MultipleCompilationErrorsException: startup failed:
WorkflowScript: 3: Invalid agent type "dockerfile" specified. Must be one of [any, label, none] @ line 3, column 5.
       dockerfile {
       ^
```
Cause: Missing `Docker` and `Docker Pipeline` plugins.

Solution: Dashboard > Manage Jenkins > Mange Plugins. In the left-hand menu, click on "Available plugins" and search for "docker". Then install:
- Docker (possibly displaying as "Docker plugin")
- Docker Pipeline

##### java.lang.NoSuchMethodError: 'boolean org.kohsuke.groovy.sandbox.SandboxTransformer.mightBePositionalArgumentConstructor(org.codehaus.groovy.ast.expr.VariableExpression)' #####
```
java.lang.NoSuchMethodError: 'boolean org.kohsuke.groovy.sandbox.SandboxTransformer.mightBePositionalArgumentConstructor(org.codehaus.groovy.ast.expr.VariableExpression)'
	at com.cloudbees.groovy.cps.SandboxCpsTransformer.visitAssignmentOrCast(SandboxCpsTransformer.java:93)
```
Cause: Out of date Groovy Pipeline plugin:

Solution: Dashboard > Manage Jenkins > Manage Plugins. In the left-hand menu, click on "Installed plugins", search for the "Groovy Pipeline" plugin and update it.


### Editing the Jenkins Pipeline
- If you want to modify the pipeline, you can set the Jenkin's Project to use a local path. Note that you will have to restart Jenkins so that it mounts the path (i.e. `-v "$HOME:/home"`). Alternatively, you can also change the Git url to that of your fork, and specify a branch (e.g. `*/solr-builder--jenkins`) and push to the branch whenever you want to test your code. Jenkins will pull from the branch when you run the project.
- Use VS Code to write your Pipeline; it has a validation extension. See https://jenkins.io/doc/book/pipeline/development/ for other editors/tips
- Read https://jenkins.io/doc/book/pipeline/development/ for general development tips

## Final Sync

TODO. Something along the lines of: Add a solrupdater to compose.production.yaml that points to the new server, and set its offset to be the correct date. See [5493 Move production solr from solr1 to solr0](https://github.com/internetarchive/openlibrary/issues/5493) for hints.

## Deploy

Now that the solr is ready, we can dump its database and import it into the solr on production. Here is the command to do that from the solrbuilder server:

```sh
time docker run --rm \
    --volumes-from solr_builder_solr-1 \
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

# Restore backup file (7min; 2021-08-11 ol-solr0)
# Note the name "openlibrary_solr-data" should match "{OL_DIR}_{SOLR_DATA_VOLUME}", where:
#    OL_DIR: is the name of the directory where the openlibrary repo is; likely openlibrary
#    SOLR_DATA_VOLUME: is the name of the volume the solr service uses; defined in compose.yaml
time docker run -v openlibrary_solr-data:/var/solr/data -v /tmp/solr:/backup ubuntu:xenial \
    tar xzf /backup/solrbuilder-2021-08-11.tar.gz

# Start the services
COMPOSE_FILE="compose.yaml:compose.production.yaml" HOSTNAME="$HOSTNAME"docker compose --profile=ol-solr0 up -d
```

## Resetting

In order to be able to re-run the job, you need to stop/remove any of the old containers you don't intend to re-use:

```sh
# "new" solr containers/volumes
docker rm -f -v solr_builder_solr-1
docker volume rm solr_builder_solr-data

# DB containers/volumes
docker rm -f -v solr_builder_db-1 solr_builder_adminer-1
docker volume rm solr_builder_postgres-data
```
