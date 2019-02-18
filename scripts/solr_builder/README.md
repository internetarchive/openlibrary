This goes through building a solr instance from a dump file. Assume current directory is `/scripts/solr_builder` for all commands unless otherwise stated.

## Step 1: Create a local postgres copy of the database

### 1a: Create the postgres instance

Start up the database docker container. Note the info in `postgres.ini` for database name, user, password, etc.

```bash
docker-compose up --no-deps -d db # launch the database container
# You might have to wait a little for it to fully "start up"
docker-compose exec -u postgres db psql -d postgres -f sql/create-dump-table.sql # create the "test" table to store the dump
```

### 1b: Populate the postgres instance

Download the data
```bash
wget https://openlibrary.org/data/ol_dump_latest.txt.gz
```

Compute the length of the dump, and split it into 6 approximately equal chunks. Here's the code from when I ran it. Note that the database at this point has no primary key (for faster import). This does however mean that if you try to insert the same document twice, it will let you. Thankfully, postgres will abandon the whole COPY if it finds an error in the import, so you can just restart the chunk if you found something errored.

TODO: Investigate if it's better to just ungzip this from the start.

```bash
# imports the file in 6 parallel chunks; ~ 7m to start the parallel chunks
./psql-import-in-chunks.sh ol_dump_latest.txt.gz 6
```

Unfortunately there's no indication of progress, so you'll just have to wait this one out. You can see if they're done by running:

```bash
for f in logs/psql-chunk-*; do echo "${f}:" `cat "$f"`; done;
```

I forgot to record how long this took exactly, but it's definitely one of those "leave over night" things.

**NOTE: Now would be a good time to do another partial import, if the above took a while, or if the dump is somewhat outdated. See Step 3a.**

Once that's all done, we create indices in postgres:

```bash
# > 10 min; forgot to time some of the indices
docker-compose exec -u postgres db psql -d postgres -f sql/create-indices.sql
```

If you'd like to investigate your handiwork, launch adminer to view the database at port `8087`!

```bash
docker-compose up -d --no-deps adminer
```

## Step 2: Populate solr

### 2a: Setup

```bash
docker build -t olsolr:latest -f ../../docker/Dockerfile.olsolr ../../ # same as openlibrary
docker-compose up --no-deps -d solr # Launch solr

# Build the environment we use to run code that copies data into solr
# This is like a "lite" version of the OL environment
docker build -t olpython:latest -f Dockerfile.olpython . # ~5 min (Linux/Jan 2019)

# Setup some convenience aliases/functions
alias psql='docker-compose exec -u postgres db psql postgres -X -t -A $1'
alias docker_solr_builder='docker-compose run -d ol python solr_builder.py $1'
# Use this to launch with live profiling at a random port; makes it SUPER easy to check progress/bottlenecks
# alias docker_solr_builder='docker-compose run -p4000 -d ol python -m cprofilev -a 0.0.0.0 solr_builder.py $1'
alias pymath='python3 -c "from math import *; print($1)"'

# Load a helper function into postgres
psql -f sql/get-partition-markers.sql
```

### 2b: Insert works & orphaned editions

```bash
WORKS_COUNT=`time psql -c "SELECT count(*) FROM test WHERE \"Type\" = '/type/work'"` # ~25s
WORKS_INSTANCES=5
WORKS_CHUNK_SIZE=`pymath "ceil($WORKS_COUNT / $WORKS_INSTANCES)"`

# Partitions the database (~33s)
WORKS_PARTITIONS=$(psql -c "SELECT \"Key\" FROM test_get_partition_markers('/type/work', $WORKS_CHUNK_SIZE);")
for key in $WORKS_PARTITIONS; do
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder works --start-at $key --limit $WORKS_CHUNK_SIZE -p progress/$RUN_SIG.txt
  echo sleep 60 | tee /dev/tty | bash;
done;
```

And start all the orphans in sequence to each other (in parallel to the works) since ordering them is slow and there aren't too many if them:

```bash
ORPHANS_COUNT=$(psql -f sql/count-orphans.sql)
RUN_SIG=orphans_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder orphans -p progress/$RUN_SIG.txt
```

### 2c: Insert authors

Note: This must be done AFTER works and orphans; authors query solr to determine how many works are by a given author.

```bash
AUTHOR_COUNT=`time psql -c "SELECT count(*) FROM test WHERE \"Type\" = '/type/author'"` # ~25s
AUTHOR_INSTANCES=6
AUTHORS_CHUNK_SIZE=`pymath "ceil($AUTHOR_COUNT / $AUTHOR_INSTANCES)"`

# Partitions the database (~___s)
AUTHORS_PARTITIONS=$(time psql -c "SELECT \"Key\" FROM test_get_partition_markers('/type/author', $AUTHORS_CHUNK_SIZE)")
for key in $AUTHORS_PARTITIONS; do
  RUN_SIG=works_${key//\//}_`date +%Y-%m-%d_%H-%M-%S`
  docker_solr_builder authors --start-at $key --limit AUTHORS_CHUNK_SIZE -p progress/$RUN_SIG.txt
  echo sleep 60 | tee /dev/tty | bash;
done;
```

After this is done, we have to call `commit` on solr:

```bash
curl localhost:8984/solr/update?commit=true
```

## Step 3: Final Sync

NONE OF THIS HAS BEEN TESTED YET!

Since the previous steps took a decent amount of time, we now have to deal with any changes that occurred since.

### 3a: Update postgres

Get the latest date in our postgres

```bash
echo $(psql -c "SELECT \"LastModified\" FROM test ORDER BY \"LastModified\" DESC LIMIT 1")
```

And run the following query on prod (however that works):

```bash
LO_DATE='2019-01-30'  # latest from postgres (from above)
DUMP_FILE=$(echo "dump_${LO_DATE}" | sed -e 's/[: .]/_/g').txt
# NOT TESTED!!!!
psql -v lo_date="$LO_DATE" -f sql/prod-partial-dump.sql openlibrary > test_partial_dump.txt
gzip "${DUMP_FILE}" # ~15s locally
```

Bring that file back to our clone, and import it:

```bash
# ~2.25 hrs for 1 month difference
psql -v source="PROGRAM 'zcat /solr_builder/partial-dump.txt.gz'" -f sql/import-partial.sql
```

### 3b: Update solr 
And now basically repeat everything, but import only the subset of where last modified within the new range.

```bash
LO_DATE='2018-10-30 23:58:49.355353'  # latest from postgres
LO_DATE_CLEAN=$(echo "${LO_DATE}" | sed -e 's/[: .]/_/g')

# Works (~___s for 1 month)
RUN_SIG=works_${LO_DATE_CLEAN}_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder works --last-modified="${LO_DATE}" -p progress/${RUN_SIG}.txt

# Orphans (in parallel!) (~___s for 1 month)
RUN_SIG=orphans_${LO_DATE_CLEAN}_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder orphans --last-modified="${LO_DATE}" -p progress/${RUN_SIG}.txt

# And AFTER all that, authors (~___s for 1 month)
RUN_SIG=authors_${LO_DATE_CLEAN}_`date +%Y-%m-%d_%H-%M-%S`
docker_solr_builder authors --last-modified="${LO_DATE}" -p progress/${RUN_SIG}.txt
```

