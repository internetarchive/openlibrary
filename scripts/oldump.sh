#! /bin/bash
#
# script to create a dump of all OL records, and generate sitemaps
#
# To run in local environment:
#     docker-compose exec web scripts/oldump.sh $(date +%Y-%m-%d)
# Will create files in the OL root at dumps/ , including edits upto today.
#

set -e

if [ $# -lt 1 ]; then
    echo "USAGE: $0 date [--archive]" 1>&2
    exit 1
fi

SCRIPTS=/openlibrary/scripts
PSQL_PARAMS=${PSQL_PARAMS:-"-h db openlibrary"}
TMPDIR=${TMPDIR:-/openlibrary/dumps}


mkdir -p $TMPDIR
cd $TMPDIR

date=$1
archive=$2

cdump=ol_cdump_$date
dump=ol_dump_$date

function log() {
    echo "* $@" 1>&2
}

# create a clean directory
log "creating clean directories"
rm -rf dumps
mkdir dumps
cd dumps

# Generate Reading Log/Ratings dumps
log "dumping reading log table"
time psql $PSQL_PARAMS --set=upto="$date" -f $SCRIPTS/dump-reading-log.sql | gzip -c > ol_dump_reading-log_$date.txt.gz
log "dumping ratings table"
time psql $PSQL_PARAMS --set=upto="$date" -f $SCRIPTS/dump-ratings.sql | gzip -c > ol_dump_ratings_$date.txt.gz

log "dumping the data table"
time psql $PSQL_PARAMS -c "copy data to stdout" | gzip -c > data.txt.gz

# generate cdump, sort and generate dump
log "generating $cdump.txt.gz"
time $SCRIPTS/oldump.py cdump data.txt.gz $date | gzip -c > $cdump.txt.gz
log "generated $cdump.txt.gz"

echo "deleting the data table dump"
# remove the dump of data table
time rm data.txt.gz

echo "generating the dump."
time gzip -cd $cdump.txt.gz | python $SCRIPTS/oldump.py sort --tmpdir $TMPDIR | python $SCRIPTS/oldump.py dump | gzip -c > $dump.txt.gz
echo "generated $dump.txt.gz"

# Remove the temp sort dir after dump generation
rm -rf $TMPDIR/oldumpsort

echo "splitting the dump"
time gzip -cd $dump.txt.gz | python $SCRIPTS/oldump.py split --format ol_dump_%s_$date.txt.gz
echo "done"

mkdir $dump $cdump
mv ol_dump_*.txt.gz $dump
mv $cdump.txt.gz $cdump

log "dumps are generated at $PWD"


function archive_dumps() {
    # copy stuff to archive.org
    # TODO: Switch to ia client tool. This will only work in production 'til then
    python /olsystem/bin/uploaditem.py $dump --nowait --uploader=openlibrary@archive.org
    python /olsystem/bin/uploaditem.py $cdump --nowait --uploader=openlibrary@archive.org
}

if [ "$archive" == "--archive" ];
then
    archive_dumps
fi

# update sitemaps
log "generating sitemaps"
mkdir -p $TMPDIR/sitemaps
cd $TMPDIR/sitemaps
time python $SCRIPTS/sitemaps/sitemap.py $TMPDIR/dumps/$dump/$dump.txt.gz > sitemaps.log

echo "done"
