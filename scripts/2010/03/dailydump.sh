#! /bin/bash
#
# Dump daily changes from OL database.
#
# USAGE:
#       ./dailydump.sh dbname date outputdir
# 
# examples:
#       ./dailydump.sh openlibrary 2010-03-20 /dumps/daily/

db=$1
date=$2
dir=$3
file=$dir/$date.log

psql $db -c "copy ( \
    SELECT thing.key, version.revision, version.created \
    FROM thing, version \
    WHERE thing.id=version.thing_id \
        AND version.created >= '$date' \
        AND version.created < date '$date' + interval '1 day' \
    ORDER BY version.created) TO '$file';"
