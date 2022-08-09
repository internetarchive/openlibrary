#! /bin/bash
#
# Create a dump of all Open Library records, and generate sitemaps
#
# To run in local environment:
#     docker-compose exec web scripts/oldump.sh $(date +%Y-%m-%d)
# Will create files in the OL root at dumps/ , including edits up to today.
#
# Call flow:
# docker-compose.production.yml defines `cron-jobs` Docker container.
# --> docker/ol-cron-start.sh sets up the cron tasks.
#     --> olsystem: /etc/cron.d/openlibrary.ol_home0 defines the actual job
#         --> scripts/oldump.sh
#             --> scripts/oldump.py
#                 --> openlibrary/data/dump.py
#
# To watch the logs on ol-home0, use:
# ol-home0% docker logs -f openlibrary_cron-jobs_1 2>&1 | grep openlibrary.dump
#
# Testing (stats as of November 2021):
# The cron job takes 18+ hours to process 192,000,000+ records in 29GB of data!!
#
# It is therefore essential to test with a subset of the full data so in the file
# `openlibrary/data/dump.py`, the `read_data_file()` has a `max_lines` parameter which
# can control the size of the subset.  In a production setting, leave `max_lines` set
# to zero so that all records are processed.  When testing, set `max_lines` to a more
# reasonable number such as 1_000_000.  The first step of this script will still take
# 110 minutes to extract the 29GB of data from the database so it is highly
# recommended to save a copy of data.txt.gz in another directory to accelerate the
# testing of subsequent job steps.  See `TESTING:` comments below.
#
# Successful data dumps are transferred to:
#     https://archive.org/details/ol_exports?sort=-publicdate

set -e

# To run a testing subset of the full ol-dump, uncomment the following line.
# export OLDUMP_TESTING=true

SCRIPTS=/openlibrary/scripts
PSQL_PARAMS=${PSQL_PARAMS:-"-h db openlibrary"}
TMPDIR=${TMPDIR:-/openlibrary}
OL_CONFIG=${OL_CONFIG:-/openlibrary/conf/openlibrary.yml}

yyyymmdd=$1  # 2022-05-31
yyyymm=${yyyymmdd:0:7}  # 2022-05-31 --> 2022-05

cdump=ol_cdump_$yyyymmdd
dump=ol_dump_$yyyymmdd

