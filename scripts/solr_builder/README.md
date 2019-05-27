This goes through building a solr instance from a dump file. Assume current directory is `scripts/solr_builder` for all commands unless otherwise stated.

## Step 1: Create a local postgres copy of the database

### 1a: Create the postgres instance

Start up the database docker container. Note the info in `postgres.ini` for database name, user, password, etc.

```bash
# launch the database container
docker-compose up -d --no-deps db

# optional; GUI for the database at port 8087
docker-compose up -d --no-deps adminer

# create the "test" table to store the dump
docker-compose exec -u postgres db psql -d postgres -f sql/create-dump-table.sql
```

### 1b: Populate the postgres instance

```bash
# Download the dump
wget https://openlibrary.org/data/ol_dump_latest.txt.gz  # 7.4GB, 3min (10 May 2019, OJF); 7.3GB, 6.5min (Feb 2019, OJF)
```

Now we insert the documents in the dump into postgres. Note that the database at this point has no primary key (for faster import). This does however mean that if you try to insert the same document twice, it will let you. Thankfully, postgres will abandon the whole COPY if it finds an error in the import, so you can just restart the chunk if you found something errored.

```bash
# Start 6 parallel import jobs
time ./psql-import-in-chunks.sh ol_dump_latest.txt.gz 6  # ~25min (Feb 2019, OJF)
```

Unfortunately there's no indication of progress, so you'll just have to wait this one out. You can see if they're done by running: (it will display the number copied once complete.)

```bash
for f in logs/psql-chunk-*; do echo "${f}:" `cat "$f"`; done;
# Sample Output:
# logs/psql-chunk-0.txt: COPY 8531084
# logs/psql-chunk-17062168.txt: COPY 8531084
# logs/psql-chunk-25593252.txt:
# logs/psql-chunk-34124336.txt:
# logs/psql-chunk-42655420.txt:
# logs/psql-chunk-8531084.txt: COPY 8531084
```

Took 1.75 hrs (10 May 2019, OJF) ; ~2.5 hours (Feb 2019, OJF).

Once that's all done, we create indices in postgres:

```bash
# 1.25 hr (10 May 2019, OJF)
time docker-compose exec -u postgres db psql postgres -f sql/create-indices.sql | ts '[%Y-%m-%d %H:%M:%S]'
```

#### TODO
- Investigate if it's better to just ungzip this from the start.
- Right now the parallel processes are all running on the same docker container. Is this a problem?
- Does postgres even benefit from parallel importing? I see some "COPY waiting" processes, maybe there's no benefit?

## Step 2: Populate solr

### 2a: Setup

```bash
# Build the image (same as openlibrary)
time docker build -t olsolr:latest -f ../../docker/Dockerfile.olsolr ../../
# Launch solr
docker-compose up --no-deps -d solr

# Build the environment we use to run code that copies data into solr
# This is like a "lite" version of the OL environment
time docker-compose build ol  # ~5 min (Linux/Jan 2019)

# Setup some convenience aliases/functions
alias psql='docker-compose exec -u postgres db psql postgres -X -t -A $1'
docker_solr_builder() { docker-compose run -d ol python solr_builder/solr_builder.py $@; }
# Use this to launch with live profiling at a random port; makes it SUPER easy to check progress/bottlenecks
# alias docker_solr_builder='docker-compose run -p4000 -d ol python -m cprofilev -a 0.0.0.0 solr_builder.py $1'
pymath () { python3 -c "from math import *; print($1)"; }

# Load a helper function into postgres
psql -f sql/get-partition-markers.sql
```

### 2b: Insert works & orphaned editions

```bash
WORKS_COUNT=$(time psql -c "SELECT count(*) FROM test WHERE \"Type\" = '/type/work'") # ~10min
WORKS_INSTANCES=5
WORKS_CHUNK_SIZE=$(pymath "ceil($WORKS_COUNT / $WORKS_INSTANCES)")

# Partitions the database (~33s)
WORKS_PARTITIONS=$(time psql -c "SELECT \"Key\" FROM test_get_partition_markers('/type/work', $WORKS_CHUNK_SIZE);")
for key in $WORKS_PARTITIONS; do
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder works --start-at $key --limit $WORKS_CHUNK_SIZE -p progress/$RUN_SIG.txt
  echo sleep 60 | tee /dev/tty | bash;
done;
```

Works took 29 hrs (18081999 works, 13 May 2019, OJF) with 5 cores and orphans also running simultaneously. Note only one batch took that long; all other batches took <18 hours.

And start all the orphans in sequence to each other (in parallel to the works) since ordering them is slow and there aren't too many if them:

```bash
ORPHANS_COUNT=$(time psql -f sql/count-orphans.sql) # ~15min
RUN_SIG=orphans_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder orphans -p progress/$RUN_SIG.txt
```

Orphans took 11 hrs over 1 core (3735145 docs, 13 May 2019, OJF), in parallel with works.

To check progress, run (clearing the progress folder as necessary):

```bash
for f in progress/*; do tail -n1 $f; done;
```

Note the work chunks happen to be (for some reason) pretty uneven, so start the subjects (step 2d) when one of the chunks finishes.

### 2c: Insert authors

Note: This must be done AFTER works and orphans; authors query solr to determine how many works are by a given author.

```bash
AUTHOR_COUNT=$(time psql -c "SELECT count(*) FROM test WHERE \"Type\" = '/type/author'") # ~25s
AUTHOR_INSTANCES=6
AUTHORS_CHUNK_SIZE=$(pymath "ceil($AUTHOR_COUNT / $AUTHOR_INSTANCES)")

# Partitions the database (~23s)
AUTHORS_PARTITIONS=$(time psql -c "SELECT \"Key\" FROM test_get_partition_markers('/type/author', $AUTHORS_CHUNK_SIZE)")
for key in $AUTHORS_PARTITIONS; do
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder authors --start-at $key --limit $AUTHORS_CHUNK_SIZE -p progress/$RUN_SIG.txt
  echo sleep 60 | tee /dev/tty | bash;
done;
```

Authors took 12 hrs over 6 cores (6980217 authors, 15 May 2019, OJF). After this is done, we have to call `commit` on solr:

```bash
time curl localhost:8984/solr/update?commit=true # ~25s
```

### 2d: Insert subjects

It is currently unknown how subjects make their way into Solr (See See https://github.com/internetarchive/openlibrary/issues/1896 ). As result, in the interest of progress, we are choosing to just use a solr dump.

1. Create a backup of prod's solr (See https://github.com/internetarchive/openlibrary/wiki/Solr#creating-a-solr-backup )
2. Extract the backup (NOT in the repo; anywhere else)
3. Launch the `solr-backup` service, modifying `docker-compose.yml` with the path of the backup
    ```bash
    docker-compose up -d --no-deps solr-backup
    ```
4. Copy the subjects into our main solr. 6.75 hrs (May 2019, OJF, 1514068 docs)
    ```bash
    # check the status by going to localhost:8984/solr/dataimport
    curl localhost:8984/solr/dataimport?command=full-import
    ```

## Step 3: Final Sync

NONE OF THIS HAS BEEN TESTED YET!

We now have to deal with any changes that occurred since. The last step is to run `solr-updater` on dev linked to the production Infobase logs, and the new solr. Something like:

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