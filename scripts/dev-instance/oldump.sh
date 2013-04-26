#! /bin/bash
# Script to generate OL dump from data table
# Puts the dumps in dumps/ directory
# Designed to work with dev instance.

set -e
set -x

ROOT=$(dirname $0)/../..
SCRIPTS=$ROOT/scripts
DUMP=$ROOT/dump

echo "`date` -- dump the data table"
psql openlibrary -c 'copy data to stdout' > $DUMP/data.txt

echo "`date` -- generating cdump"
$SCRIPTS/oldump.py cdump $DUMP/data.txt > $DUMP/ol_cdump.txt

echo "`date` -- generating dump"
cat $DUMP/ol_cdump.txt | python $SCRIPTS/oldump.py sort | python $SCRIPTS/oldump.py dump > $DUMP/ol_dump.txt
rm -rf /tmp/oldumpsort

echo "`date` -- splitting the dump"
cat $DUMP/ol_dump.txt | python $SCRIPTS/oldump.py split --format $DUMP/ol_dump_%s.txt

touch $DUMP/ia_metadata_dump.txt

echo "generating xworks dumps"
python $SCRIPTS/2011/09/generate_deworks.py $DUMP/ol_dump.txt $DUMP/ia_metadata_dump.txt > $DUMP/ol_xworks.txt