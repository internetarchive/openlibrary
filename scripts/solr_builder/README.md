This goes through building a solr instance from a dump file. Assume current directory is `scripts/solr_builder` for all commands unless otherwise stated.

Disk space required:
 - Docker Desktop with all containers including all data - 220 GB
or individual disk space requirements for data:
 - PostgreSQL DB - 55 GB
 - Solr Index - 30 GB
 - solr_builder logs - up to 30 GB

## Step 1: Create a local postgres copy of the database

### 1a: Create the postgres instance

Start up the database docker container. Note the info in `postgres.ini` for database name, user, password, etc.

```bash
# launch the database container
docker-compose up -d --no-deps db

# optional; GUI for the database at port 8087
docker-compose up -d --no-deps adminer

# create the "entity" table to store the dump
docker-compose exec -u postgres db psql -d postgres -c "DROP TABLE entity CASCADE;" # ~ 5 min
docker-compose exec -u postgres db psql -d postgres -c "DROP TYPE type_enum CASCADE;"
docker-compose exec -u postgres db psql -d postgres -f sql/create-dump-table.sql
```

### 1b: Populate the postgres instance

```bash
# Download the dump
time wget --trust-server-names https://openlibrary.org/data/ol_dump_latest.txt.gz  # 7.5GB, 3min (7 Jun 2019, OJF); 7.4GB, 3min (10 May 2019, OJF); 7.3GB, 6.5min (Feb 2019, OJF)
```
2019-07 18 min on 200 Mb/s US East residential connection
2019-07 30 min on 200 Mb/s US East residential connection