if [[ $# -lt 1 ]]
then
    echo "USAGE: $0 yyyy-mm-dd [--archive] [--overwrite]" 1>&2
    exit 1
fi

function cleanup() {
    rm -f $TMPDIR/dumps/data.txt.gz
    rm -rf $TMPDIR/dumps/ol_*
    rm -rf $TMPDIR/sitemaps
}

function log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') [openlibrary.dump] * $@" 1>&2
}

function archive_dumps() {
    # Copy data dumps to https://archive.org/details/ol_exports?sort=-publicdate
    # For progress on transfers, see:
    # https://catalogd.archive.org/catalog.php?checked=1&all=1&banner=rsync%20timeout
    # TODO: Switch to ia client tool. This will only work in production 'til then
    log "ia version is v$(ia --version)"  # ia version is v2.2.0
    is_uploaded=$(ia list ${dump} | wc -l)
    if [[ $is_uploaded == 0 ]]
    then
        log "archive_dumps(): $dump"
	ia --config-file=/olsystem/etc/ia.ini upload $dump  $dump/  --metadata "collection:ol_exports" --metadata "year:${yyyymm:0:4}" --metadata "format:Data" --retries 300
        log "archive_dumps(): $cdump"
	ia --config-file=/olsystem/etc/ia.ini upload $cdump $cdump/ --metadata "collection:ol_exports" --metadata "year:${yyyymm:0:4}" --metadata "format:Data" --retries 300
        log "archive_dumps(): $dump and $cdump have been archived to https://archive.org/details/ol_exports?sort=-publicdate"
    else
	log "Skipping: Archival Zip already exists"
    fi
}

# script <date> --archive --overwrite
log "$@"
log "<host:${HOSTNAME:-$HOST}> <user:$USER> <dir:$TMPDIR>"
log "<cdump:$cdump> <dump:$dump>"

if [[ $@ == *'--overwrite'* ]]
then
   log "Cleaning Up: Found --overwrite, removing old files"
   cleanup
fi

# create a clean directory
mkdir -p $TMPDIR/dumps
cd $TMPDIR/dumps

# If there's not already a completed dump for this YYYY-MM
if [[ ! -d $(compgen -G "ol_cdump_$yyyymm*") ]]
then

  log "=== Step 1 ==="
  # Generate Reading Log/Ratings dumps
  if [[ ! -f $(compgen -G "ol_dump_reading-log_$yyyymm*.txt.gz") ]]
  then
      log "generating reading log table: ol_dump_reading-log_$yyyymmdd.txt.gz"
      time psql $PSQL_PARAMS --set=upto="$yyyymmdd" -f $SCRIPTS/dump-reading-log.sql | gzip -c > ol_dump_reading-log_$yyyymmdd.txt.gz
  else
      log "Skipping: $(compgen -G "ol_dump_reading-log_$yyyymm*.txt.gz")"
  fi


  log "=== Step 2 ==="
  if [[ ! -f $(compgen -G "ol_dump_ratings_$yyyymm*.txt.gz") ]]
  then
      log "generating ratings table: ol_dump_ratings_$yyyymmdd.txt.gz"
      time psql $PSQL_PARAMS --set=upto="$yyyymmdd" -f $SCRIPTS/dump-ratings.sql | gzip -c > ol_dump_ratings_$yyyymmdd.txt.gz
  else
      log "Skipping: $(compgen -G "ol_dump_ratings_$yyyymm*.txt.gz")"
  fi


  log "=== Step 3 ==="
  if [[ ! -f "data.txt.gz" ]]
  then
      log "generating the data table: data.txt.gz -- takes approx. 110 minutes..."
      # In production, we copy the contents of our database into the `data.txt.gz` file.
      # else if we are testing, save a lot of time by using a preexisting `data.txt.gz`.
      if [[ -z $OLDUMP_TESTING ]]; then
	  time psql $PSQL_PARAMS -c "copy data to stdout" | gzip -c > data.txt.gz
      fi
  else
      log "Skipping: data.txt.gz"
  fi


  log "=== Step 4 ==="
  if [[ ! -f $(compgen -G "ol_cdump_$yyyymm*.txt.gz") ]]
  then
      # generate cdump, sort and generate dump
      log "generating $cdump.txt.gz -- takes approx. 500 minutes for 192,000,000+ records..."
      # if $OLDUMP_TESTING has been exported then `oldump.py cdump` will only process a subset.
      time python $SCRIPTS/oldump.py cdump data.txt.gz $yyyymmdd | gzip -c > $cdump.txt.gz
      log "generated $cdump.txt.gz"
  else
      log "Skipping: $(compgen -G "ol_cdump_$yyyymm*.txt.gz")"
  fi


  log "=== Step 5 ==="
  if [[ ! -f $(compgen -G "ol_dump_*.txt.gz") ]]
  then
      echo "generating the dump -- takes approx. 485 minutes for 173,000,000+ records..."
      time gzip -cd $(compgen -G "ol_cdump_$yyyymm*.txt.gz") | python $SCRIPTS/oldump.py sort --tmpdir $TMPDIR | python $SCRIPTS/oldump.py dump | gzip -c > $dump.txt.gz
      echo "generated $dump.txt.gz"
  else
      echo "Skipping: $(compgen -G "ol_dump_$yyyymm*.txt.gz")"
  fi


  log "=== Step 6 ==="
  if [[ ! -f $(compgen -G "ol_dump_*_$yyyymm*.txt.gz") ]]
  then
      mkdir -p $TMPDIR/oldumpsort
      echo "splitting the dump: ol_dump_%s_$yyyymmdd.txt.gz -- takes approx. 85 minutes for 68,000,000+ records..."
      time gzip -cd $dump.txt.gz | python $SCRIPTS/oldump.py split --format ol_dump_%s_$yyyymmdd.txt.gz
      rm -rf $TMPDIR/oldumpsort
  else
      echo "Skipping $(compgen -G "ol_dump_*_$yyyymm*.txt.gz")"
  fi

  mkdir -p $dump $cdump
  mv ol_dump_*.txt.gz $dump
  mv $cdump.txt.gz $cdump

  log "dumps are generated at $PWD"
else
  log "Skipping generation: dumps already exist at $PWD"
fi
ls -lhR

# ========
# Archival
# ========
# Only archive if that caller has requested it and we are not testing.
if [[ $@ == *'--archive'* ]]; then
  if [[ -z $OLDUMP_TESTING ]]; then
    archive_dumps
  else
    log "Skipping archival: Test mode"
  fi
else
  log "Skipping archival: Option omitted"
fi

# =================
# Generate Sitemaps
# =================
if [[ ! -d $TMPDIR/sitemaps ]]
then
    log "generating sitemaps"
    mkdir -p $TMPDIR/sitemaps
    cd $TMPDIR/sitemaps
    time python $SCRIPTS/sitemaps/sitemap.py $TMPDIR/dumps/$dump/$dump.txt.gz > sitemaps.log
    rm -fr $TMPDIR/sitemaps
    ls -lh
else
    log "Skipping sitemaps"
fi

log "$USER has completed $@ in $TMPDIR on ${HOSTNAME:-$HOST}"

# remove the dump of data table
# In production, we remove the raw database dump to save disk space.
# else if we are testing, we keep the raw database dump for subsequent test runs.
if [[ -z $OLDUMP_TESTING ]]
then
    log "deleting the data table dump"
    # After successful run (didn't terminate w/ error)
    # Remove any leftover ol_cdump* and ol_dump* files or directories.
    # Remove the tmp sort dir after dump generation
fi
log "Done."
