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

if [ $# -lt 1 ]; then
    echo "USAGE: $0 yyyy-mm-dd [--archive]" 1>&2
    exit 1
fi

SCRIPTS=/openlibrary/scripts
PSQL_PARAMS=${PSQL_PARAMS:-"-h db openlibrary"}
TMPDIR=${TMPDIR:-/openlibrary/dumps}

date=$1
archive=$2

cdump=ol_cdump_$date
dump=ol_dump_$date

function log() {
    echo "* $@" 1>&2
}

MSG="$USER has started $0 $1 $2 in $TMPDIR on ${HOSTNAME:-$HOST} at $(date)"
log $MSG
logger $MSG

# create a clean directory
log "clean directory: $TMPDIR/dumps"
mkdir -p $TMPDIR/dumps
# Remove any leftover ol_cdump* and ol_dump* files or directories.
rm -rf $TMPDIR/dumps/ol_*
cd $TMPDIR/dumps

# Generate Reading Log/Ratings dumps
log "generating reading log table: ol_dump_reading-log_$date.txt.gz"
time psql $PSQL_PARAMS --set=upto="$date" -f $SCRIPTS/dump-reading-log.sql | gzip -c > ol_dump_reading-log_$date.txt.gz

log "generating ratings table: ol_dump_ratings_$date.txt.gz"
time psql $PSQL_PARAMS --set=upto="$date" -f $SCRIPTS/dump-ratings.sql | gzip -c > ol_dump_ratings_$date.txt.gz
ls -lhR

log "generating the data table: data.txt.gz -- takes approx. 110 minutes..."
# In production, we copy the contents of our database into the `data.txt.gz` file.
# else if we are testing, save a lot of time by using a preexisting `data.txt.gz`.
if [[ -z $OLDUMP_TESTING ]]; then
    time psql $PSQL_PARAMS -c "copy data to stdout" | gzip -c > data.txt.gz
fi
ls -lhR  # data.txt.gz is 29G

# generate cdump, sort and generate dump
log "generating $cdump.txt.gz -- takes approx. 500 minutes for 192,000,000+ records..."
# if $OLDUMP_TESTING has been exported then `oldump.py cdump` will only process a subset.
time $SCRIPTS/oldump.py cdump data.txt.gz $date | gzip -c > $cdump.txt.gz
log "generated $cdump.txt.gz"
ls -lhR  # ol_cdump_2021-11-14.txt.gz is 25G

echo "deleting the data table dump"
# remove the dump of data table
# In production, we remove the raw database dump to save disk space.
# else if we are testing, we keep the raw database dump for subsequent test runs.
if [[ -z $OLDUMP_TESTING ]]; then
    rm -f data.txt.gz
fi

echo "generating the dump -- takes approx. 485 minutes for 173,000,000+ records..."
time gzip -cd $cdump.txt.gz | python $SCRIPTS/oldump.py sort --tmpdir $TMPDIR | python $SCRIPTS/oldump.py dump | gzip -c > $dump.txt.gz
echo "generated $dump.txt.gz"
ls -lhR

# Remove the temp sort dir after dump generation
rm -rf $TMPDIR/oldumpsort

echo "splitting the dump: ol_dump_%s_$date.txt.gz -- takes approx. 85 minutes for 68,000,000+ records..."
time gzip -cd $dump.txt.gz | python $SCRIPTS/oldump.py split --format ol_dump_%s_$date.txt.gz
echo "done"

mkdir -p $dump $cdump
mv ol_dump_*.txt.gz $dump
mv $cdump.txt.gz $cdump

log "dumps are generated at $PWD"
ls -lhR


function archive_dumps() {
    # Copy data dumps to https://archive.org/details/ol_exports?sort=-publicdate
    # For progress on transfers, see:
    # https://catalogd.archive.org/catalog.php?checked=1&all=1&banner=rsync%20timeout
    # TODO: Switch to ia client tool. This will only work in production 'til then
    log "ia version is v$(ia --version)"  # ia version is v2.2.0
    ia --config-file=/olsystem/etc/ia.ini upload $dump  $dump/  --metadata "collection:ol_exports" --metadata "year:${date:0:4}" --metadata "format:Data" --retries 300
    ia --config-file=/olsystem/etc/ia.ini upload $cdump $cdump/ --metadata "collection:ol_exports" --metadata "year:${date:0:4}" --metadata "format:Data" --retries 300
}

# Only archive if that caller has requested it and we are not testing.
if [ "$archive" == "--archive" ]; then
    if [[ -z $OLDUMP_TESTING ]]; then
        archive_dumps
    fi
fi


# update sitemaps
log "generating sitemaps"
rm -fr $TMPDIR/sitemaps
mkdir -p $TMPDIR/sitemaps
cd $TMPDIR/sitemaps
time python $SCRIPTS/sitemaps/sitemap.py $TMPDIR/dumps/$dump/$dump.txt.gz > sitemaps.log
ls -lh

MSG="$USER has completed $0 $1 $2 in $TMPDIR on ${HOSTNAME:-$HOST} at $(date)"
echo $MSG
logger $MSG

echo "done"
