This goes through building a solr instance from a dump file. Assume current directory is `scripts/solr_builder` for all commands unless otherwise stated.

Disk space required:
 - Docker Desktop with all containers including all data - 220 GB
or individual disk space requirements for data:
 - PostgreSQL DB - 55 GB
 - Solr Index - 30 GB
 - solr_builder logs - up to 30 GB

## Step 1: Create a local postgres copy of the database

    ./create-db.sh

Which does the following:
 - start the DB container (building it first, if necessary)
 - create the database and necessary tables
 - download the OpenLibrary dump, decompress it, and load it into the database
   all as a piped streaming operation (~60min - 7857 MB 2019-08-31)
 - create indexes for the tables (~40 min)

# optional; GUI for the database at port 8087
docker-compose up -d --no-deps adminer


## Step 2: Populate solr

### 2a: Setup

```bash
Launch standard pre-built solr:8 containter

    docker-compose up --no-deps -d solr8
#then create the openlibrary core (FIRST TIME ONLY)
    docker-compose exec solr8 solr create -c openlibrary -d /opt/solr/server/solr/configsets/olconfig -n openlibrary
to delete core, if needed:
    docker-compose exec solr8 solr delete -c openlibrary

The configuration for this core is in openlibrary/config/solr8-ol/conf/solrconfig.xml and the schema is in
managed-schema in the same directory.

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

2019-07-31 - Orphans 4.8hrs (deletes off, batch = 1000), Works ETA 1428 hrs (!) with batch size of 1000 due to pathological SQL query plan
  Works 9.3-10.3hrs across 5 shards (deletes off, batch = 5000) for 18450464 (18.4M) works
  (original time was 27 hrs for OJF)

```bash
./index-orphans.sh
```

Solr 8.1 orphans - 4.8 hrs in parallel with 5 shards of works (MacBook Pro, 3128386 (3.1M) orphans, 2019-07-31 dump -- vs 8 hrs for OJF)
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

Extract subjects from the dump

time gzcat ol_dump_2019-08-31.txt.gz | grep '"subjects":' | cut -f 5 | jq -r .subjects[] | gzip > subjects.txt.gz # 55 min
time gzcat subjects.txt.gz | sort | uniq -c | sort -r -n | gzip > subject-counts.txt.gz #


 7189632 total subjects
 gzcat subjects-counts.txt.gz | grep -v -E "^ " | wc -l
    4461 occurring > 1000 times
 gzcat subjects-counts.txt.gz | grep -v -E "^  " | wc -l
   45390 > 100 times
 gzcat subjects-counts.txt.gz | grep -v -E "^   " | wc -l
  379438 > 10 times

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



---------------------

Simultaneous download and build DB

s$ time ./create-db.sh
++ CONTAINER=db
++ DATE=2019-08-31
++ FILE=https://archive.org/download/ol_dump_2019-08-31/ol_dump_2019-08-31.txt.gz
++ alias 'psql=docker-compose exec -T -u postgres $CONTAINER psql postgres -X -t -A $1'
++ docker-compose up -d --no-deps db
Creating network "solr_builder_db-access" with the default driver
Creating network "solr_builder_solr-access" with the default driver
Creating volume "solr_builder_postgres-data" with default driver
Creating volume "solr_builder_solr-data" with default driver
Creating volume "solr_builder_solr8-data" with default driver
Creating volume "solr_builder_ol-vendor" with default driver
Building db
Step 1/2 : FROM  postgres
 ---> c3fe76fef0a6
Step 2/2 : RUN apt-get update && apt-get -qq -y install curl
 ---> Running in 91ea77f11e0f
Ign:1 http://deb.debian.org/debian stretch InRelease
Get:2 http://security.debian.org/debian-security stretch/updates InRelease [94.3 kB]
Get:3 http://deb.debian.org/debian stretch-updates InRelease [91.0 kB]
Get:4 http://deb.debian.org/debian stretch Release [118 kB]
Get:5 http://deb.debian.org/debian stretch Release.gpg [2,434 B]
Get:6 http://security.debian.org/debian-security stretch/updates/main amd64 Packages [503 kB]
Get:7 http://deb.debian.org/debian stretch-updates/main amd64 Packages [27.4 kB]
Get:8 http://deb.debian.org/debian stretch/main amd64 Packages [7,082 kB]
Get:9 http://apt.postgresql.org/pub/repos/apt stretch-pgdg InRelease [51.4 kB]
Get:10 http://apt.postgresql.org/pub/repos/apt stretch-pgdg/main amd64 Packages [182 kB]
Fetched 8,152 kB in 2s (3,129 kB/s)
Reading package lists...
debconf: delaying package configuration, since apt-utils is not installed
Selecting previously unselected package libssl1.0.2:amd64.
(Reading database ... 12782 files and directories currently installed.)
Preparing to unpack .../0-libssl1.0.2_1.0.2s-1~deb9u1_amd64.deb ...
Unpacking libssl1.0.2:amd64 (1.0.2s-1~deb9u1) ...
Selecting previously unselected package ca-certificates.
Preparing to unpack .../1-ca-certificates_20161130+nmu1+deb9u1_all.deb ...
Unpacking ca-certificates (20161130+nmu1+deb9u1) ...
Selecting previously unselected package libidn2-0:amd64.
Preparing to unpack .../2-libidn2-0_0.16-1+deb9u1_amd64.deb ...
Unpacking libidn2-0:amd64 (0.16-1+deb9u1) ...
Selecting previously unselected package libnghttp2-14:amd64.
Preparing to unpack .../3-libnghttp2-14_1.18.1-1+deb9u1_amd64.deb ...
Unpacking libnghttp2-14:amd64 (1.18.1-1+deb9u1) ...
Selecting previously unselected package libpsl5:amd64.
Preparing to unpack .../4-libpsl5_0.17.0-3_amd64.deb ...
Unpacking libpsl5:amd64 (0.17.0-3) ...
Selecting previously unselected package librtmp1:amd64.
Preparing to unpack .../5-librtmp1_2.4+20151223.gitfa8646d.1-1+b1_amd64.deb ...
Unpacking librtmp1:amd64 (2.4+20151223.gitfa8646d.1-1+b1) ...
Selecting previously unselected package libssh2-1:amd64.
Preparing to unpack .../6-libssh2-1_1.7.0-1+deb9u1_amd64.deb ...
Unpacking libssh2-1:amd64 (1.7.0-1+deb9u1) ...
Selecting previously unselected package libcurl3:amd64.
Preparing to unpack .../7-libcurl3_7.52.1-5+deb9u9_amd64.deb ...
Unpacking libcurl3:amd64 (7.52.1-5+deb9u9) ...
Selecting previously unselected package curl.
Preparing to unpack .../8-curl_7.52.1-5+deb9u9_amd64.deb ...
Unpacking curl (7.52.1-5+deb9u9) ...
Selecting previously unselected package publicsuffix.
Preparing to unpack .../9-publicsuffix_20190415.1030-0+deb9u1_all.deb ...
Unpacking publicsuffix (20190415.1030-0+deb9u1) ...
Setting up libidn2-0:amd64 (0.16-1+deb9u1) ...
Setting up libnghttp2-14:amd64 (1.18.1-1+deb9u1) ...
Setting up libpsl5:amd64 (0.17.0-3) ...
Setting up librtmp1:amd64 (2.4+20151223.gitfa8646d.1-1+b1) ...
Setting up libssl1.0.2:amd64 (1.0.2s-1~deb9u1) ...
debconf: unable to initialize frontend: Dialog
debconf: (TERM is not set, so the dialog frontend is not usable.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (Can't locate Term/ReadLine.pm in @INC (you may need to install the Term::ReadLine module) (@INC contains: /etc/perl /usr/local/lib/x86_64-linux-gnu/perl/5.24.1 /usr/local/share/perl/5.24.1 /usr/lib/x86_64-linux-gnu/perl5/5.24 /usr/share/perl5 /usr/lib/x86_64-linux-gnu/perl/5.24 /usr/share/perl/5.24 /usr/local/lib/site_perl /usr/lib/x86_64-linux-gnu/perl-base .) at /usr/share/perl5/Debconf/FrontEnd/Readline.pm line 7.)
debconf: falling back to frontend: Teletype
Setting up libssh2-1:amd64 (1.7.0-1+deb9u1) ...
Processing triggers for libc-bin (2.24-11+deb9u4) ...
Setting up publicsuffix (20190415.1030-0+deb9u1) ...
Setting up ca-certificates (20161130+nmu1+deb9u1) ...
debconf: unable to initialize frontend: Dialog
debconf: (TERM is not set, so the dialog frontend is not usable.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (Can't locate Term/ReadLine.pm in @INC (you may need to install the Term::ReadLine module) (@INC contains: /etc/perl /usr/local/lib/x86_64-linux-gnu/perl/5.24.1 /usr/local/share/perl/5.24.1 /usr/lib/x86_64-linux-gnu/perl5/5.24 /usr/share/perl5 /usr/lib/x86_64-linux-gnu/perl/5.24 /usr/share/perl/5.24 /usr/local/lib/site_perl /usr/lib/x86_64-linux-gnu/perl-base .) at /usr/share/perl5/Debconf/FrontEnd/Readline.pm line 7.)
debconf: falling back to frontend: Teletype
Updating certificates in /etc/ssl/certs...
151 added, 0 removed; done.
Setting up libcurl3:amd64 (7.52.1-5+deb9u9) ...
Setting up curl (7.52.1-5+deb9u9) ...
Processing triggers for ca-certificates (20161130+nmu1+deb9u1) ...
Updating certificates in /etc/ssl/certs...
0 added, 0 removed; done.
Running hooks in /etc/ca-certificates/update.d...
done.
Processing triggers for libc-bin (2.24-11+deb9u4) ...
Removing intermediate container 91ea77f11e0f
 ---> 793544414df8
Successfully built 793544414df8
Successfully tagged solr_builder_db:latest
WARNING: Image for service db was built because it did not already exist. To rebuild this image you must use `docker-compose build` or `docker-compose up --build`.
Creating solr_builder_db_1 ... done
++ sleep 20
++ docker-compose exec -u postgres db psql -d postgres -f sql/create-dump-table.sql
psql:sql/create-dump-table.sql:1: NOTICE:  table "entity" does not exist, skipping
DROP TABLE
psql:sql/create-dump-table.sql:2: NOTICE:  type "type_enum" does not exist, skipping
DROP TYPE
CREATE TYPE
CREATE TABLE

real   0m1.465s
user   0m0.502s
sys    0m0.340s
++ docker-compose exec -u postgres db bash -c 'time curl -L https://archive.org/download/ol_dump_2019-08-31/ol_dump_2019-08-31.txt.gz | gunzip | sed --expression='\''s/\\u0000//g'\'' |  psql -d postgres --user=postgres -c "COPY entity FROM STDIN with delimiter E'\''\t'\'' escape '\''\'\'' quote E'\''\b'\'' csv" '
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
100 7850M  100 7850M    0     0  3928k      0  0:34:06  0:34:06 --:--:-- 4445k
COPY 53586852

real 34m6.623s
user 6m24.290s
sys  3m41.340s

real 34m8.568s (To download and load data)
user 0m0.860s
sys  0m1.154s
++ docker-compose exec -u postgres db psql -d postgres -f sql/create-indices.sql
ALTER TABLE
# computer sleep 6 hrs
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE INDEX
VACUUM
CREATE FUNCTION

  count  
---------
 7082715 (7M Authors)
(1 row)

 26184230 (26.1M Editions)
 18472807 (18.5M Works)
 53586852 (53.5M All entity types)
 53586852 (Matches count from Copy command for DB load)
 53586852 (Matches count from gzcat ol_dump.txt.gz | wc -l)

real	412m26.193s (-360 = 52m to create indexes)
user	0m1.032s
sys	0m2.846s

real	459m54.233s (-360 = 100m)
user	1m3.942s
sys	1m22.033s