The native location that the OpenLibrary URL points to is of the form:
https://archive.org/download/ol_dump_2019-07-31/ol_dump_2019-07-31.txt.gz
(Yes, it would be simpler to script if they'd chosen the first instead of the last day of the month!)

Now we insert the documents in the dump into postgres. Note that the database at this point has no primary key (for faster import). This does however mean that if you try to insert the same document twice, it will let you. Thankfully, postgres will abandon the whole COPY if it finds an error in the import, so you can just restart the chunk if you found something errored.

```bash
# Start import job(s)
time ./psql-import-in-chunks.sh ol_dump_latest.txt.gz 6  # ~25min (Feb 2019, OJF)
```

Took 2 hrs (8 Jun 2019); 1.75 hrs (10 May 2019, OJF) ; ~2.5 hours (Feb 2019, OJF).

This can be reduced to as low as 16 minutes using 3 shards and no staggered start, but a single stream import is only 19.5
minutes and there appears to be a fencepost issue with the same record getting imported twice in the sharded import, so
I'm just using the single stream import as simpler (plus it can be piped together with the network fetch).

time ./psql-import-in-chunks.sh ol_dump_2019-06-30.txt.gz 1 # 20 minutes

time ./create-db.sh # 26.5 min to download and copy into table
COPY 53530379

ERROR:  invalid input syntax for type json
DETAIL:  Token "created" is invalid.
CONTEXT:  JSON data, line 1: ...s-Design fundamentals, Second edition\", "created...
COPY entity, line 40111410, column content: "{"title": "Electric and hybrid vehicles-Design fundamentals, Second edition\", "created": {"type": "..."
  NUL byte at end of string, not getting correctly stripped by SED (quoting/escaping?)


Once that's all done, we create indices in postgres:

```bash
# 1 hr (8 June 2019, OJF); 1.25 hr (10 May 2019, OJF)
time docker-compose exec -u postgres db psql postgres -f sql/create-indices.sql | ts '[%Y-%m-%d %H:%M:%S]'
```
2019-07 - 22 min. on modern laptop (44 min with new schema?)
2019-08 - 


## Step 2: Populate solr

### 2a: Setup

```bash
# Build the Solr image (same as openlibrary) and launch it
time docker build -t olsolr:latest -f ../../docker/Dockerfile.olsolr ../../ # < 2 min on modern laptop
docker-compose up --no-deps -d solr

or launch standard pre-built solr:8 containter

    docker-compose up --no-deps -d solr8
#then create the openlibrary core (FIRST TIME ONLY)
    docker-compose exec solr8 solr create -c openlibrary -d /opt/solr-8.1.1/server/solr/configsets/olconfig -n openlibrary
to delete core, if needed:
    docker-compose exec solr8 solr delete -c openlibrary

# Build the environment we use to run code that copies data into solr
# This is like a "lite" version of the OL environment
time docker-compose build ol  # ~5 min (Linux/Jan 2019)
# Build the cython files (necessary otherwsie they get overwritten)
docker-compose run ol ./build-cython.sh

# Some convenience aliases/functions
source aliases.sh


### 2b: Insert works & orphaned editions

2019-06-30 dump - 18257278 (18.2M) works, 3687292 (3.7M) orphans
2019-07-31 dump - 18450464 (18.4M) works, 3128386 (3.1M) orphans == 21578850 total - 21571191 loaded == 7659 missing (0.035%)

```bash
# Import over 5 cores
./index-works.sh
```

Works took 27 hrs with 5 cores and orphans also running simultaneously. Note only one batch took that long; all other batches took <18 hours. (27 hrs, 18188010 works, 10 June 2019; 29 hrs, 18081999 works, 13 May 2019, OJF)

And start all the orphans in sequence to each other (in parallel to the works) since ordering them is slow and there aren't too many if them:

Solr 8.1 - 24-26 hrs (with deletes enabled) for 5 shards in parallel with orphans - 18257278 (18.2M) works, MacBook Pro, 2019-06-30 dump

2019-07-31 - Orphans 4.8hrs (deletes off, batch = 1000), Works ETA 1428 hrs (!) with batch size of 1000 due to pathological SQL query plan
  Works 9.3-10.3hrs across 5 shards (deletes off, batch = 5000) for 18450464 (18.4M) works

```bash
./index-orphans.sh
```

Orphans took 8 hrs over 1 core in parallel with works (8 hrs, 3711877 docs, 10 June 2019, OJF; 11 hrs, 3735145 docs, 13 May 2019, OJF).

Solr 8.1 orphans - 4.8 hrs in parallel with 5 shards of works (MacBook Pro, 3128386 (3.1M) orphans, 2019-07-31 dump)
 (Time above is with deletes disabled. It was 3x-4x with them enabled. They aren't needed for bulk loads, but they need
  to be fixed / optimized for normal production updates)

To check progress, run (clearing the progress folder as necessary):

```bash
for f in progress/*; do tail -n1 $f; done;
```

Note the work chunks happen to be (for some reason) pretty uneven, so start the subjects (step 2d) when one of the chunks finishes.

And commit:
```bash
time curl localhost:8984/solr/openlibrary/update?commit=true # ~1s
```

Verify counts: Works + Orphans = 21944570 - 21940724 = 3846 works or orphans missing ie 0.02% (2019-06-30 dump)

### 2c: Insert authors

Note: This must be done AFTER works and orphans; authors query solr to determine how many works are by a given author.

```bash
# index authors over 6 cores
./index-authors.sh
```

Authors took 12 hrs over 6 cores (6980217 authors, 15 May 2019, OJF).

Solr 8.1 (with ICU folding & w/o deletes) - 4.5 hrs across 6 shards - (Aug 2019 MacBook Pro, 7077262 authors, 2019-07-31 dump)
 7077096 loaded, missing 166 authors (0.002%) which require more investigation - no errors logged

After this is done, we have to call `commit` on solr:
```bash
time curl localhost:8984/solr/update?commit=true # ~10s
```
and verify the number of records loaded:
http://localhost:8984/solr/openlibrary/select?facet.field=type&facet=on&q=*%3A*&rows=0
  "facet_counts":{
    "facet_fields":{
      "type":[
        "work",21571191,
        "author",7077096]},


### 2d: Insert subjects

It is currently unknown how subjects make their way into Solr (See See https://github.com/internetarchive/openlibrary/issues/1896 ). As result, in the interest of progress, we are choosing to just use a solr dump.

1. Create a backup of prod's solr (See https://github.com/internetarchive/openlibrary/wiki/Solr#creating-a-solr-backup )
2. Extract the backup (NOT in the repo; anywhere else):
   ```bash
   mkdir ~/solr-backup
   time tar xzf /storage/openlibrary/solr/backup-2019-06-09.tar.gz -C ~/solr-backup # 20min
   mv ~/solr-backup/var/lib/solr/data ~/solr-backup
   rm -r ~/solr-backup/var
   ```
3. Launch the `solr-backup` service, modifying `docker-compose.yml` if the above command was run differently.
    ```bash
    docker-compose up -d --no-deps solr-backup
    ```
4. Copy the subjects into our main solr. 6.75 hrs (May 2019, OJF, 1514068 docs)
    ```bash
    # check the status by going to localhost:8984/solr/dataimport
    curl server.openjournal.foundation:8984/solr/dataimport?command=full-import
    ```

## Step 3: Final Sync

NOTE: These aren't the exact instructions; use with discretion.

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

### Notes

- Monitor the logs for solrupdater. It will sometimes get overloading and slow down a lot; restarting it fixes the issues though.
- 3 weeks of edits takes ~1 week to reindex.