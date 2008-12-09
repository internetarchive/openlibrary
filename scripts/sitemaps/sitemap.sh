#! /bin/bash
#
# script to create xml sitemap and html index
#

# print id, key, type and last_modified from thing table
psql -h pharosdb infostore_production -c 'copy thing to stdout' | awk '{ printf("%s\t%s\t%s\t%s\n",$1, $2, $3, $6); }' | sort -n -S1G -k1 > thing.txt

# print id, key for all books
awk '$3 == 52 { printf("%s\t%s\n", $1, $2);}' thing.txt > book_keys.txt

# key_id of "title" is 3  (select * from edition_keys where key='title')
psql -h pharosdb infostore_production -c 'copy edition_str to stdout' | awk '$2 == 3 { printf("%s\t%s\n", $1, $3); }' | sort -n -S1G -k1 > book_titles.txt

python index.py book_titles.txt book_keys.txt
