#! /bin/bash
#
# Script to create jsondump from given database.
#
# USAGE: jsondump.sh openlibrary -h dbhost

db=$1

cd `dirname $0`/../..
root=`pwd`
cd -

rm -rf dump
mkdir dump
cd dump

psql $* -c 'copy data to stdout' > data.txt
sort -k1 data.txt > data_sorted.txt

python $root/jsondump.py rawdump data_sorted.txt > rawdump.txt
python $root/jsondump.py split_types rawdump.txt
python $root/jsondump.py bookdump type/edition.txt type/author.txt type/language.txt | cut -f3 > bookdump.txt

echo "bookdump saved in dump/bookdump.txt"
