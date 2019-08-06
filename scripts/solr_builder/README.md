This goes through building a solr instance from a dump file. To build the reindex (only tested on the OJF environment):

1. Start Jenkins (altering the details as necessary):
```bash
docker run \
  -u root \
  --rm \
  -d \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins-data:/var/jenkins_home \
  -v /storage:/storage \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/lib/docker/volumes/jenkins-data:/var/lib/docker/volumes/jenkins-data \
  --name jenkins \
  jenkinsci/blueocean
```
2. Follow the steps here to finish setting up Jenkins: https://jenkins.io/doc/book/installing/#setup-wizard
3. Follow these steps to create a new Pipeline from git: https://jenkins.io/doc/book/pipeline/getting-started/#defining-a-pipeline-in-scm
    - Be sure to set the script path 
4. Run the pipeline!

Notes:
- Jenkins has a classic UI and a new, Blue Ocean UI. Each has its benefits.
- Logs are stored as artifacts after the jobs are finished, but you can also access the logs by clicking on "workspaces" in the classic UI and navigating to the logs directory (you can usually ignore the paths containing `@`)
- Although it _looks_ like we are starting a Jenkins docker image, which starts a building docker image, which starts the `solr_builder` docker images, because we are forwarding the docker socket, everything is actually happening with the host docker (this is best practice). This has some caveats:
    - You should not assume you have full control of what's running; if you're not careful you will stop other containers
    - You should not try to run multiple re-indexes at the same time. This might be possible, but the current pipeline makes assumptions which would cause this to error   

## Final Sync

NOTE: These aren't the exact instructions; use with discretion.

We now have to deal with any changes that occurred since the dump. The last step is to run `solr-updater` on dev linked to the production Infobase logs, and the new solr. Something like:

```bash
DAY_BEFORE_DUMP='2019-04-30'
cd /opt/openlibrary/openlibrary/
cp conf/openlibrary.yml conf/solrbuilder-openlibrary.yml
vim conf/solrbuilder-openlibrary.yml # Modify to point to new solr
echo "${DAY_BEFORE_DUMP}:0" > solr-builder.offset
```

Create `/etc/supervisor/conf.d/solrbuilder-solrupdater.conf` with:
```
[program:solrbuilder-solrupdater]
command=/olsystem/bin/olenv python /opt/openlibrary/openlibrary/scripts/new-solr-updater.py \
  --config /opt/openlibrary/openlibrary/conf/solrbuilder-openlibrary.yml \
  --state-file /opt/openlibrary/openlibrary/solr-builder.offset \
  --socket-timeout 600
user=solrupdater
directory=/opt/openlibrary/openlibrary
redirect_stderr=true
stdout_logfile=/var/log/openlibrary/solrbuilder-solrupdater.log
environment=USER=solrupdater
```

Then start it:

```bash
supervisorctl start solrbuilder-solrupdater
```

### Notes

- Monitor the logs for solrupdater. It will sometimes get overloading and slow down a lot; restarting it fixes the issues though.
- 3 weeks of edits takes ~1 week to reindex.