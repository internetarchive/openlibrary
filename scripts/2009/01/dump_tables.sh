#! /bin/bash
# 
# script to dump tables of production database
#
# run this script as postgres user

db='infobase_production'
dir='/1/pharos/pgdumps'

tables="thing datum edition_str"

for t in $tables
do
    echo `date` -- dumping $t
    psql $db -c "copy $t to stdout" | gzip -c > $dir/.$t.txt.gz
done

echo `date` -- moving files

for t in $tables
do
    mv .$t.txt.gz $t.txt.gz
done

echo `date` -- finished

